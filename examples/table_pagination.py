"""Demonstrates Table.paginate: terminal-height paging for long tables.

Run with:

    python -m examples.table_pagination

It renders a table (Chinese text, combining characters, a hyperlink, and a
cell spanning three pages) at width 32 / page height 12, then shows the
error raised when the page height is too small.
"""

from rich import errors
from rich.console import Console
from rich.table import Table
from rich.text import Text

WIDTH = 32
PAGE_HEIGHT = 12


def build_table() -> Table:
    table = Table(title="分页演示 Demo")
    table.add_column("名称")
    table.add_column("说明", overflow="fold")
    table.add_row("中文标题", "cafe\u0301 组合字符")
    table.add_row("链接", Text("example 链接", style="link https://example.com"))
    for index in range(6):
        table.add_row(f"行{index}", "短行")
    long_text = "很长的单元格内容，用来测试跨页拆分。" * 12
    table.add_row("长行", Text(long_text))
    table.add_row("结尾", "最后一行")
    return table


def main() -> None:
    console = Console(width=WIDTH)
    table = build_table()

    console.print("[bold]1. Normal paging with continuation of an oversized row[/]")
    pages = table.paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    for page in pages:
        console.print(page, end="")
        console.print(f"[dim]----- end of page {page.page_number} -----[/]")

    console.print("[bold]2. Page height too small[/]")
    try:
        table.paginate(console, width=WIDTH, page_height=5)
    except errors.PaginationError as error:
        console.print(f"[red]PaginationError:[/] {error}")


if __name__ == "__main__":
    main()
