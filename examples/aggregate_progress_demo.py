"""Short terminal demo for the independent parent/child aggregation layer.

Run as ``python examples/aggregate_progress_demo.py``.

It prints three aggregate states, rendered with a normal Rich ``Progress``:

1. child A (weight 1) at 100%, child B (weight 3) at 0%  -> parent 25%
2. child B at 50%                                         -> parent 62.5%
3. child B loses its known total                          -> parent indeterminate
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.aggregate_progress import AggregateProgress
from rich.console import Console
from rich.panel import Panel
from rich.progress_aggregate import AggregateStatus, ProgressAggregator
from rich.rule import Rule


def main() -> None:
    console = Console(width=72)
    aggregator = ProgressAggregator()
    ap = AggregateProgress(aggregator, console=console, auto_refresh=False)

    parent = aggregator.add_parent("parent task")
    a = aggregator.add_child(parent, "A (weight 1)", weight=1, total=4, completed=4)
    b = aggregator.add_child(parent, "B (weight 3)", weight=3, total=8, completed=0)

    steps = [
        ("1. A done (100%), B at 0%", None, 0),
        ("2. B advances to 50%", 8, 4),
        ("3. B total becomes unknown", None, 4),
    ]

    for title, total, completed in steps:
        if total is None and completed == 0:
            aggregator.update_child(b, total=8, completed=0)
        elif total is None:
            aggregator.update_child(b, total=None)
        else:
            aggregator.update_child(b, total=total, completed=completed)
        snapshot = aggregator.aggregate(parent)
        ap.sync()

        if snapshot.status is AggregateStatus.INDETERMINATE:
            value = "indeterminate (unknown total)"
        else:
            value = f"{snapshot.percentage:.1f}%"
        console.print(Rule(title))
        console.print(
            f"state output : status={snapshot.status.value}, percentage={value}"
        )
        console.print("rich render  :")
        console.print(ap.progress)
        console.print()

    aggregator.complete_child(a)
    console.print(
        Panel(
            "rule: parent = sum(child_ratio * weight) / sum(weight); "
            "different totals are never added together.\n"
            "unknown active total -> indeterminate; any failed child -> FAILED.",
            title="aggregation rules",
        )
    )


if __name__ == "__main__":
    main()
