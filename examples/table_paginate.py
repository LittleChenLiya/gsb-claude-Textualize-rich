"""Demonstrate paginating a long table to fit a terminal height.

Run with:
    python examples/table_paginate.py
"""
from rich import errors
from rich.console import Console
from rich.table import Table
from rich.text import Text

WIDTH = 32
PAGE_HEIGHT = 12


def build_table() -> Table:
    table = Table(title="""分页演示""", caption="""end of table""", show_footer=True)
    table.add_column("""名称""", footer="""footer""")
    table.add_column("""说明""", footer="""footer""")
    table.add_row("""caf\u00e9""", Text("""组合字符 e\u0301 与中文""", style="""bold"""))
    table.add_row(
        """链接""", Text("""Rich 主页""", style="""link https://github.com/Textualize/rich""")
    )
    # A single cell that wraps to more than three pages of lines.
    table.add_row("""长行""", """ """.join(f"""wide{i}中文""" for i in range(40)))
    for index in range(1, 8):
        table.add_row(f"""行{index}""", f"""内容 {index} 中文""")
    return table


def main() -> None:
    console = Console(width=WIDTH)
    table = build_table()

    console.rule("""[bold]分页输出 (32x12)""")
    pages = table.paginate(console, WIDTH, PAGE_HEIGHT)
    for page in pages:
        marker = """ [yellow](续行)[/]""" if page.continued else """"""
        console.rule(f"""第 {page.page_number}/{page.page_count} 页{marker}""")
        console.print(page, end="""""")
    console.rule()

    console.rule("""[bold]高度过小的错误""")
    try:
        build_table().paginate(console, WIDTH, 3)
    except errors.PaginationError as error:
        console.print(f"""[red]PaginationError:[/] {error}""")


if __name__ == """__main__""":
    main()
