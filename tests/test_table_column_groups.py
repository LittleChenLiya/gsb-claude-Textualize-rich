# encoding=utf-8

import io
import re

import pytest

from rich import box, errors
from rich.cells import cell_len
from rich.console import Console
from rich.measure import Measurement
from rich.table import ColumnGroup, Table


def make_console(width=80, color_system=None):
    return Console(
        width=width,
        force_terminal=True,
        file=io.StringIO(),
        legacy_windows=False,
        color_system=color_system,
        _environ={},
    )


def render(table, width=80, color_system=None):
    console = make_console(width, color_system=color_system)
    console.print(table)
    return console.file.getvalue()


def build_local_remote_table():
    table = Table()
    for header in ["成功", "失败", "成功", "失败"]:
        table.add_column(header)
    table.add_column_group("本地", columns=[0, 1])
    table.add_column_group("远端", columns=[2, 3])
    table.add_row("alpha", "beta", "gamma", "delta")
    table.add_row("epsilon", "zeta", "eta", "theta")
    return table


def border_columns(line):
    """Visual column positions of vertical border characters in a line."""
    return {cell_len(line[:index]) for index, char in enumerate(line) if char in "┃│"}


def assert_lines_within_width(text, width):
    for line in text.splitlines():
        assert cell_len(line) <= width, f"line exceeds width {width}: {line!r}"


def assert_group_boundaries_align(text):
    """Borders in group rows must align with borders of the leaf header row."""
    lines = [line for line in text.splitlines() if line]
    header_row = next(line for line in lines if "成功" in line)
    header_borders = border_columns(header_row)
    for line in lines:
        assert (
            border_columns(line) <= header_borders
            or border_columns(line) == header_borders
        )
    data_rows = [line for line in lines if line.startswith("│")]
    assert data_rows, "expected data rows to be rendered"
    for line in data_rows:
        assert border_columns(line) == header_borders


EXPECTED_WIDTH_80 = """\
┏━━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━┓
┃      本地      ┃     远端      ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
┃ 成功    ┃ 失败 ┃ 成功  ┃ 失败  ┃
┡━━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━┩
│ alpha   │ beta │ gamma │ delta │
│ epsilon │ zeta │ eta   │ theta │
└─────────┴──────┴───────┴───────┘
"""

EXPECTED_WIDTH_32 = """\
┏━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━┓
┃     本地     ┃     远端      ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
┃ 成功  ┃ 失败 ┃ 成功  ┃ 失败  ┃
┡━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━┩
│ alpha │ beta │ gamma │ delta │
│ epsi… │ zeta │ eta   │ theta │
└───────┴──────┴───────┴───────┘
"""

EXPECTED_NESTED = """\
┏━━━━┳━━━━┳━━━━┳━━━━┓
┃       总计        ┃
┡━━━━━━━━━━━━━━━━━━━┩
┃  上半   ┃  下半   ┃
┡━━━━━━━━━╇━━━━━━━━━┩
┃ 甲 ┃ 乙 ┃ 丙 ┃ 丁 ┃
┡━━━━╇━━━━╇━━━━╇━━━━┩
│ 1  │ 2  │ 3  │ 4  │
└────┴────┴────┴────┘
"""

EXPECTED_NO_BOX = """\
    本地        远端    
 成功  失败  成功  失败 
 1     2     3     4    
"""

EXPECTED_COMBINING = """\
┏━━━━━━┳━━━━━━━━┓
┃  组合字符é组  ┃
┡━━━━━━━━━━━━━━━┩
┃ café ┃ 中文列 ┃
┡━━━━━━╇━━━━━━━━┩
│ a    │ b      │
└──────┴────────┘
"""

EXPECTED_PLAIN_TABLE = """\
┏━━━━━┳━━━━━┓
┃ foo ┃ bar ┃
┡━━━━━╇━━━━━┩
│ 1   │ 2   │
└─────┴─────┘
"""


def test_local_remote_groups_width_80():
    output = render(build_local_remote_table(), 80)
    assert output == EXPECTED_WIDTH_80
    assert_lines_within_width(output, 80)
    assert_group_boundaries_align(output)


def test_local_remote_groups_width_32():
    output = render(build_local_remote_table(), 32)
    assert output == EXPECTED_WIDTH_32
    assert_lines_within_width(output, 32)
    assert_group_boundaries_align(output)


