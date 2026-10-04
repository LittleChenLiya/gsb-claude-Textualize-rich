.. _progress_aggregate:

Weighted progress aggregation
=============================

The :class:`~rich.progress_aggregate.AggregatedProgress` layer computes a
parent task's progress from the weighted completion *ratios* of child tasks.
It is an independent layer on top of :class:`~rich.progress.Progress`: the
aggregation result is a plain state object, and the existing Progress display
renders it like any other task.

Tasks with different totals are never added together directly. A 4-step task
and a 1000-step task contribute in proportion to their explicit weights.

Aggregation rules
-----------------

1. **Weighted ratios.** For children with weights ``w_i`` and ratios
   ``r_i`` (``completed / total``, clamped to ``[0, 1]``) the parent ratio is
   ``sum(w_i * r_i) / sum(w_i)``.
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

Basic usage
-----------

Create a :class:`~rich.progress.Progress` with a parent task, then wrap it
with :class:`~rich.progress_aggregate.AggregatedProgress` and register child
tasks with explicit weights::

    from rich.progress import Progress, BarColumn, TaskProgressColumn, TextColumn
    from rich.progress_aggregate import (
        AggregateStatusColumn,
        AggregatedProgress,
    )

    progress = Progress(
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        AggregateStatusColumn(),
    )

    with progress:
        parent = progress.add_task("Parent", total=100)
        agg = AggregatedProgress(progress, parent)
        a = agg.add_child_task("Child A (weight 1)", total=4, weight=1)
        b = agg.add_child_task("Child B (weight 3)", total=4, weight=3)
        ta, tb = agg.task_id(a), agg.task_id(b)

        progress.update(ta, completed=4)   # 100% of A
        agg.sync()                           # parent -> 25%

        progress.update(tb, completed=2)     # 50% of B
        agg.sync()                           # parent -> 62.5%

        # Make B's total unknown -> parent is indeterminate (pulse).
        progress._tasks[tb].total = None
        agg.sync()

Call :meth:`~rich.progress_aggregate.AggregatedProgress.state` to get the
pure :class:`~rich.progress_aggregate.AggregateState` without touching the
display, or :meth:`~rich.progress_aggregate.AggregatedProgress.sync` to push
the state into the parent task.

See ``examples/aggregate_progress.py`` in the repository for a short terminal
demo.
