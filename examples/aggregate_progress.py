"""Weighted parent-child progress aggregation demo.

Shows the three aggregate states:

1. weights 1:3, children 100% / 0%  -> parent 25%
2. second child at 50%              -> parent 62.5%
3. second child total unknown       -> parent indeterminate (pulsing bar)

Run from the repository root:

    python examples/aggregate_progress.py
"""

import os
import sys
import time

# Make the worktree-local rich importable when run as a script
# (python examples/aggregate_progress.py from the repository root).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.progress_aggregate import AggregatedProgress, AggregateStatusColumn

RULES = """\
Aggregation rules:
  1. Parent progress = weighted completion ratios (completed/total); tasks
     with different totals are never summed directly.
  2. Any active child with unknown total -> parent is indeterminate (pulse).
  3. Finished children keep their final contribution (snapshot).
  4. A failed child makes the parent show FAILURE, never auto-complete.
  5. Child identity is separate from TaskID: removing a task or reusing its
     TaskID can never associate an old snapshot with a new task."""


def main() -> None:
    console = Console()
    console.print(RULES)
    console.print()

    progress = Progress(
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        AggregateStatusColumn(),
        console=console,
    )

    with progress:
        parent = progress.add_task("Parent (weighted aggregate)", total=100)
        agg = AggregatedProgress(progress, parent)
        a = agg.add_child_task("Child A (weight 1)", total=4, weight=1)
        b = agg.add_child_task("Child B (weight 3)", total=4, weight=3)
        ta, tb = agg.task_id(a), agg.task_id(b)

        # State 1: A=100%, B=0% -> 25%
        progress.update(ta, completed=4)
        state = agg.sync()
        console.print(
            f"State 1: A=100%, B=0%  -> parent {state.completed:.1f}% "
            "(expected 25.0%)"
        )
        time.sleep(1.5)

        # State 2: B=50% -> 62.5%
        progress.update(tb, completed=2)
        state = agg.sync()
        console.print(
            f"State 2: A=100%, B=50% -> parent {state.completed:.1f}% "
            "(expected 62.5%)"
        )
        time.sleep(1.5)

        # State 3: B total unknown -> indeterminate (pulse)
        # rich's update() treats total=None as "no change", so set the total
        # directly on the task object to make it unknown.
        progress._tasks[tb].total = None
        state = agg.sync()
        console.print(
            f"State 3: B total unknown -> indeterminate={state.indeterminate} "
            "(bar pulses)"
        )
        time.sleep(1.5)

    console.print()
    console.print("Pure state object (separate from rendering):")
    console.print(state)


if __name__ == "__main__":
    main()
