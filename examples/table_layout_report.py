# encoding=utf-8
"""Demonstration of the optional Table layout report.

Render a mixed Chinese/English table at a fixed width, then print the
recorded layout report: per-column minimum, maximum and final widths
(including padding), the width taken by borders, and the actual reasons
for any wrapping or ellipsis.

Run with:

    python examples/table_layout_report.py
"""

from rich.console import Console
from rich.table import Table


def main() -> None:
    console = Console(width=48)

    table = Table(
        "City 城市",
        "Note 备注",
        title="Layout report demo",
        caption="rendered at width 48",
        layout_report=True,  # record the layout report during rendering
    )
    table.add_row("北京 Beijing", "中国的首都 the capital of China")
    table.add_row("上海 Shanghai", "最大的城市 the largest city")
    table.add_row("深圳 Shenzhen", "科技中心 a technology hub")

    console.print(table)

    report = table.layout_report
    assert report is not None

    # Plain-text summary (also usable in logs)
    console.print()
    console.print(str(report))
    console.print()

    # The report itself is renderable
    console.print(report)

    # Sanity: content widths + borders add up to the rendered table width
    assert report.content_width + report.border_width == report.table_width


if __name__ == "__main__":
    main()
