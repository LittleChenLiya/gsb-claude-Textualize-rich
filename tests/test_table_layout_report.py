# encoding=utf-8

import io

from rich.console import Console
from rich.cells import cell_len
from rich.measure import Measurement
from rich.segment import Segment
from rich.table import ColumnLayout, Table, TableLayoutReport


def make_console(width=40):
    return Console(
        width=width,
        file=io.StringIO(),
        force_terminal=False,
        legacy_windows=False,
        _environ={},
    )


def make_table(**kwargs):
    """A mixed Chinese/English table."""
    table = Table("Name 名称", "Description 描述", **kwargs)
    table.add_row("苹果 apple", "一种常见的水果 a common fruit")
    table.add_row("banana 香蕉", "yellow tropical fruit 黄色热带水果")
    return table


class CountingRenderable:
    """A renderable that counts how often it is measured and rendered."""

    def __init__(self, text="hello"):
        self.text = text
        self.render_count = 0
        self.measure_count = 0

    def __rich_console__(self, console, options):
        self.render_count += 1
        yield Segment(self.text)

    def __rich_measure__(self, console, options):
        self.measure_count += 1
        return Measurement(len(self.text), len(self.text))


def test_layout_report_disabled_by_default():
    console = make_console()
    table = make_table()
    console.print(table)
    assert table.layout_report is None


def test_layout_report_widths_sum_with_cjk():
    """Final column widths (incl. padding) plus borders add up to the table width."""
    console = make_console(width=40)
    table = make_table(layout_report=True)
    console.print(table)
    report = table.layout_report
    assert isinstance(report, TableLayoutReport)
    assert all(isinstance(column, ColumnLayout) for column in report.columns)
    assert len(report.columns) == 2
    # widths are consistent
    assert report.content_width == sum(column.width for column in report.columns)
    assert report.table_width == report.content_width + report.border_width
    assert report.table_width <= 40
    # min <= width <= max for each column
    for column in report.columns:
        assert column.minimum <= column.width <= column.maximum
    # every rendered line spans exactly the reported table width
    lines = console.file.getvalue().splitlines()
    assert lines
    for line in lines:
        assert cell_len(line) == report.table_width


def test_layout_report_padding_and_borders_counted():
    """Padding is included in column widths; borders are reported separately."""
    console = make_console(width=30)
    table = Table("a", "b", padding=(0, 2), layout_report=True)
    table.add_row("xy", "z")
    console.print(table)
    report = table.layout_report
    # 2 columns * (left 2 + right 2) padding
    assert report.padding_width == 8
    # 2 edge borders + 1 divider
    assert report.border_width == 3
    # column widths include padding: "xy" + 4 padding
    assert report.columns[0].maximum == 2 + 4
    assert report.columns[1].maximum == 1 + 4
    assert report.table_width == report.content_width + report.border_width


def test_layout_report_same_layout_as_normal_render():
    """Enabling the report must not change the rendered output."""
    plain_console = make_console(width=36)
    plain_table = make_table()
    plain_console.print(plain_table)

    report_console = make_console(width=36)
    report_table = make_table(layout_report=True)
    report_console.print(report_table)

    assert report_console.file.getvalue() == plain_console.file.getvalue()
    # widths agree with the un-reported render
    report = report_table.layout_report
    assert report.table_width == 36


def test_layout_report_does_not_measure_or_render_extra_times():
    """A counting renderable is called the same number of times with/without the report."""
    counts = []
    for layout_report in (False, True):
        console = make_console(width=24)  # narrow, to force width collapsing
        renderables = [CountingRenderable("foo bar baz") for _ in range(3)]
        table = Table("one", "two", "three", layout_report=layout_report)
        table.add_row(*renderables)
        table.add_row("some quite long text here", "and more text", "even more")
        console.print(table)
        counts.append(
            (
                [r.render_count for r in renderables],
                [r.measure_count for r in renderables],
            )
        )
    assert counts[0] == counts[1]
    # sanity: the renderables were actually exercised
    assert all(count == 1 for count in counts[1][0])


def test_layout_report_wrap_reason():
    console = make_console(width=40)
    table = make_table(layout_report=True)
    console.print(table)
    report = table.layout_report
    wrapped_columns = [column for column in report.columns if column.wrapped]
    assert wrapped_columns, "expected at least one wrapped column"
    reasons = "\n".join(wrapped_columns[0].reasons)
    assert "wrapped into" in reasons
    assert "exceeds final width" in reasons


def test_layout_report_ellipsis_reason():
    console = make_console(width=20)
    table = Table(layout_report=True)
    table.add_column("Col", no_wrap=True, overflow="ellipsis")
    table.add_row("a very long piece of text that will not fit")
    console.print(table)
    report = table.layout_report
    column = report.columns[0]
    assert column.truncated
    assert any("ellipsis" in reason for reason in column.reasons)
    assert any("no_wrap" in reason for reason in column.reasons)


def test_layout_report_stores_no_cell_text():
    secret = "xyzzy-plugh-secret"
    console = make_console(width=30)
    table = Table("header-qux", layout_report=True)
    table.add_row(secret)
    console.print(table)
    report = table.layout_report
    report_text = str(report) + repr(report) + "\n".join(
        reason for column in report.columns for reason in column.reasons
    )
    assert secret not in report_text
    assert "header-qux" not in report_text


def test_layout_report_is_renderable():
    console = make_console(width=60)
    table = make_table(layout_report=True)
    console.print(table)
    report_console = make_console(width=60)
    report_console.print(table.layout_report)
    output = report_console.file.getvalue()
    assert "Table layout report" in output
    for line in output.splitlines():
        assert cell_len(line) <= 60


def test_layout_report_str():
    console = make_console(width=40)
    table = make_table(layout_report=True)
    console.print(table)
    report_str = str(table.layout_report)
    assert "table_width=40" in report_str
    assert "column 0: min=" in report_str
    assert "column 1: min=" in report_str


def test_layout_report_ellipsis_without_no_wrap():
    """A single unbreakable word is ellipsized (not wrapped) with default overflow."""
    console = make_console(width=24)
    table = Table("h", layout_report=True)
    table.add_row("x" * 40)
    console.print(table)
    column = table.layout_report.columns[0]
    assert column.truncated
    assert not column.wrapped
    assert any("overflow='ellipsis'" in reason for reason in column.reasons)


def test_layout_report_fold_overflow_wraps():
    """With overflow='fold' a long unbreakable word is folded on to new lines."""
    console = make_console(width=24)
    table = Table("h", layout_report=True)
    table.columns[0].overflow = "fold"
    table.add_row("x" * 40)
    console.print(table)
    column = table.layout_report.columns[0]
    assert column.wrapped
    assert not column.truncated