def test_cjk_and_combining_characters_alignment():
    table = Table()
    table.add_column("café")  # e followed by a combining acute accent
    table.add_column("中文列")
    table.add_column_group("组合字符é组", columns=[0, 1])
    table.add_row("a", "b")
    output = render(table, 40)
    assert output == EXPECTED_COMBINING
    lines = [line for line in output.splitlines() if line]
    widths = {cell_len(line) for line in lines}
    assert len(widths) == 1  # every row has the same visible width
    header_borders = border_columns(lines[3])
    for line in lines:
        assert border_columns(line) <= header_borders


def test_nested_groups():
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
    output = render(table, 40)
    assert output == EXPECTED_NESTED
    assert_lines_within_width(output, 40)


def test_groups_without_box():
    table = Table(box=None)
    for header in ["成功", "失败", "成功", "失败"]:
        table.add_column(header)
    table.add_column_group("本地", columns=[0, 1])
    table.add_column_group("远端", columns=[2, 3])
    table.add_row("1", "2", "3", "4")
    output = render(table, 40)
    assert output == EXPECTED_NO_BOX


def test_group_style_spans_full_width():
    table = Table()
    table.add_column("a")
    table.add_column("b")
    table.add_column_group("grp", columns=[0, 1], style="red")
    table.add_row("1", "2")
    output = render(table, 40, color_system="standard")
    group_line = next(line for line in output.splitlines() if "grp" in line)
    # The style starts immediately after the left border and covers the
    # whole span, including the padding around the title.
    assert re.search(r"┃\x1b\[[0-9;]*31", group_line)
    assert "\x1b[" in group_line


def test_group_title_participates_in_measurement():
    console = make_console(80)
    table = Table()
    table.add_column("a")
    table.add_column("b")
    table.add_column_group("本地服务器统计信息", columns=[0, 1])
    table.add_row("1", "2")
    measurement = Measurement.get(console, console.options, table)
    # 16 cells for the group title, plus 2 edges and 1 divider
    assert measurement.minimum >= 16 + 3
    output = render(table, 80)
    # With room available, leaf columns grow so the title fits on one line
    assert "本地服务器统计信息" in output


def test_group_titles_wrap_when_narrow_and_keep_data_rows():
    table = build_local_remote_table()
    output = render(table, 20)
    assert_lines_within_width(output, 20)
    # Data rows are still rendered (group titles must not push them out)
    data_rows = [line for line in output.splitlines() if line.startswith("│")]
    assert len(data_rows) == 2


def test_narrower_than_minimum_column_width():
    table = build_local_remote_table()
    output = render(table, 10)
    assert_lines_within_width(output, 10)
    # The group title wraps rather than overflowing or hiding rows
    assert output.count("\n") >= 8


def test_table_without_groups_is_unchanged():
    table = Table()
    table.add_column("foo")
    table.add_column("bar")
    table.add_row("1", "2")
    assert table.column_groups == []
    assert render(table, 20) == EXPECTED_PLAIN_TABLE


@pytest.mark.parametrize(
    "make_group",
    [
        # empty group
        lambda table: table.add_column_group("empty"),
        # out of range column index
        lambda table: table.add_column_group("oob", columns=[0, 4]),
        # negative column index
        lambda table: table.add_column_group("neg", columns=[-1]),
        # duplicated column within one group
        lambda table: table.add_column_group("dup", columns=[0, 0]),
        # non-consecutive (crossing) span
        lambda table: table.add_column_group("cross", columns=[0, 2]),
        # two groups at the same level covering the same column
        lambda table: (
            table.add_column_group("g1", columns=[0, 1]),
            table.add_column_group("g2", columns=[1, 2]),
        ),
        # nested groups covering the same column
        lambda table: table.add_column_group(
            "outer",
            children=[
                ColumnGroup("c1", columns=[0, 1]),
                ColumnGroup("c2", columns=[1, 2]),
            ],
        ),
        # child span overlapping the parent's own columns
        lambda table: table.add_column_group(
            "outer",
            columns=[0],
            children=[ColumnGroup("c1", columns=[0, 1])],
        ),
    ],
)
def test_invalid_column_groups_raise_before_render(make_group):
    table = Table()
    for header in ["a", "b", "c"]:
        table.add_column(header)
    make_group(table)
    table.add_row("1", "2", "3")
    console = make_console(40)
    with pytest.raises(errors.ColumnGroupError):
        console.print(table)
    # Nothing should have been written before the error
    assert console.file.getvalue() == ""


def test_add_column_group_returns_group():
    table = Table()
    table.add_column("a")
    group = table.add_column_group("grp", columns=[0], style="bold")
    assert isinstance(group, ColumnGroup)
    assert table.column_groups == [group]
    assert group.columns == [0]
    assert group.justify == "center"
