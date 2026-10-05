"""Demonstrate the optional Table layout report.

The report lists each column's minimum, maximum, and final width, along with
the reason content wraps or truncates. It is produced from the same measurement
pass used to render the table, so custom renderables are not executed again.

Run with:
    python examples/table_layout_report.py
"""

import os
import sys

# Ensure the local Rich package is used when running from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table

# A fixed terminal width so the layout is deterministic.
console = Console(width=40, height=25, force_terminal=True, legacy_windows=False)

table = Table(title="中英文混合表", expand=False)
table.add_column("Name", no_wrap=True)
table.add_column("Description")
table.add_column("Qty", justify="right")

table.add_row("Alice", "一个中英文混合的描述内容", "12")
table.add_row("Bob", "short", "3")
table.add_row("Charlie", "这是另一个较长的描述，用于测试折行效果", "456")

# Generate the layout report. This runs the same layout calculation as
# rendering; custom renderables are not re-executed.
report = table.get_layout_report(console)

# Render the table normally.
console.print(table)
console.print()

# Print the report.
console.rule("布局报告 / Layout Report")
console.print(f"总宽度 Total width: {report.total_width} (terminal 40)")
console.print(f"边框宽度 Border width: {report.border_width}")
console.print(f"Padding 宽度: {report.padding_width}")
console.print()

header = f"{'列 Column':<10} {'最小 Min':>6} {'最大 Max':>6} {'最终 Final':>10} {'Padding':>8}  {'原因 Reason'}"
console.print(header)
console.print("-" * len(header))
for col in report.columns:
    console.print(
        f"{col.index:<10} {col.min_width:>6} {col.max_width:>6} "
        f"{col.final_width:>10} {col.padding_width:>8}  {col.reason}"
    )

console.print()
# Verify the total: sum of final column widths + borders must equal total.
column_sum = sum(col.final_width for col in report.columns)
assert column_sum + report.border_width == report.total_width
console.print(
    f"验证通过: 列宽总和 {column_sum} + 边框 {report.border_width} "
    f"= {report.total_width} (与渲染一致)"
)
