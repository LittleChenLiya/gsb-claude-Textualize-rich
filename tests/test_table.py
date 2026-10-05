# encoding=utf-8

import io
from textwrap import dedent

import pytest

from rich import box, errors
from rich.console import Console
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style
from rich.table import Column, Table, TableLayoutReport
from rich.text import Text


def render_tables():
    console = Console(
        width=60,
        force_terminal=True,
        file=io.StringIO(),
        legacy_windows=False,
        color_system=None,
        _environ={},
    )

    table = Table(title="test table", caption="table caption", expand=False)
    table.add_column("foo", footer=Text("total"), no_wrap=True, overflow="ellipsis")
    table.add_column("bar", justify="center")
    table.add_column("baz", justify="right")

    table.add_row("Averlongwordgoeshere", "banana pancakes", None)

    assert Measurement.get(console, console.options, table) == Measurement(41, 48)
    table.expand = True
    assert Measurement.get(console, console.options, table) == Measurement(41, 48)

    for width in range(10, 60, 5):
        console.print(table, width=width)

    table.expand = False
    console.print(table, justify="left")
    console.print(table, justify="center")
    console.print(table, justify="right")

    assert table.row_count == 1

    table.row_styles = ["red", "yellow"]
    table.add_row("Coffee")
    table.add_row("Coffee", "Chocolate", None, "cinnamon")

    assert table.row_count == 3

    console.print(table)

    table.show_lines = True
    console.print(table)

    table.show_footer = True
    console.print(table)

    table.show_edge = False

    console.print(table)

    table.padding = 1
    console.print(table)

    table.width = 20
    assert Measurement.get(console, console.options, table) == Measurement(20, 20)
    table.expand = False
    assert Measurement.get(console, console.options, table) == Measurement(20, 20)
    table.expand = True
    console.print(table)

    table.columns[0].no_wrap = True
    table.columns[1].no_wrap = True
    table.columns[2].no_wrap = True

    console.print(table)

    table.padding = 0
    table.width = 60
    table.leading = 1
    console.print(table)

    return console.file.getvalue()


