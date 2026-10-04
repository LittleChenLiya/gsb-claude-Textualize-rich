"""Render aggregated parent/child progress with a regular Rich Progress.

This is the *rendering* layer.  All state lives in
:class:`rich.progress_aggregate.ProgressAggregator`; this module only mirrors
:class:`~rich.progress_aggregate.AggregateSnapshot` values onto an ordinary
:class:`~rich.progress.Progress` instance, so every existing Progress column
(bar, percentage, ETA, ...) keeps working with aggregated tasks.

Mapping snapshot state onto Progress tasks
------------------------------------------

============================  =================================================
AggregateStatus               Progress task
============================  =================================================
``RUNNING``                   ``total=100``, ``completed=fraction * 100``
``SUCCESS``                   ``total=100``, ``completed=100`` (finished)
``FAILED``                    ``total=100``, bar kept *unfinished* and a red
                              ``FAILED`` marker shown (it never auto-completes)
``INDETERMINATE``             ``total=None`` (pulsing bar / unknown percentage)
============================  =================================================
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union

from .progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from .progress_aggregate import (
    AggregateSnapshot,
    AggregateStatus,
    ChildSnapshot,
    ProgressAggregator,
    TaskIdentity,
    TaskStatus,
)
from .text import Text

if TYPE_CHECKING:
    from .console import Console

_STATUS_TEXT = {
    AggregateStatus.INDETERMINATE: "INDETERMINATE",
    AggregateStatus.RUNNING: "RUNNING",
    AggregateStatus.SUCCESS: "SUCCESS",
    AggregateStatus.FAILED: "FAILED",
}

_STATUS_STYLE = {
    "INDETERMINATE": "yellow",
    "RUNNING": "cyan",
    "SUCCESS": "green",
    "FAILED": "bold red",
}


class AggregateStatusColumn(ProgressColumn):
    """Render the aggregate status (FAILED / SUCCESS / ...) of a task."""

    def render(self, task: Any) -> Text:
        status = task.fields.get("aggregate_status", "")
        if not status:
            return Text("")
        return Text(status, style=_STATUS_STYLE.get(status, ""))


def _force_total_none(progress: Progress, task_id: TaskID) -> None:
    """Set ``total`` to ``None`` on a Progress task.

    ``Progress.update`` treats ``total=None`` as "leave unchanged", so the
    internal task object is adjusted directly (and its speed samples reset).
    """
    task = progress._tasks[task_id]
    if task.total is not None:
        task.total = None
        task._reset()


class AggregateProgress:
    """Display a :class:`ProgressAggregator` with an existing-style Progress.

    Example:
        ```python
        from rich.aggregate_progress import AggregateProgress

        aggregator = ProgressAggregator()
        with AggregateProgress(aggregator) as ap:
            parent = aggregator.add_parent("Overall")
            child = aggregator.add_child(parent, "work", weight=2, total=100)
            aggregator.update_child(child, advance=50)
            ap.refresh()
        ```

    Args:
        aggregator (ProgressAggregator, optional): The state layer. A new one
            is created if omitted.
        *columns: Progress columns; defaults to description, bar, percentage
            and the aggregate status column.
        console (Console, optional): Console forwarded to Progress.
        show_children (bool): Also render one indented row per child.
        **kwargs: Extra keyword arguments forwarded to :class:`Progress`.
    """

    def __init__(
        self,
        aggregator: Optional[ProgressAggregator] = None,
        *columns: Union[str, ProgressColumn],
        console: Optional["Console"] = None,
        show_children: bool = False,
        **kwargs: Any,
    ) -> None:
        self.aggregator = aggregator or ProgressAggregator()
        self.show_children = show_children
        columns = columns or (
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            AggregateStatusColumn(),
        )
        self.progress = Progress(*columns, console=console, **kwargs)
        self._parent_tasks: Dict[TaskIdentity, TaskID] = {}
        self._child_tasks: Dict[TaskIdentity, TaskID] = {}

    # ------------------------------------------------------------- lifecycle

    @property
    def console(self) -> "Console":
        """The console used by the underlying Progress display."""
        return self.progress.console

    def start(self) -> None:
        """Start the progress display."""
        self.progress.start()

    def stop(self) -> None:
        """Stop the progress display."""
        self.progress.stop()

    def __enter__(self) -> "AggregateProgress":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.stop()

    def __rich__(self) -> object:
        """Render the current aggregated state."""
        self.sync()
        return self.progress.get_renderable()

    @property
    def finished(self) -> bool:
        """bool: Whether every parent has reached a terminal state."""
        snapshots = self.aggregator.snapshot_all()
        return bool(snapshots) and all(
            snapshot.finished for snapshot in snapshots.values()
        )

    # ------------------------------------------------------------ rendering

    def _parent_task_id(self, snapshot: AggregateSnapshot) -> TaskID:
        task_id = self._parent_tasks.get(snapshot.identity)
        if task_id is None:
            task_id = self.progress.add_task(
                snapshot.description, total=100, aggregate_status=""
            )
            self._parent_tasks[snapshot.identity] = task_id
        return task_id

    def _child_task_id(self, snapshot: ChildSnapshot) -> TaskID:
        task_id = self._child_tasks.get(snapshot.identity)
        if task_id is None:
            task_id = self.progress.add_task(
                f"  - {snapshot.description}", total=100, aggregate_status=""
            )
            self._child_tasks[snapshot.identity] = task_id
        return task_id

    def _sync_snapshot(
        self,
        task_id: TaskID,
        description: str,
        status: AggregateStatus,
        fraction: float,
    ) -> None:
        marker = _STATUS_TEXT[status]
        self.progress.update(
            task_id,
            description=description,
            completed=fraction * 100.0,
            aggregate_status=marker,
        )
        task = self.progress._tasks[task_id]
        if status is AggregateStatus.INDETERMINATE:
            # Unknown total: pulsing bar, no percentage.
            _force_total_none(self.progress, task_id)
            task.finished_time = None
        else:
            task.total = 100.0
            if status is AggregateStatus.FAILED:
                # A failed parent must never display as a finished bar.
                task.finished_time = None

    def sync(self) -> None:
        """Mirror every live aggregate snapshot onto Progress tasks."""
        with self.progress._lock:
            snapshots: List[AggregateSnapshot] = list(
                self.aggregator.snapshot_all().values()
            )
            live_parents = {snapshot.identity for snapshot in snapshots}
            live_children = set()

            for snapshot in snapshots:
                task_id = self._parent_task_id(snapshot)
                self._sync_snapshot(
                    task_id,
                    snapshot.description,
                    snapshot.status,
                    snapshot.fraction,
                )
                if self.show_children:
                    for child in snapshot.children:
                        live_children.add(child.identity)
                        child_task_id = self._child_task_id(child)
                        child_status = self._child_aggregate_status(child)
                        fraction = child.ratio if child.ratio is not None else 0.0
                        self._sync_snapshot(
                            child_task_id,
                            f"  - {child.description}",
                            child_status,
                            fraction,
                        )

            for identity, task_id in list(self._parent_tasks.items()):
                if identity not in live_parents and task_id in self.progress._tasks:
                    self.progress.remove_task(task_id)
                    del self._parent_tasks[identity]
            for identity, task_id in list(self._child_tasks.items()):
                if identity not in live_children and task_id in self.progress._tasks:
                    self.progress.remove_task(task_id)
                    del self._child_tasks[identity]

    @staticmethod
    def _child_aggregate_status(child: ChildSnapshot) -> AggregateStatus:
        return {
            TaskStatus.PENDING: AggregateStatus.INDETERMINATE,
            TaskStatus.RUNNING: AggregateStatus.RUNNING,
            TaskStatus.INDETERMINATE: AggregateStatus.INDETERMINATE,
            TaskStatus.SUCCESS: AggregateStatus.SUCCESS,
            TaskStatus.FAILED: AggregateStatus.FAILED,
        }[child.status]

    def refresh(self) -> None:
        """Recompute aggregate state and refresh the display."""
        self.sync()
        self.progress.refresh()
