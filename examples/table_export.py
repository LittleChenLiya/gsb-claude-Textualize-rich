# encoding=utf-8
"""Export a Rich table to structured, JSON-serializable data.

Run with:

    python examples/table_export.py
"""

import json

from rich.console import Console
from rich.table import Table
from rich.text import Text


class CountingRenderable:
    """A renderable that counts how many times it has been rendered."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.render_count = 0

    def __rich_console__(self, console, options):
        self.render_count += 1
        yield self.text


console = Console()

counting = CountingRenderable("第一行\n第二行")

table = Table("名称", "数值", "备注", title="导出示例")
table.add_row(Text("你好", style="bold red"), "3.5", counting)
table.add_row("world", "42", Text("styled", style="green"))

console.print(table)

renders_before = counting.render_count
exported = table.export()
print()
print("JSON export:")
print(json.dumps(exported, ensure_ascii=False, indent=2))
print()
print(
    f"CountingRenderable rendered {counting.render_count - renders_before} time(s) "
    f"during export (total: {counting.render_count})"
)