def test_render_table():
    expected = "test table\n┏━━━━━━┳┳┓\n┃ foo  ┃┃┃\n┡━━━━━━╇╇┩\n│ Ave… │││\n└──────┴┴┘\n  table   \n caption  \n  test table   \n┏━━━━━━━━━━━┳┳┓\n┃ foo       ┃┃┃\n┡━━━━━━━━━━━╇╇┩\n│ Averlong… │││\n└───────────┴┴┘\n table caption \n     test table     \n┏━━━━━━━━━━━━━━━━┳┳┓\n┃ foo            ┃┃┃\n┡━━━━━━━━━━━━━━━━╇╇┩\n│ Averlongwordg… │││\n└────────────────┴┴┘\n   table caption    \n       test table        \n┏━━━━━━━━━━━━━━━━━━━━━┳┳┓\n┃ foo                 ┃┃┃\n┡━━━━━━━━━━━━━━━━━━━━━╇╇┩\n│ Averlongwordgoeshe… │││\n└─────────────────────┴┴┘\n      table caption      \n          test table          \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━┳━━┓\n┃ foo                  ┃  ┃  ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━╇━━┩\n│ Averlongwordgoeshere │  │  │\n└──────────────────────┴──┴──┘\n        table caption         \n            test table             \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━┓\n┃ foo                  ┃ bar ┃ b… ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━┩\n│ Averlongwordgoeshere │ ba… │    │\n│                      │ pa… │    │\n└──────────────────────┴─────┴────┘\n           table caption           \n               test table               \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━┓\n┃ foo                  ┃   bar   ┃ baz ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━┩\n│ Averlongwordgoeshere │ banana  │     │\n│                      │ pancak… │     │\n└──────────────────────┴─────────┴─────┘\n             table caption              \n                 test table                  \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━┓\n┃ foo                  ┃     bar      ┃ baz ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━┩\n│ Averlongwordgoeshere │    banana    │     │\n│                      │   pancakes   │     │\n└──────────────────────┴──────────────┴─────┘\n                table caption                \n                    test table                    \n┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━┓\n┃ foo                   ┃       bar        ┃ baz ┃\n┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━┩\n│ Averlongwordgoeshere  │ banana pancakes  │     │\n└───────────────────────┴──────────────────┴─────┘\n                  table caption                   \n                      test table                       \n┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━┓\n┃ foo                      ┃        bar         ┃ baz ┃\n┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━┩\n│ Averlongwordgoeshere     │  banana pancakes   │     │\n└──────────────────────────┴────────────────────┴─────┘\n                     table caption                     \n                   test table                               \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━┓            \n┃ foo                  ┃       bar       ┃ baz ┃            \n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━┩            \n│ Averlongwordgoeshere │ banana pancakes │     │            \n└──────────────────────┴─────────────────┴─────┘            \n                 table caption                              \n                         test table                         \n      ┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━┓      \n      ┃ foo                  ┃       bar       ┃ baz ┃      \n      ┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━┩      \n      │ Averlongwordgoeshere │ banana pancakes │     │      \n      └──────────────────────┴─────────────────┴─────┘      \n                       table caption                        \n                               test table                   \n            ┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━┓\n            ┃ foo                  ┃       bar       ┃ baz ┃\n            ┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━┩\n            │ Averlongwordgoeshere │ banana pancakes │     │\n            └──────────────────────┴─────────────────┴─────┘\n                             table caption                  \n                        test table                         \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━┓\n┃ foo                  ┃       bar       ┃ baz ┃          ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━┩\n│ Averlongwordgoeshere │ banana pancakes │     │          │\n│ Coffee               │                 │     │          │\n│ Coffee               │    Chocolate    │     │ cinnamon │\n└──────────────────────┴─────────────────┴─────┴──────────┘\n                       table caption                       \n                        test table                         \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━┓\n┃ foo                  ┃       bar       ┃ baz ┃          ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━┩\n│ Averlongwordgoeshere │ banana pancakes │     │          │\n├──────────────────────┼─────────────────┼─────┼──────────┤\n│ Coffee               │                 │     │          │\n├──────────────────────┼─────────────────┼─────┼──────────┤\n│ Coffee               │    Chocolate    │     │ cinnamon │\n└──────────────────────┴─────────────────┴─────┴──────────┘\n                       table caption                       \n                        test table                         \n┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━┓\n┃ foo                  ┃       bar       ┃ baz ┃          ┃\n┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━┩\n│ Averlongwordgoeshere │ banana pancakes │     │          │\n├──────────────────────┼─────────────────┼─────┼──────────┤\n│ Coffee               │                 │     │          │\n├──────────────────────┼─────────────────┼─────┼──────────┤\n│ Coffee               │    Chocolate    │     │ cinnamon │\n├──────────────────────┼─────────────────┼─────┼──────────┤\n│ total                │                 │     │          │\n└──────────────────────┴─────────────────┴─────┴──────────┘\n                       table caption                       \n                       test table                        \n foo                  ┃       bar       ┃ baz ┃          \n━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━\n Averlongwordgoeshere │ banana pancakes │     │          \n──────────────────────┼─────────────────┼─────┼──────────\n Coffee               │                 │     │          \n──────────────────────┼─────────────────┼─────┼──────────\n Coffee               │    Chocolate    │     │ cinnamon \n──────────────────────┼─────────────────┼─────┼──────────\n total                │                 │     │          \n                      table caption                      \n                       test table                        \n                      ┃                 ┃     ┃          \n foo                  ┃       bar       ┃ baz ┃          \n                      ┃                 ┃     ┃          \n━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━\n                      │                 │     │          \n Averlongwordgoeshere │ banana pancakes │     │          \n                      │                 │     │          \n──────────────────────┼─────────────────┼─────┼──────────\n                      │                 │     │          \n Coffee               │                 │     │          \n                      │                 │     │          \n──────────────────────┼─────────────────┼─────┼──────────\n                      │                 │     │          \n Coffee               │    Chocolate    │     │ cinnamon \n                      │                 │     │          \n──────────────────────┼─────────────────┼─────┼──────────\n                      │                 │     │          \n total                │                 │     │          \n                      │                 │     │          \n                      table caption                      \n     test table     \n                 ┃┃┃\n foo             ┃┃┃\n                 ┃┃┃\n━━━━━━━━━━━━━━━━━╇╇╇\n                 │││\n Averlongwordgo… │││\n                 │││\n─────────────────┼┼┼\n                 │││\n Coffee          │││\n                 │││\n─────────────────┼┼┼\n                 │││\n Coffee          │││\n                 │││\n─────────────────┼┼┼\n                 │││\n total           │││\n                 │││\n   table caption    \n      test table      \n          ┃         ┃┃\n foo      ┃   bar   ┃┃\n          ┃         ┃┃\n━━━━━━━━━━╇━━━━━━━━━╇╇\n          │         ││\n Averlon… │ banana… ││\n          │         ││\n──────────┼─────────┼┼\n          │         ││\n Coffee   │         ││\n          │         ││\n──────────┼─────────┼┼\n          │         ││\n Coffee   │ Chocol… ││\n          │         ││\n──────────┼─────────┼┼\n          │         ││\n total    │         ││\n          │         ││\n    table caption     \n                         test table                         \nfoo                      ┃        bar        ┃ baz┃         \n━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━╇━━━━━━━━━\nAverlongwordgoeshere     │  banana pancakes  │    │         \n                         │                   │    │         \nCoffee                   │                   │    │         \n                         │                   │    │         \nCoffee                   │     Chocolate     │    │cinnamon \n─────────────────────────┼───────────────────┼────┼─────────\ntotal                    │                   │    │         \n                       table caption                        \n"
    result = render_tables()
    print(repr(result))
    assert result == expected


