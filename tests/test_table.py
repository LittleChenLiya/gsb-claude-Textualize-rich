# encoding=utf-8

import io
from textwrap import dedent

import pytest

from rich import box, errors
from rich.console import Console
from rich.measure import Measurement
from rich.style import Style
from rich.table import Column, Table
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


class CountingRenderable:
    """A stateful renderable that counts invocations of __rich_console__."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.render_count = 0

    def __rich_console__(self, console, options):
        from rich.control import Control

        self.render_count += 1
        yield Text(f"{self.label} 第{self.render_count}次")
        yield Control.bell()


class WidthAwareRenderable:
    """A renderable that outputs as many characters as the render width allows."""

    def __rich_console__(self, console, options):
        yield "x" * options.max_width


def _plain_console():
    return Console(
        file=io.StringIO(),
        force_terminal=True,
        legacy_windows=False,
        color_system="truecolor",
        width=80,
    )


def test_table_export_data_values_and_single_render():
    console = _plain_console()
    counting_cell = CountingRenderable("动态")
    table = Table("姓名", "备注", "年龄")
    table.add_row(Text("张三", style="bold red"), "第一行\n第二行", 42)
    table.add_row("李四", counting_cell, 3.5)

    data = table.export_data(console=console)

    assert [column["name"] for column in data["columns"]] == [
        "姓名",
        "备注",
        "年龄",
    ]
    assert [column["index"] for column in data["columns"]] == [0, 1, 2]

    first_row = data["rows"][0]["cells"]
    assert first_row[0]["text"] == "张三"
    assert first_row[1]["text"] == "第一行\n第二行"
    assert first_row[2]["text"] == "42"

    second_row = data["rows"][1]["cells"]
    assert second_row[0]["text"] == "李四"
    assert second_row[1]["text"] == "动态 第1次"
    assert second_row[2]["text"] == "3.5"
    # The stateful renderable must have been rendered exactly once.
    assert counting_cell.render_count == 1


def test_table_export_json_roundtrip():
    import json

    table = Table("姓名")
    table.add_row("张三")
    rendered = table.export_json(indent=2)
    assert "\\u" not in rendered
    data = json.loads(rendered)
    assert data["rows"][0]["cells"][0]["text"] == "张三"


def test_table_export_json_writes_file(tmp_path):
    table = Table("a")
    table.add_row("value")
    path = tmp_path / "table.json"
    result = table.export_json(path=str(path))
    assert result is None
    import json

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["rows"][0]["cells"][0]["text"] == "value"


def test_table_export_empty():
    console = _plain_console()
    table = Table("a", "b")
    data = table.export_data(console=console)
    assert data == {
        "columns": [
            {"index": 0, "name": "a", "header": "a"},
            {"index": 1, "name": "b", "header": "b"},
        ],
        "rows": [],
    }

    table_without_columns = Table()
    assert table_without_columns.export_data(console=console) == {
        "columns": [],
        "rows": [],
    }


def test_table_export_duplicate_column_names():
    console = _plain_console()
    table = Table("名称", "名称")
    table.add_row("第一个", "第二个")
    data = table.export_data(console=console)

    names = [column["name"] for column in data["columns"]]
    assert names == ["名称", "名称"]
    cells = data["rows"][0]["cells"]
    assert cells[0]["column_index"] == 0
    assert cells[1]["column_index"] == 1
    assert cells[0]["text"] == "第一个"
    assert cells[1]["text"] == "第二个"


def test_table_export_empty_cell_and_none():
    console = _plain_console()
    table = Table("a", "b")
    table.add_row("", None)
    data = table.export_data(console=console)
    cells = data["rows"][0]["cells"]
    assert cells[0]["text"] == ""
    assert cells[1]["text"] == ""


def test_table_export_strips_styles_and_control_codes():
    console = _plain_console()
    table = Table("标题")
    table.add_row(Text("红\n绿", style="bold red"))
    table.add_row(CountingRenderable("带控制字符"))
    data = table.export_data(console=console)
    text = data["rows"][0]["cells"][0]["text"]
    assert text == "红\n绿"
    assert "\x1b" not in text
    assert "\x07" not in text
    control_text = data["rows"][1]["cells"][0]["text"]
    assert control_text == "带控制字符 第1次"
    assert "\x07" not in control_text


def test_table_export_does_not_wrap_or_ellipsize():
    console = Console(width=10, file=io.StringIO())
    table = Table()
    table.add_column("long", overflow="ellipsis")
    long_text = "这是一段非常非常长的文本内容"
    table.add_row(long_text)
    data = table.export_data(console=console)
    assert data["rows"][0]["cells"][0]["text"] == long_text
    assert "…" not in data["rows"][0]["cells"][0]["text"]


def test_table_export_max_cell_length_failure():
    console = _plain_console()
    table = Table("a", "b")
    table.add_row("ok", "这真的太长了")

    with pytest.raises(errors.CellOverflowError) as exc_info:
        table.export_data(console=console, max_cell_length=4)
    message = str(exc_info.value)
    assert "row 0" in message
    assert "column 1" in message
    assert "b" in message


def test_table_export_max_cell_length_at_boundary():
    console = _plain_console()
    table = Table("a")
    table.add_row("1234")
    data = table.export_data(console=console, max_cell_length=4)
    assert data["rows"][0]["cells"][0]["text"] == "1234"


def test_table_export_max_cell_length_with_width_aware_renderable():
    console = _plain_console()
    table = Table("a")
    table.add_row(WidthAwareRenderable())
    with pytest.raises(errors.CellOverflowError):
        table.export_data(console=console, max_cell_length=10)


def test_table_export_max_cell_length_counts_newlines():
    console = _plain_console()
    table = Table("a")
    table.add_row("ab\ncd")
    with pytest.raises(errors.CellOverflowError):
        table.export_data(console=console, max_cell_length=4)


def test_table_export_json_failure_leaves_no_file(tmp_path):
    console = _plain_console()
    table = Table("a")
    table.add_row("这真的太长了")
    path = tmp_path / "partial.json"
    with pytest.raises(errors.CellOverflowError):
        table.export_json(console=console, max_cell_length=2, path=str(path))
    assert not path.exists()


def test_table_export_invalid_max_cell_length():
    with pytest.raises(ValueError):
        Table("a").export_data(max_cell_length=-1)


def test_table_render_unchanged_by_export():
    """Displaying the table before and after export must be identical."""

    table = Table("姓名", "信息", "年龄")
    table.add_row(Text("张三", style="bold red"), "第一行\n第二行", 42)
    table.add_row("李四", "", 3)
    before_console = _plain_console()
    before_console.print(table)
    table.export_data(console=_plain_console())
    after_console = _plain_console()
    after_console.print(table)
    before = before_console.file.getvalue()
    after = after_console.file.getvalue()
    assert before == after


def test_table_numbers_are_renderable_in_rows():
    console = _plain_console()
    table = Table("n")
    table.add_row(1)
    table.add_row(2.5)
    rendered = "".join(
        segment.text for lines in console.render_lines(table) for segment in lines
    )
    assert "1" in rendered
    assert "2.5" in rendered


if __name__ == "__main__":
    render = render_tables()
    print(render)
    print(repr(render))
