"""Demonstration of the standalone frame differencing component.

For three small examples (a double-width character replaced by two narrow
characters, a shortened line, and a color-only change) this script prints
the frame before and after, plus the structured diff plan, and verifies the
plan on a SimulatedTerminal -- no real terminal required.

Run with: python examples/frame_diff_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.frame_diff import SimulatedTerminal, diff_frames
from rich.segment import Segment, SegmentLines
from rich.style import Style

console = Console()


def show_example(title, old_lines, new_lines):
    console.rule(title)
    console.print("[bold]Before:[/]")
    console.print(SegmentLines(old_lines, new_lines=True))
    plan = diff_frames(old_lines, new_lines)
    console.print("[bold]Plan:[/]")
    for operation in plan.operations:
        console.print(f"  {operation!r}")
    terminal = SimulatedTerminal.from_lines(old_lines)
    terminal.apply(plan)
    console.print("[bold]After (simulated terminal):[/]")
    console.print(SegmentLines(terminal.to_lines(), new_lines=True))
    assert terminal.matches(new_lines), "plan did not reproduce the new frame!"
    console.print("[green]Plan verified against the new frame.[/]")


def main():
    show_example(
        "Double-width character replaced by two narrow characters",
        [[Segment("模式:中")]],
        [[Segment("模式:en")]],
    )
    show_example(
        "A shortened line (tail residue is cleared)",
        [[Segment("hello world")], [Segment("-----------")]],
        [[Segment("hello")], [Segment("-----------")]],
    )
    show_example(
        "Color-only change",
        [[Segment("status: OK", Style(color="red", bold=True))]],
        [[Segment("status: OK", Style(color="green", bold=True))]],
    )


if __name__ == "__main__":
    main()