def test_not_renderable():
    class Foo:
        pass

    table = Table()
    with pytest.raises(errors.NotRenderableError):
        table.add_row(Foo())


def test_init_append_column():
    header_names = ["header1", "header2", "header3"]
    test_columns = [
        Column(_index=index, header=header) for index, header in enumerate(header_names)
    ]

    # Test appending of strings for header names
    assert Table(*header_names).columns == test_columns
    # Test directly passing a Table Column objects
    assert Table(*test_columns).columns == test_columns


def test_rich_measure():
    console = Console()
    assert Table("test_header", width=-1).__rich_measure__(
        console, console.options
    ) == Measurement(0, 0)
    # Check __rich_measure__() for a positive width passed as an argument
    assert Table("test_header", width=None).__rich_measure__(
        console, console.options.update_width(10)
    ) == Measurement(10, 10)


def test_min_width():
    table = Table("foo", min_width=30)
    table.add_row("bar")
    console = Console()
    assert table.__rich_measure__(
        console, console.options.update_width(100)
    ) == Measurement(30, 30)
    console = Console(color_system=None)
    console.begin_capture()
    console.print(table)
    output = console.end_capture()
    print(output)
    assert all(len(line) == 30 for line in output.splitlines())


def test_no_columns():
    console = Console(color_system=None)
    console.begin_capture()
    console.print(Table())
    output = console.end_capture()
    print(repr(output))
    assert output == "\n"


def test_get_row_style():
    console = Console()
    table = Table()
    table.add_row("foo")
    table.add_row("bar", style="on red")
    assert table.get_row_style(console, 0) == Style.parse("")
    assert table.get_row_style(console, 1) == Style.parse("on red")


def test_vertical_align_top():
    console = Console(_environ={})

    def make_table(vertical_align):
        table = Table(show_header=False, box=box.SQUARE)
        table.add_column(vertical=vertical_align)
        table.add_row("foo", "\n".join(["bar"] * 5))

        return table

    with console.capture() as capture:
        console.print(make_table("top"))
        console.print()
        console.print(make_table("middle"))
        console.print()
        console.print(make_table("bottom"))
        console.print()
    result = capture.get()
    print(repr(result))
    expected = "┌─────┬─────┐\n│ foo │ bar │\n│     │ bar │\n│     │ bar │\n│     │ bar │\n│     │ bar │\n└─────┴─────┘\n\n┌─────┬─────┐\n│     │ bar │\n│     │ bar │\n│ foo │ bar │\n│     │ bar │\n│     │ bar │\n└─────┴─────┘\n\n┌─────┬─────┐\n│     │ bar │\n│     │ bar │\n│     │ bar │\n│     │ bar │\n│ foo │ bar │\n└─────┴─────┘\n\n"
    assert result == expected


