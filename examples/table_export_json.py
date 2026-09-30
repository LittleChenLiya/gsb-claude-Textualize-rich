"""Export a table as machine-readable JSON without parsing terminal output.

Run with::

    python examples/table_export_json.py

The original table is printed first, followed by its structured export.
Each cell is rendered only once, even when it is a stateful renderable.
"""

import json
import os
import sys

# Allow running this example directly from a source checkout.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.control import Control
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class CountingRenderable:
    """A renderable that records how many times it is rendered."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.render_count = 0

    def __rich_console__(self, console, options):
        self.render_count += 1
        yield Text(f"{self.label}（第{self.render_count}次渲染）", style="bold green")
        yield Control.bell()  # Control codes must not appear in the export.


console = Console()

counting_cell = CountingRenderable("自定义单元格")
table = Table("姓名", "描述", "年龄", title="结构化导出示例")
table.add_row(Text("张三", style="bold red"), "第一行内容\n第二行内容", 42)
table.add_row("李四", counting_cell, 3.5)
table.add_row("王五", None, None)

console.rule("原始表格")
console.print(table)
render_count_after_display = counting_cell.render_count

data = table.export_data(console=console)
console.rule("JSON 结构化结果")
console.print_json(json.dumps(data, ensure_ascii=False))

console.print(
    Panel(
        f"自定义单元格导出值：{data['rows'][1]['cells'][1]['text']}\n"
        f"显示表格后渲染次数：{render_count_after_display}\n"
        f"再导出一次后的渲染次数：{counting_cell.render_count}（导出只增加 1 次）",
        title="调用次数校验",
    )
)
