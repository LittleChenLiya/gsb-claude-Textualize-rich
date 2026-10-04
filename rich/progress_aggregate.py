"""Weighted parent-child aggregation for :class:`~rich.progress.Progress`.

This module adds an *independent* aggregation layer on top of Progress: a
parent task's progress is computed from the completion *ratios* of its child
tasks and explicit weights. Tasks with different totals are never added
together directly.

The layer deliberately separates *state* from *rendering*:

* :class:`AggregateState` is a plain, immutable snapshot of the aggregation
  result (ratio, indeterminate / failed flags, per-child contributions). It
  can be inspected, logged, serialized, etc. without touching the terminal.
* :meth:`AggregatedProgress.sync` pushes that state into an ordinary
  :class:`~rich.progress.Progress` parent task, so the existing Progress
  display (bars, spinners, ...) renders the aggregate like any other task.

Aggregation rules
-----------------

1. **Weighted ratios.** For children with weights ``w_i`` and ratios
   ``r_i`` (``completed / total``, clamped to ``[0, 1]``) the parent ratio is
   ``sum(w_i * r_i) / sum(w_i)``. A 4-step task and a 1000-step task
   contribute in proportion to their weights, not their raw step counts.
2. **Unknown total.** While *any* active child has ``total=None`` the parent
   is *indeterminate* (``ratio is None``); the Progress bar pulses.
3. **Finished children freeze.** When a child task finishes, its ratio is
   snapshotted. Later updates to the task (or its removal) do not change the
   parent's contribution.
4. **Failure.** A failed child makes the parent *fail*: the parent shows the
   failure status and is never marked as automatically finished, even if the
   frozen ratios would sum to 100%.
5. **Identity vs TaskID.** Children are tracked by a unique identity string,
   *not* by TaskID. If a task is removed from Progress (or its TaskID is
   reused by a different task object), the aggregator detects the
   object-identity change and freezes the old child at its last known
   contribution. Old snapshots can never be associated with a new task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .progress import Progress, ProgressColumn, Task, TaskID
from .table import Column
from .text import Text

__all__ = [
    "AggregatedProgress",
    "AggregateState",
    "ChildAggregateState",
    "ChildState",
    "AggregateStatusColumn",
]


AGG_STATUS_FIELD = "agg_status"
"""Task field key used to pass the aggregate status to the render column."""


class ChildState(str, Enum):
    """Lifecycle state of an aggregated child task."""

    ACTIVE = "active"
    """The child task is still running; its live ratio contributes."""

    FINISHED = "finished"
    """The child ended successfully; its ratio is a frozen snapshot."""

    FAILED = "failed"
    """The child failed; the parent shows failure."""


@dataclass(frozen=True)
class ChildAggregateState:
    """Immutable snapshot of a single child's contribution.

    Attributes:
        identity: Unique identity of the child (independent of TaskID).
        task_id: TaskID the child was registered with.
        name: Human readable name (defaults to the task description).
        weight: Explicit weight of the child.
        state: Lifecycle state.
        ratio: Frozen completion ratio in ``[0, 1]``, or ``None`` if unknown.
    """

    identity: str
    task_id: TaskID
    name: str
    weight: float
    state: ChildState
    ratio: Optional[float]


@dataclass(frozen=True)
class AggregateState:
    """Immutable snapshot of the parent aggregation result.

    Attributes:
        ratio: Weighted completion ratio in ``[0, 1]``, or ``None`` if
            indeterminate.
        total: Normalized total (``100.0``), or ``None`` if indeterminate.
        completed: Weighted completed steps in ``[0, total]``.
        indeterminate: ``True`` while an active child has an unknown total.
        failed: ``True`` if any child failed.
        finished: ``True`` if all children finished successfully (and none
            failed).
        children: Per-child contributions.
    """

    ratio: Optional[float]
    total: Optional[float]
    completed: float
    indeterminate: bool
    failed: bool
    finished: bool
    children: Tuple[ChildAggregateState, ...]


@dataclass
class _Child:
    """Internal record for a registered child."""

    identity: str
    task_id: TaskID
    name: str
    weight: float
    state: ChildState = ChildState.ACTIVE
    ratio: Optional[float] = None
    task_ref: Optional[Task] = field(default=None, repr=False)


class AggregatedProgress:
    """Aggregates weighted child task progress into a parent Progress task.

    The aggregation is independent of rendering: call :meth:`state` to get
    the pure aggregate result, or :meth:`sync` to additionally push it into
    the parent task of a :class:`~rich.progress.Progress` instance, where the
    existing Progress display renders it like any other task.

    Args:
        progress: The Progress instance that owns the parent task and renders
            the display.
        parent_id: TaskID of the parent task that receives the aggregate.
        total: Normalized total written to the parent task. Defaults to 100.
    """

    def __init__(
        self, progress: Progress, parent_id: TaskID, *, total: float = 100.0
    ) -> None:
        if total <= 0:
            raise ValueError("total must be > 0")
        self._progress = progress
        self._parent_id = parent_id
        self._total = float(total)
        self._lock = RLock()
        self._children: Dict[str, _Child] = {}

    @property
    def parent_id(self) -> TaskID:
        """TaskID of the parent task receiving the aggregate."""
        return self._parent_id

    @property
    def identities(self) -> List[str]:
        """Unique identities of all registered children."""
        with self._lock:
            return list(self._children)

    def add_child(self, task_id: TaskID, *, weight: float = 1.0, name: str = "") -> str:
        """Register an existing task as a weighted child.

        The child is tracked by a unique identity, *not* by TaskID. Keep the
        returned identity to call :meth:`fail_child` / :meth:`remove_child`.

        Args:
            task_id: TaskID of the child task (from
                :meth:`~rich.progress.Progress.add_task`).
            weight: Explicit weight of the child. Must be > 0.
            name: Optional name for the child state. Defaults to the task
                description.

        Returns:
            str: A unique identity for the child, independent of TaskID.
        """
        if weight <= 0:
            raise ValueError("weight must be > 0")
        identity = uuid4().hex
        progress = self._progress
        with self._lock, progress._lock:
            task = progress._tasks.get(task_id)
            if task is None:
                raise KeyError(f"unknown task id {task_id!r}")
            if not name:
                name = task.description
            self._children[identity] = _Child(
                identity=identity,
                task_id=task_id,
                name=name,
                weight=float(weight),
                task_ref=task,
            )
        return identity

    def add_child_task(
        self,
        description: str,
        *,
        total: Optional[float] = 100.0,
        weight: float = 1.0,
        name: Optional[str] = None,
        **fields: Any,
    ) -> str:
        """Add a new task to the Progress display and register it as a child.

        Convenience wrapper around
        :meth:`~rich.progress.Progress.add_task` and :meth:`add_child`.

        Returns:
            str: The unique identity of the new child.
        """
        task_id = self._progress.add_task(description, total=total, **fields)
        return self.add_child(
            task_id, weight=weight, name=name if name is not None else description
        )

    def task_id(self, identity: str) -> TaskID:
        """Get the TaskID a child was registered with."""
        with self._lock:
            return self._children[identity].task_id

    def fail_child(self, identity: str) -> None:
        """Mark a child as failed.

        The child's current ratio is snapshotted. The parent will show the
        failure status and will never be automatically marked as finished.
        """
        progress = self._progress
        with self._lock, progress._lock:
            child = self._children[identity]
            if child.state == ChildState.ACTIVE:
                child.ratio = self._read_ratio(child)
            child.state = ChildState.FAILED

    def remove_child(self, identity: str) -> None:
        """Detach a child from the aggregation.

        The child's contribution is dropped from the parent. This does not
        remove the task from the Progress display; use
        :meth:`~rich.progress.Progress.remove_task` for that.
        """
        with self._lock:
            del self._children[identity]

    def state(self) -> AggregateState:
        """Compute the current aggregate state without touching the display.

        This is a pure function of the registered children and their tasks:
        it does not modify the parent task.

        Returns:
            AggregateState: The immutable aggregation result.
        """
        progress = self._progress
        with self._lock, progress._lock:
            children = tuple(self._children.values())
            snapshots: List[ChildAggregateState] = []
            weighted = 0.0
            total_weight = 0.0
            indeterminate = False
            failed = False
            all_finished = bool(children)
            for child in children:
                ratio = self._read_ratio(child)
                snapshots.append(
                    ChildAggregateState(
                        identity=child.identity,
                        task_id=child.task_id,
                        name=child.name,
                        weight=child.weight,
                        state=child.state,
                        ratio=ratio,
                    )
                )
                total_weight += child.weight
                if child.state == ChildState.FAILED:
                    failed = True
                    all_finished = False
                elif child.state == ChildState.ACTIVE:
                    all_finished = False
                    if ratio is None:
                        indeterminate = True
                if ratio is not None:
                    weighted += child.weight * ratio
            if failed:
                all_finished = False
            ratio = (
                None
                if indeterminate
                else weighted / total_weight if total_weight else 0.0
            )
            completed = 0.0 if ratio is None else ratio * self._total
            return AggregateState(
                ratio=ratio,
                total=None if indeterminate else self._total,
                completed=completed,
                indeterminate=indeterminate,
                failed=failed,
                finished=all_finished,
                children=tuple(snapshots),
            )

    def sync(self) -> AggregateState:
        """Compute the aggregate state and push it to the parent task.

        The parent task's ``total`` / ``completed`` are updated so the
        existing Progress display renders the aggregate:

        * indeterminate -> ``total=None`` (the bar pulses),
        * failed -> the ``agg_status`` field is set to ``"failed"`` and the
          parent is never marked finished,
        * finished -> the parent is marked finished (green bar),
        * otherwise -> the weighted ratio is written.

        Returns:
            AggregateState: The state that was applied to the parent task.
        """
        state = self.state()
        progress = self._progress
        with progress._lock:
            task = progress._tasks.get(self._parent_id)
            if task is not None:
                if state.indeterminate:
                    task.total = None
                    task.completed = 0.0
                else:
                    task.total = self._total
                    task.completed = state.completed
                task.fields[AGG_STATUS_FIELD] = (
                    "failed"
                    if state.failed
                    else (
                        "indeterminate"
                        if state.indeterminate
                        else "finished" if state.finished else "active"
                    )
                )
                if state.finished:
                    if task.finished_time is None:
                        task.finished_time = task.elapsed
                else:
                    # A failed / indeterminate parent must never be
                    # auto-marked as finished.
                    task.finished_time = None
        return state

    def _read_ratio(self, child: _Child) -> Optional[float]:
        """Read the live ratio of a child, or return its frozen snapshot.

        Identity is checked by object identity (``task is child.task_ref``),
        *not* by TaskID: if the task was removed from Progress, or its TaskID
        was reused by a different task object, the old child is frozen at its
        last known contribution and the new task is never read.
        """
        task = self._progress._tasks.get(child.task_id)
        if task is None or task is not child.task_ref:
            # Task removed or TaskID reused: freeze the old contribution.
            if child.state == ChildState.ACTIVE:
                child.state = ChildState.FINISHED
            return child.ratio
        if child.state != ChildState.ACTIVE:
            # Finished / failed children keep their frozen snapshot.
            return child.ratio
        if task.finished:
            child.state = ChildState.FINISHED
            child.ratio = self._ratio(task)
            return child.ratio
        ratio = self._ratio(task)
        child.ratio = ratio
        return ratio

    @staticmethod
    def _ratio(task: Task) -> Optional[float]:
        """Completion ratio of a task, clamped to [0, 1]."""
        if task.total is None:
            return None
        if task.total <= 0:
            return 1.0 if task.completed > 0 else 0.0
        return min(1.0, max(0.0, task.completed / task.total))


class AggregateStatusColumn(ProgressColumn):
    """Renders the status of an aggregated parent task.

    Reads the ``agg_status`` field written by :meth:`AggregatedProgress.sync`
    and renders ``FAIL`` / ``....`` / ``DONE`` next to the progress bar.
    """

    def __init__(self, table_column: Optional[Column] = None) -> None:
        super().__init__(table_column=table_column)

    def render(self, task: Task) -> Text:
        status = task.fields.get(AGG_STATUS_FIELD)
        if status == "failed":
            return Text("FAIL", style="bold red")
        if status == "indeterminate":
            return Text("....", style="yellow")
        if status == "finished":
            return Text("DONE", style="green")
        return Text("")