@pytest.mark.parametrize(
    "box,result",
    [
        (None, " 1  2 \n 3  4 \n"),
        (box.HEAVY_HEAD, "┌───┬───┐\n│ 1 │ 2 │\n│ 3 │ 4 │\n└───┴───┘\n"),
        (box.SQUARE_DOUBLE_HEAD, "┌───┬───┐\n│ 1 │ 2 │\n│ 3 │ 4 │\n└───┴───┘\n"),
        (box.MINIMAL_DOUBLE_HEAD, "    ╷    \n  1 │ 2  \n  3 │ 4  \n    ╵    \n"),
        (box.MINIMAL_HEAVY_HEAD, "    ╷    \n  1 │ 2  \n  3 │ 4  \n    ╵    \n"),
        (box.ASCII_DOUBLE_HEAD, "+---+---+\n| 1 | 2 |\n| 3 | 4 |\n+---+---+\n"),
    ],
)
def test_table_show_header_false_substitution(box, result):
    """When the box style is one with a custom header edge, it should be substituted for
    the equivalent box that does not have a custom header when show_header=False"""
    table = Table(show_header=False, box=box)
    table.add_column()
    table.add_column()

    table.add_row("1", "2")
    table.add_row("3", "4")

    console = Console(record=True)
    console.print(table)
    output = console.export_text()

    assert output == result


def test_section():
    table = Table("foo")
    table.add_section()  # Null-op
    table.add_row("row1")
    table.add_row("row2", end_section=True)
    table.add_row("row3")
    table.add_row("row4")
    table.add_section()
    table.add_row("row5")
    table.add_section()  # Null-op

    console = Console(
        width=80,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
        record=True,
    )
    console.print(table)
    output = console.export_text()
    print(repr(output))
    expected = "┏━━━━━━┓\n┃ foo  ┃\n┡━━━━━━┩\n│ row1 │\n│ row2 │\n├──────┤\n│ row3 │\n│ row4 │\n├──────┤\n│ row5 │\n└──────┘\n"

    assert output == expected


@pytest.mark.parametrize(
    "show_header,show_footer,expected",
    [
        (
            False,
            False,
            dedent(
                """
                abbbbbcbbbbbbbbbcbbbbcbbbbbd
                1Dec  2Skywalker2275M2375M 3
                4May  5Solo     5275M5393M 6
                ijjjjjkjjjjjjjjjkjjjjkjjjjjl
                7Dec  8Last Jedi8262M81333M9
                qrrrrrsrrrrrrrrrsrrrrsrrrrrt
                """
            ).lstrip(),
        ),
        (
            True,
            False,
            dedent(
                """
                abbbbbcbbbbbbbbbcbbbbcbbbbbd
                1Month2Nickname 2Cost2Gross3
                efffffgfffffffffgffffgfffffh
                4Dec  5Skywalker5275M5375M 6
                4May  5Solo     5275M5393M 6
                ijjjjjkjjjjjjjjjkjjjjkjjjjjl
                7Dec  8Last Jedi8262M81333M9
                qrrrrrsrrrrrrrrrsrrrrsrrrrrt
                """
            ).lstrip(),
        ),
        (
            False,
            True,
            dedent(
                """
                abbbbbcbbbbbbbbbcbbbbcbbbbbd
                1Dec  2Skywalker2275M2375M 3
                4May  5Solo     5275M5393M 6
                ijjjjjkjjjjjjjjjkjjjjkjjjjjl
                4Dec  5Last Jedi5262M51333M6
                mnnnnnonnnnnnnnnonnnnonnnnnp
                7MONTH8NICKNAME 8COST8GROSS9
                qrrrrrsrrrrrrrrrsrrrrsrrrrrt
                """
            ).lstrip(),
        ),
        (
            True,
            True,
            dedent(
                """
                abbbbbcbbbbbbbbbcbbbbcbbbbbd
                1Month2Nickname 2Cost2Gross3
                efffffgfffffffffgffffgfffffh
                4Dec  5Skywalker5275M5375M 6
                4May  5Solo     5275M5393M 6
                ijjjjjkjjjjjjjjjkjjjjkjjjjjl
                4Dec  5Last Jedi5262M51333M6
                mnnnnnonnnnnnnnnonnnnonnnnnp
                7MONTH8NICKNAME 8COST8GROSS9
                qrrrrrsrrrrrrrrrsrrrrsrrrrrt
                """
            ).lstrip(),
        ),
    ],
)
def test_placement_table_box_elements(show_header, show_footer, expected):
    """Ensure box drawing characters correctly positioned."""

    table = Table(
        box=box.ASCII, show_header=show_header, show_footer=show_footer, padding=0
    )

    # content rows indicated by numerals, pure dividers by letters
    table.box.__dict__.update(
        top_left="a",
        top="b",
        top_divider="c",
        top_right="d",
        head_left="1",
        head_vertical="2",
        head_right="3",
        head_row_left="e",
        head_row_horizontal="f",
        head_row_cross="g",
        head_row_right="h",
        mid_left="4",
        mid_vertical="5",
        mid_right="6",
        row_left="i",
        row_horizontal="j",
        row_cross="k",
        row_right="l",
        foot_left="7",
        foot_vertical="8",
        foot_right="9",
        foot_row_left="m",
        foot_row_horizontal="n",
        foot_row_cross="o",
        foot_row_right="p",
        bottom_left="q",
        bottom="r",
        bottom_divider="s",
        bottom_right="t",
    )

    # add content - note headers title case, footers upper case
    table.add_column("Month", "MONTH", width=5)
    table.add_column("Nickname", "NICKNAME", width=9)
    table.add_column("Cost", "COST", width=4)
    table.add_column("Gross", "GROSS", width=5)

    table.add_row("Dec", "Skywalker", "275M", "375M")
    table.add_row("May", "Solo", "275M", "393M")
    table.add_section()
    table.add_row("Dec", "Last Jedi", "262M", "1333M")

    console = Console(record=True, width=28)
    console.print(table)
    output = console.export_text()
    print(repr(output))

    assert output == expected


