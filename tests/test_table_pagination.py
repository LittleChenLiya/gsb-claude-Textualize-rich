import io

import pytest

from rich import errors
from rich.cells import cell_len
from rich.console import Console
from rich.table import Table, TablePage
from rich.text import Text

WIDTH = 32
PAGE_HEIGHT = 12
HEADER_LINES = 3  # top border, header row, header separator
FOOTER_LINES = 1  # bottom border
PAGE_NUMBER_LINES = 1


def build_table() -> Table:
    table = Table(title="分页演示 Demo")
    table.add_column("名称")
    table.add_column("说明", overflow="fold")
    table.add_row("中文标题", "cafe\u0301 组合字符")
    table.add_row("链接", Text("example 链接", style="link https://example.com"))
    for index in range(6):
        table.add_row(f"行{index}", "短行")
    long_text = "很长的单元格内容，用来测试跨页拆分。" * 12
    table.add_row("长行", Text(long_text))
    table.add_row("结尾", "最后一行")
    return table


def make_console(width: int = WIDTH, force_terminal: bool = False) -> Console:
    return Console(file=io.StringIO(), width=width, force_terminal=force_terminal)


def line_text(line) -> str:
    return "".join(segment.text for segment in line).rstrip()


def page_content_lines(page: TablePage, first: bool):
    """Strip pagination decorations (header, footer, page number, title,
    continuation markers) and return the remaining content lines as text."""
    body = page.lines[HEADER_LINES : len(page.lines) - FOOTER_LINES - PAGE_NUMBER_LINES]
    texts = [line_text(line) for line in body]
    if first:
        title = texts.pop(0)
        assert "Demo" in title
    return [text for text in texts if "(continued)" not in text]


def test_pages_fit_height():
    console = make_console()
    pages = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    assert len(pages) >= 3
    for page in pages:
        assert len(page.lines) <= PAGE_HEIGHT
        console.file.seek(0)
        console.file.truncate(0)
        console.print(page, end="")
        output = console.file.getvalue()
        assert output.count("\n") <= PAGE_HEIGHT
        for output_line in output.splitlines():
            assert cell_len(output_line) <= WIDTH


def test_header_and_borders_repeated_and_aligned():
    console = make_console()
    pages = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    headers = [
        [line_text(line) for line in page.lines[:HEADER_LINES]] for page in pages
    ]
    for header in headers[1:]:
        assert header == headers[0]
    footers = [line_text(page.lines[-2]) for page in pages]
    assert len(set(footers)) == 1


def test_page_numbers_stable():
    console = make_console()
    first = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    second = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    assert len(first) == len(second)
    for index, page in enumerate(first, 1):
        assert page.page_number == index
        assert page.page_count == len(first)
        assert f"Page {index} of {len(first)}" in line_text(page.lines[-1])


def test_content_preserved_and_ordered():
    console = make_console()
    table = build_table()
    pages = table.paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    collected = []
    for index, page in enumerate(pages):
        collected.extend(page_content_lines(page, first=index == 0))

    full_lines = console.render_lines(table, console.options.update(width=WIDTH))
    expected = [
        line_text(line)
        for line in full_lines[1 + HEADER_LINES : len(full_lines) - FOOTER_LINES]
    ]
    assert collected == expected


def test_oversized_row_continuation():
    console = make_console()
    pages = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    markers = [
        line_text(line)
        for page in pages
        for line in page.lines
        if "(continued)" in line_text(line)
    ]
    assert len(markers) >= 2  # long row spans at least three pages
    assert all(len(page.lines) <= PAGE_HEIGHT for page in pages)


def test_wide_and_combining_characters_intact():
    console = make_console()
    pages = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    collected = []
    for index, page in enumerate(pages):
        collected.extend(page_content_lines(page, first=index == 0))
    joined = "\n".join(collected)
    assert "中文标题" in joined
    assert "cafe\u0301" in joined
    assert "example 链接" in joined


def test_no_style_or_link_leak_between_pages():
    console = make_console(force_terminal=True)
    pages = build_table().paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    for page in pages:
        console.file.seek(0)
        console.file.truncate(0)
        console.print(page, end="")
        output = console.file.getvalue()
        for output_line in output.splitlines():
            if "\x1b[" in output_line:
                # any style opened on a line is reset on the same line
                assert "\x1b[0m" in output_line
        # hyperlinks are opened and closed within the page
        assert output.count("\x1b]8;id=") == output.count("\x1b]8;;\x1b\\")


def test_empty_table_has_valid_output():
    console = make_console()
    table = Table()
    table.add_column("empty")
    pages = table.paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    assert len(pages) == 1
    console.print(pages[0])


def test_page_height_too_small():
    console = make_console()
    table = build_table()
    with pytest.raises(errors.PaginationError):
        table.paginate(console, width=WIDTH, page_height=5)


def test_multiline_text_and_nested_renderable():
    console = make_console()
    table = Table()
    table.add_column("key")
    table.add_column("value")
    table.add_row("multi", Text("one\ntwo\nthree\nfour"))
    nested = Table()
    nested.add_column("a")
    nested.add_row("nested")
    table.add_row("nested", nested)
    pages = table.paginate(console, width=WIDTH, page_height=PAGE_HEIGHT)
    assert pages
    for page in pages:
        assert len(page.lines) <= PAGE_HEIGHT
