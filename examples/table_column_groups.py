# encoding=utf-8
"""Demonstrates nested column group headers in :class:`rich.table.Table`.

Run with::

    python examples/table_column_groups.py

Prints grouped tables at width 80 and 32, a nested group example, and then
shows how invalid group definitions are reported before rendering.
"""

from rich import errors
from rich.console import Console
from rich.table import ColumnGroup, Table


def build_local_remote_table() -> Table:
    table = Table(title="任务执行结果")
    for header in ["成功", "失败", "成功", "失败"]:
        table.add_column(header)
    table.add_column_group("本地", columns=[0, 1])
    table.add_column_group("远端", columns=[2, 3])
    table.add_row("alpha", "beta", "gamma", "delta")
    table.add_row("epsilon", "zeta", "eta", "theta")
    return table


def build_nested_table() -> Table:
    table = Table()
    for header in ["甲", "乙", "丙", "丁"]:
        table.add_column(header)
    table.add_column_group(
        "总计",
        children=[
            ColumnGroup("上半", columns=[0, 1]),
            ColumnGroup("下半", columns=[2, 3]),
        ],
    )
    table.add_row("1", "2", "3", "4")
    return table


def show_invalid_groups(console: Console) -> None:
    def build_empty() -> Table:
        table = Table()
        table.add_column("a")
        table.add_column_group("空组")
        return table

    def build_out_of_range() -> Table:
        table = Table()
        table.add_column("a")
        table.add_column_group("越界", columns=[0, 5])
        return table

    def build_overlapping() -> Table:
        table = Table()
        for header in ["a", "b", "c"]:
            table.add_column(header)
        table.add_column_group("组一", columns=[0, 1])
        table.add_column_group("组二", columns=[1, 2])
        return table

    def build_crossing() -> Table:
        table = Table()
        for header in ["a", "b", "c"]:
            table.add_column(header)
        table.add_column_group("交叉", columns=[0, 2])
        return table

    for label, build in [
        ("空组 (empty group)", build_empty),
        ("越界 (out of range)", build_out_of_range),
        ("重复覆盖 (overlapping groups)", build_overlapping),
        ("交叉跨度 (non-consecutive span)", build_crossing),
    ]:
        table = build()
        table.add_row("1", "2", "3")
        try:
            console.print(table)
        except errors.ColumnGroupError as error:
            console.print(f"[red]ColumnGroupError[/] ({label}): {error}")


def main() -> None:
    console = Console()
    for width in (80, 32):
        console.rule(f"本地/远端分组, width={width}")
        console.print(build_local_remote_table(), width=width)
    console.rule("嵌套分组 (nested groups)")
    console.print(build_nested_table())
    console.rule("非法分组 (invalid groups)")
    show_invalid_groups(console)


if __name__ == "__main__":
    main()