def test_columns_highlight_added_by_add_row() -> None:
    """Regression test for https://github.com/Textualize/rich/issues/3517"""
    table = Table(show_header=False, highlight=True)
    table.add_row("1", repr("FOO"))

    assert table.columns[0].highlight == table.highlight
    assert table.columns[1].highlight == table.highlight

    console = Console(record=True)
    console.print(table)
    output = console.export_text(styles=True)
    print(repr(output))

    expected = (
        "┌───┬───────┐\n│ \x1b[1;36m1\x1b[0m │ \x1b[32m'FOO'\x1b[0m │\n└───┴───────┘\n"
    )
    assert output == expected


def test_padding_width():
    """Regression test for https://github.com/Textualize/rich/issues/3871

    Padding should be even between cells/

    """

    table = Table.grid(padding=(0, 1))

    for _ in range(3):
        table.add_column(width=3)

    for row in range(1):
        table.add_row(*["a" * 3 for _ in range(3)])

    console = Console(record=True)
    console.print(table)
    output = console.export_text(styles=True)

    print(repr(output))
    expected = "aaa aaa aaa\n"
    assert output == expected


# ---------------------------------------------------------------------------
# Layout report tests
# ---------------------------------------------------------------------------


def _fixed_console(width: int = 60) -> Console:
    """Get a console with a fixed terminal width."""
    return Console(
        width=width,
        height=25,
        force_terminal=True,
        legacy_windows=False,
        color_system=None,
        _environ={},
    )


def test_layout_report_chinese_english_mixed():
    """A Chinese-English mixed table at a fixed width has the correct total."""
    console = _fixed_console(40)
    table = Table(expand=False)
    table.add_column("Name")
    table.add_column("Description")
    table.add_row("Alice", "一个中英文混合的描述内容")
    table.add_row("Bob", "short")

    report = table.get_layout_report(console)

    assert isinstance(report, TableLayoutReport)
    # Total width must not exceed the terminal width.
    assert report.total_width <= 40
    # The Chinese description is 12 CJK characters = 24 cells, plus padding 2.
    desc = report.columns[1]
    assert desc.max_width == 26
    # Total = col0 (7) + col1 (26) + border (3) = 36.
    assert report.total_width == 36
    # Borders and padding are counted in the total.
    assert report.border_width == 3
    assert report.padding_width == 4
    # The report does not store cell text.
    assert not hasattr(report, "cells")
    assert not hasattr(report, "renderables")


def test_layout_report_collapse_reason():
    """Columns that shrink to fit the terminal report the collapse reason."""
    console = _fixed_console(30)
    table = Table(expand=False)
    table.add_column("foo")
    table.add_column("bar")
    table.add_row("this is a long sentence that wraps", "another long sentence here")

    report = table.get_layout_report(console)

    assert report.total_width == 30
    for column in report.columns:
        assert column.reason == "collapse"
        assert column.final_width < column.max_width


