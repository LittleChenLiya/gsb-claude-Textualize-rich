"""Independent state layer for parent/child progress aggregation.

This module is deliberately free of any Rich imports: it computes
*aggregated state* only and does no rendering.  Use
:class:`rich.aggregate_progress.AggregateProgress` to display the state of a
:class:`ProgressAggregator` with the usual :class:`~rich.progress.Progress`
display.

Aggregation rules
-----------------

* A parent task never sums the raw ``completed``/``total`` numbers of tasks
  with different totals.  Instead, every child contributes its *completion
  ratio* (``completed / total``), multiplied by an explicit ``weight``::

      parent_ratio = sum(child_ratio * child_weight) / sum(child_weight)

* If any *active* (not finished, not failed) child has an unknown total
  (``total is None``), the parent is **indeterminate**.

* Children that finished successfully keep their final contribution (their
  ratio at the moment they succeeded, normally 1.0).

* A failed child makes the parent **failed**; the parent does not silently
  become completed when the remaining children finish.

* Tasks are referenced with a :class:`TaskIdentity`, *not* with a plain
  integer id.  Removing a child and re-adding a task that reuses the same
  integer id produces a new identity (a new generation), so old snapshots
  can never be associated with the new task.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any, Dict, List, Optional, Set, Tuple

_UNSET: Any = object()


class TaskStatus(str, Enum):
    """Lifecycle status of an individual (child) task."""

    PENDING = "pending"
    """The task has been registered but never started."""

    RUNNING = "running"
    """The task is active with a known total."""

    INDETERMINATE = "indeterminate"
    """The task is active but its total is unknown."""

    SUCCESS = "success"
    """The task finished successfully."""

    FAILED = "failed"
    """The task failed."""

    @property
    def active(self) -> bool:
        """bool: Whether the task is still in progress."""
        return self in (
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.INDETERMINATE,
        )

    @property
    def finished(self) -> bool:
        """bool: Whether the task reached a terminal state."""
        return self in (TaskStatus.SUCCESS, TaskStatus.FAILED)


class AggregateStatus(str, Enum):
    """Status of an aggregated parent task."""

    INDETERMINATE = "indeterminate"
    """At least one active child has an unknown total (or there are no children)."""

    RUNNING = "running"
    """All active children have known totals and the work is not done."""

    SUCCESS = "success"
    """Every child finished successfully."""

    FAILED = "failed"
    """At least one child failed."""

    @property
    def active(self) -> bool:
        """bool: Whether the aggregate is still in progress."""
        return self in (AggregateStatus.INDETERMINATE, AggregateStatus.RUNNING)

    @property
    def finished(self) -> bool:
        """bool: Whether the aggregate reached a terminal state."""
        return self in (AggregateStatus.SUCCESS, AggregateStatus.FAILED)


@dataclass(frozen=True)
class TaskIdentity:
    """The identity of a task, kept separate from the plain integer id.

    Two tasks that share the same ``task_id`` (because an id was reused
    after a removal) are *different* tasks as soon as their ``generation``
    differs.  Always compare :class:`TaskIdentity` instances, never the bare
    integer id, when associating snapshots with live tasks.

    Attributes:
        task_id: The caller supplied (or aggregator assigned) integer id.
        generation: Monotonic number, bumped every time the same integer id
            is (re)added after a removal.
    """

    task_id: int
    generation: int

    def __str__(self) -> str:
        return f"#{self.task_id}@gen{self.generation}"


@dataclass(frozen=True)
class ChildSnapshot:
    """Immutable snapshot of a child task at a point in time."""

    identity: TaskIdentity
    """Identity of the child (use this, not ``task_id``, for association)."""

    description: str
    """Description of the child task."""

    weight: float
    """Explicit weight used when aggregating."""

    status: TaskStatus
    """Current lifecycle status of the child."""

    total: Optional[float]
    """Total steps, or ``None`` if unknown."""

    completed: float
    """Steps completed so far."""

    ratio: Optional[float]
    """Completion ratio in ``[0, 1]``; ``None`` while the total is unknown."""


@dataclass(frozen=True)
class AggregateSnapshot:
    """Immutable snapshot of an aggregated parent task."""

    identity: TaskIdentity
    """Identity of the parent task."""

    description: str
    """Description of the parent task."""

    status: AggregateStatus
    """Aggregated lifecycle status."""

    fraction: float
    """Weighted completion fraction in ``[0, 1]``; 0.0 while indeterminate."""

    percentage: float
    """Weighted completion percentage in ``[0, 100]``; 0.0 while indeterminate."""

    children: Tuple[ChildSnapshot, ...]
    """Tuple of :class:`ChildSnapshot` for the children of this parent."""

    @property
    def finished(self) -> bool:
        """bool: Whether the aggregate reached a terminal state."""
        return self.status.finished


@dataclass
class _Child:
    identity: TaskIdentity
    description: str
    weight: float
    status: TaskStatus
    total: Optional[float]
    completed: float
    ratio: Optional[float]
    finished_ratio: Optional[float] = None


def _ratio(total: Optional[float], completed: float) -> Optional[float]:
    if total is None or total <= 0:
        return None
    return min(1.0, max(0.0, completed / total))


class ProgressAggregator:
    """Compute parent/child aggregated progress without rendering anything.

    The aggregator is the *state* counterpart of
    :class:`rich.aggregate_progress.AggregateProgress`: it knows nothing
    about Rich and can be tested, serialised or driven by code that has no
    interest in a terminal display.

    Parents and children are addressed with :class:`TaskIdentity` values,
    returned by :meth:`add_parent` and :meth:`add_child`.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        # Plain integer id -> next generation to hand out. Retained after
        # removal so reused ids get a new generation and a distinct identity.
        self._generations: Dict[int, int] = {}
        self._live_ids: Set[int] = set()
        self._next_id = 1
        self._parents: Dict[TaskIdentity, List[TaskIdentity]] = {}
        self._parent_descriptions: Dict[TaskIdentity, str] = {}
        self._children: Dict[TaskIdentity, _Child] = {}

    # ------------------------------------------------------------------ IDs

    def _new_identity(self, task_id: Optional[int]) -> TaskIdentity:
        if task_id is None:
            task_id = self._next_id
            while task_id in self._live_ids:
                task_id += 1
            self._next_id = task_id + 1
        elif task_id in self._live_ids:
            raise ValueError(
                f"task_id {task_id!r} is in use; remove the task before reusing it"
            )
        generation = self._generations.get(task_id, 0)
        self._generations[task_id] = generation + 1
        self._live_ids.add(task_id)
        return TaskIdentity(task_id=task_id, generation=generation)

    def get_identity(self, task_id: int) -> Optional[TaskIdentity]:
        """Get the *current* :class:`TaskIdentity` for a plain integer id.

        Returns ``None`` if no live task currently uses that id.  This is
        how callers must convert an ordinary integer id (for example one
        coming from an external queue) into the identity used to talk to
        the aggregator.  Compare identities, never integer ids, when
        matching snapshots.
        """
        with self._lock:
            for identity in list(self._parents.keys()) + list(self._children.keys()):
                if identity.task_id == task_id:
                    return identity
        return None

    def is_live(self, identity: TaskIdentity) -> bool:
        """Check whether ``identity`` still refers to a live task.

        An identity becomes stale when its task is removed, even if a new
        task later reuses the same integer id (it gets a new generation).
        """
        with self._lock:
            return identity in self._parents or identity in self._children

    # -------------------------------------------------------------- parents

    def add_parent(
        self, description: str = "", task_id: Optional[int] = None
    ) -> TaskIdentity:
        """Add an aggregated parent task.

        Args:
            description: Human readable description of the parent.
            task_id: Optional integer id to use. A fresh identity is minted
                either way; the id may only be reused after the previous
                task with that id was removed.

        Returns:
            TaskIdentity: The identity of the new parent.
        """
        with self._lock:
            identity = self._new_identity(task_id)
            self._parents[identity] = []
            self._parent_descriptions[identity] = description
            return identity

    def remove_parent(self, identity: TaskIdentity) -> None:
        """Remove a parent (and stop aggregating its children)."""
        with self._lock:
            child_ids = self._parents.pop(identity, [])
            self._parent_descriptions.pop(identity, None)
            self._live_ids.discard(identity.task_id)
            for child_id in child_ids:
                self._children.pop(child_id, None)
                self._live_ids.discard(child_id.task_id)

    # -------------------------------------------------------------- children

    def add_child(
        self,
        parent: TaskIdentity,
        description: str = "",
        *,
        weight: float = 1.0,
        total: Optional[float] = None,
        completed: float = 0.0,
        task_id: Optional[int] = None,
    ) -> TaskIdentity:
        """Add a child task to a parent.

        Args:
            parent: Identity of the parent returned by :meth:`add_parent`.
            description: Human readable description of the child.
            weight: Explicit aggregation weight. Must be > 0. Defaults to 1.
            total: Total number of steps, or ``None`` if unknown.
            completed: Steps already completed.
            task_id: Optional integer id to use (see :meth:`add_parent`).

        Returns:
            TaskIdentity: The identity of the new child.
        """
        if weight <= 0:
            raise ValueError("weight must be > 0")
        with self._lock:
            if parent not in self._parents:
                raise KeyError(f"unknown parent identity {parent}")
            identity = self._new_identity(task_id)
            ratio = _ratio(total, completed)
            finished = total is not None and total > 0 and float(completed) >= total
            child = _Child(
                identity=identity,
                description=description,
                weight=float(weight),
                status=(
                    TaskStatus.SUCCESS
                    if finished
                    else (
                        TaskStatus.INDETERMINATE
                        if total is None
                        else TaskStatus.RUNNING
                    )
                ),
                total=total,
                completed=float(completed),
                ratio=ratio,
                finished_ratio=1.0 if finished else None,
            )
            self._children[identity] = child
            self._parents[parent].append(identity)
            return identity

    def update_child(
        self,
        identity: TaskIdentity,
        *,
        total: Any = _UNSET,
        completed: Any = _UNSET,
        advance: Optional[float] = None,
        description: Optional[str] = None,
        weight: Optional[float] = None,
        status: Optional[TaskStatus] = None,
    ) -> None:
        """Update a child task.

        Pass ``total=None`` explicitly to mark a previously known total as
        unknown (omitting ``total`` leaves it untouched).  Use
        ``status=TaskStatus.SUCCESS`` / ``TaskStatus.FAILED`` to mark a
        terminal state; the child's final ratio is frozen at that point.
        """
        with self._lock:
            child = self._children.get(identity)
            if child is None:
                raise KeyError(f"unknown child identity {identity}")

            if description is not None:
                child.description = description
            if weight is not None:
                if weight <= 0:
                    raise ValueError("weight must be > 0")
                child.weight = float(weight)

            if total is not _UNSET:
                child.total = None if total is None else float(total)
            if completed is not _UNSET and completed is not None:
                child.completed = float(completed)
            if advance is not None:
                child.completed += float(advance)

            child.ratio = _ratio(child.total, child.completed)

            # An explicit status wins; otherwise derive active state from total.
            if status is not None:
                child.status = status
                if status.finished:
                    # Freeze the contribution at the terminal moment.
                    if child.finished_ratio is None:
                        child.finished_ratio = child.ratio
                    if status is TaskStatus.SUCCESS and child.finished_ratio is None:
                        child.finished_ratio = 1.0
            elif child.status.active:
                child.status = (
                    TaskStatus.INDETERMINATE
                    if child.total is None
                    else TaskStatus.RUNNING
                )

            # Auto-succeed once a known total is reached.
            if (
                child.status == TaskStatus.RUNNING
                and child.total is not None
                and child.total > 0
                and child.completed >= child.total
            ):
                child.status = TaskStatus.SUCCESS
                child.finished_ratio = 1.0

    def complete_child(self, identity: TaskIdentity) -> None:
        """Mark a child as successfully finished (freezes its contribution)."""
        self.update_child(identity, status=TaskStatus.SUCCESS)

    def fail_child(self, identity: TaskIdentity) -> None:
        """Mark a child as failed (the parent aggregate becomes failed)."""
        self.update_child(identity, status=TaskStatus.FAILED)

    def remove_child(self, parent: TaskIdentity, identity: TaskIdentity) -> None:
        """Remove a child from a parent.

        The child's :class:`TaskIdentity` becomes stale immediately.  Adding
        another task with the same integer id later mints a new generation,
        so snapshots taken before the removal never associate with the new
        task.
        """
        with self._lock:
            if parent not in self._parents:
                raise KeyError(f"unknown parent identity {parent}")
            children = self._parents[parent]
            if identity in children:
                children.remove(identity)
            self._children.pop(identity, None)
            self._live_ids.discard(identity.task_id)

    # ------------------------------------------------------------- snapshots

    def _child_snapshot(self, child: _Child) -> ChildSnapshot:
        ratio = child.finished_ratio if child.status.finished else child.ratio
        return ChildSnapshot(
            identity=child.identity,
            description=child.description,
            weight=child.weight,
            status=child.status,
            total=child.total,
            completed=child.completed,
            ratio=ratio,
        )

    def aggregate(self, parent: TaskIdentity) -> AggregateSnapshot:
        """Compute (and return an immutable snapshot of) a parent's state."""
        with self._lock:
            if parent not in self._parents:
                raise KeyError(f"unknown parent identity {parent}")
            child_records = [
                self._children[identity]
                for identity in self._parents[parent]
                if identity in self._children
            ]
            snapshots = [self._child_snapshot(child) for child in child_records]

            failed = any(child.status is TaskStatus.FAILED for child in child_records)
            active_indeterminate = any(
                child.status.active and child.total is None for child in child_records
            )

            weight_total = sum(child.weight for child in child_records)
            weighted = 0.0
            if weight_total > 0:
                for child in child_records:
                    ratio = (
                        child.finished_ratio if child.status.finished else child.ratio
                    )
                    if ratio is not None:
                        weighted += ratio * child.weight
                fraction = min(1.0, max(0.0, weighted / weight_total))
            else:
                fraction = 0.0

            all_success = bool(child_records) and all(
                child.status is TaskStatus.SUCCESS for child in child_records
            )

            if failed:
                status = AggregateStatus.FAILED
            elif all_success:
                status = AggregateStatus.SUCCESS
            elif active_indeterminate or not child_records:
                status = AggregateStatus.INDETERMINATE
            else:
                status = AggregateStatus.RUNNING

            display_fraction = (
                0.0 if status is AggregateStatus.INDETERMINATE else fraction
            )

            return AggregateSnapshot(
                identity=parent,
                description=self._parent_descriptions.get(parent, ""),
                status=status,
                fraction=display_fraction,
                percentage=display_fraction * 100.0,
                children=tuple(snapshots),
            )

    def snapshot_all(self) -> Dict[TaskIdentity, AggregateSnapshot]:
        """Return snapshots for every live parent."""
        with self._lock:
            return {parent: self.aggregate(parent) for parent in self._parents}
