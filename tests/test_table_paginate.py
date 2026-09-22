import io
import re

import pytest

from rich import errors
from rich.console import Console
from rich.table import Table, TablePage
from rich.text import Text

WIDTH = 32
PAGE_HEIGHT = 12


def make_console(width=WIDTH, **kwargs):
    return Console(file=io.StringIO(), width=width, **kwargs)


def build_table():
    # Table with CJK text, combining characters, a hyperlink and a cell
    # that spans more than three pages.
    table = Table(title="""分页 Demo""", caption="""caption""", show_footer=True)
    table.add_column("""名称""", footer="""f1""")
    table.add_column("""说明""", footer="""f2""")
    table.add_row("""caf\u00e9""", Text("""组合字符 e\u0301 中文""", style="""bold"""))
    table.add_row("""链接""", Text("""Rich 主页""", style="""link https://example.com"""))
    table.add_row("""长行""", """ """.join(f"""wide{i}中文""" for i in range(40)))
    for index in range(1, 8):
        table.add_row(f"""行{index}""", f"""内容 {index} 中文""")
    return table


def line_text(line):
    return """""".join(segment.text for segment in line)


def page_lines(page):
    return [line_text(line) for line in page.lines]


def body_rows(lines):
    # Content lines, with pagination decorations (borders/header/footer) removed.
    return [
        line
        for line in lines
        if line.startswith("""\u2502""")
        and """名称""" not in line
        and """f1""" not in line
    ]


def test_pages_are_renderable_and_fit_height():
    console = make_console()
    pages = build_table().paginate(console, WIDTH, PAGE_HEIGHT)
    assert len(pages) >= 3
    for page in pages:
        assert isinstance(page, TablePage)
        assert page.height <= PAGE_HEIGHT
        console.print(page)  # must not raise


def test_page_numbers_are_stable():
    console = make_console()
    table = build_table()
    first = table.paginate(console, WIDTH, PAGE_HEIGHT)
    second = table.paginate(console, WIDTH, PAGE_HEIGHT)
    assert len(first) == len(second)
    assert [page_lines(page) for page in first] == [
        page_lines(page) for page in second
    ]
    for number, page in enumerate(first, 1):
        assert page.page_number == number
        assert page.page_count == len(first)


def test_header_repeated_and_alignment_consistent():
    console = make_console()
    pages = build_table().paginate(console, WIDTH, PAGE_HEIGHT)
    # Page 1 starts with the title; the header block follows it.
    reference = page_lines(pages[0])[1:4]
    assert len(reference) == 3
    for page in pages[1:]:
        assert page_lines(page)[:3] == reference
    # Column widths are calculated once: every line on every page has
    # exactly the same cell width.
    widths = {
        sum(segment.cell_length for segment in line)
        for page in pages
        for line in page.lines
    }
    assert len(widths) == 1


def test_no_content_lost_or_reordered():
    console = make_console()
    table = build_table()
    full = console.render_lines(table, console.options.update_width(WIDTH))
    full_rows = body_rows([line_text(line) for line in full])
    pages = table.paginate(console, WIDTH, PAGE_HEIGHT)
    paged_rows = body_rows("""""")
    for page in pages:
        paged_rows.extend(body_rows(page_lines(page)))
    assert paged_rows == full_rows
    tokens = re.findall(r"""wide\d+""", """ """.join(paged_rows))
    assert tokens == [f"""wide{index}""" for index in range(40)]


def test_oversized_row_is_split_with_continuation_marks():
    console = make_console()
    pages = build_table().paginate(console, WIDTH, PAGE_HEIGHT)
    continued = [page for page in pages if page.continued]
    continues = [page for page in pages if page.continues]
    # The long cell spans more than three pages.
    assert len(continued) >= 3
    assert len(continues) == len(continued)
    for before, after in zip(pages, pages[1:]):
        assert after.continued == before.continues or not before.continues
        if before.continues:
            assert after.continued
    # No page exceeds the height, even mid-row.
    assert all(page.height <= PAGE_HEIGHT for page in pages)


def test_hyperlink_and_styles_survive_split():
    console = make_console()
    pages = build_table().paginate(console, WIDTH, PAGE_HEIGHT)
    links = [
        segment
        for page in pages
        for line in page.lines
        for segment in line
        if segment.style and segment.style.link
    ]
    assert len(links) == 1
    assert links[0].style.link == """https://example.com"""
    # Wide characters are never cut: every line is exactly table width.
    for page in pages:
        for line in page.lines:
            assert sum(segment.cell_length for segment in line) <= WIDTH


def test_ansi_styles_do_not_leak_between_pages():
    file = io.StringIO()
    console = Console(file=file, width=WIDTH, force_terminal=True)
    for page in build_table().paginate(console, WIDTH, PAGE_HEIGHT):
        console.print(page, end="""""")
    for line in file.getvalue().splitlines():
        if """\x1b[""" in line:
            # Any style opened on a line is closed before the line ends.
            assert line.endswith("""\x1b[0m""")


def test_empty_table_has_valid_output():
    console = make_console()
    table = Table(title="""empty""")
    table.add_column("""a""")
    pages = table.paginate(console, WIDTH, PAGE_HEIGHT)
    assert len(pages) == 1
    assert pages[0].height <= PAGE_HEIGHT
    # No columns at all.
    pages = Table().paginate(console, WIDTH, PAGE_HEIGHT)
    assert len(pages) == 1
    console.print(pages[0])


def test_page_height_too_small_raises():
    console = make_console()
    table = build_table()
    with pytest.raises(errors.PaginationError):
        table.paginate(console, WIDTH, 3)
    with pytest.raises(errors.PaginationError):
        table.paginate(console, WIDTH, 0)


def test_multiline_text_and_nested_renderable_cells():
    console = make_console()
    inner = Table.grid()
    inner.add_column()
    inner.add_row("""nested 1""")
    inner.add_row("""nested 2""")
    table = Table(show_footer=True)
    table.add_column("""col""", footer="""f""")
    table.add_row(Text("""line1\nline2\nline3"""))
    table.add_row(inner)
    for index in range(10):
        table.add_row(f"""row {index}""")
    pages = table.paginate(console, WIDTH, PAGE_HEIGHT)
    assert len(pages) >= 2
    assert all(page.height <= PAGE_HEIGHT for page in pages)
    text = """\n""".join(
        line for page in pages for line in page_lines(page)
    )
    for expected in ("""line1""", """line2""", """line3""", """nested 1""", """nested 2"""):
        assert expected in text
    for index in range(10):
        assert f"""row {index}""" in text


def test_console_render_table_pages_helper():
    console = make_console()
    table = build_table()
    pages = console.render_table_pages(table, PAGE_HEIGHT, width=WIDTH)
    expected = table.paginate(console, WIDTH, PAGE_HEIGHT)
    assert [page_lines(page) for page in pages] == [
        page_lines(page) for page in expected
    ]
    assert all(page.height <= PAGE_HEIGHT for page in pages)