def test_layout_report_fixed_width_reason():
    """A fixed-width column reports the fixed_width reason."""
    console = _fixed_console(60)
    table = Table(expand=False)
    table.add_column("foo", width=10)
    table.add_column("bar")
    table.add_row("a", "this is a long sentence")

    report = table.get_layout_report(console)

    assert report.columns[0].reason == "fixed_width"
    assert report.columns[0].final_width == 12  # 10 + padding


def test_layout_report_expand_reason():
    """An expanded table reports the expand reason and fills the terminal."""
    console = _fixed_console(50)
    table = Table(expand=True)
    table.add_column("foo")
    table.add_column("bar")
    table.add_row("a", "b")

    report = table.get_layout_report(console)

    assert report.total_width == 50
    for column in report.columns:
        assert column.reason == "expand"


def test_layout_report_min_width_reason():
    """A table constrained by min_width reports the min_width reason."""
    console = _fixed_console(60)
    table = Table(expand=False, min_width=50)
    table.add_column("foo")
    table.add_row("short")

    report = table.get_layout_report(console)

    assert report.total_width == 50
    assert report.columns[0].reason == "min_width"


def test_layout_report_consistency_with_render():
    """The standalone report matches the report captured during rendering."""
    console = _fixed_console(40)
    table = Table(expand=False)
    table.add_column("Name")
    table.add_column("Description")
    table.add_row("Alice", "一个中英文混合的描述内容")
    table.add_row("Bob", "short")

    standalone = table.get_layout_report(console)
    console.print(table)
    rendered = table.layout_report

    assert rendered is not None
    assert standalone.total_width == rendered.total_width
    assert standalone.border_width == rendered.border_width
    assert standalone.padding_width == rendered.padding_width
    for a, b in zip(standalone.columns, rendered.columns):
        assert a.final_width == b.final_width
        assert a.reason == b.reason


def test_layout_report_counting_renderable():
    """The report must not cause custom renderables to be re-executed."""

    class CountingRenderable:
        def __init__(self, text: str) -> None:
            self.text = text
            self.measure_count = 0

        def __rich_measure__(self, console: Console, options):
            self.measure_count += 1
            from rich.cells import cell_len

            width = cell_len(self.text)
            return Measurement(width, width)

        def __rich_console__(self, console: Console, options):
            yield Segment(self.text)

    console = _fixed_console(60)
    table = Table(expand=False)
    table.add_column("A")
    table.add_column("B")
    r1 = CountingRenderable("hello")
    r2 = CountingRenderable("world")
    table.add_row(r1, r2)

    # Generate a standalone report: each renderable is measured once.
    report = table.get_layout_report(console)
    assert r1.measure_count == 1
    assert r2.measure_count == 1

    # Rendering captures the report for free; no extra measurements.
    r1.measure_count = 0
    r2.measure_count = 0
    console.print(table)
    assert r1.measure_count == 1
    assert r2.measure_count == 1
    assert table.layout_report is not None
    assert table.layout_report.total_width == report.total_width


def test_layout_report_padding_counted():
    """Padding is counted in column widths and the total."""
    console = _fixed_console(60)
    table = Table(expand=False, padding=(1, 2), box=None)
    table.add_column("foo")
    table.add_row("bar")

    report = table.get_layout_report(console)

    # padding = top 1 + right 2 + bottom 1 + left 2; horizontal = 4
    assert report.columns[0].padding_width == 4
    assert report.padding_width == 4
    # content "bar" = 3, plus padding 4 = 7
    assert report.columns[0].final_width == 7
    # no edge box: total = final width only
    assert report.total_width == 7


def test_layout_report_no_wrap():
    """A no_wrap column that fits reports the none reason."""
    console = _fixed_console(60)
    table = Table(expand=False)
    table.add_column("foo", no_wrap=True)
    table.add_row("short")

    report = table.get_layout_report(console)

    assert report.columns[0].reason == "none"
    assert report.columns[0].final_width == report.columns[0].max_width


if __name__ == "__main__":
    render = render_tables()
    print(render)
    print(repr(render))
