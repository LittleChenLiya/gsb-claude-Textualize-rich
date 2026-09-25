# encoding=utf-8

import io
import json

import pytest

from rich.console import Console
from rich.table import Table, TableExportError
from rich.text import Text


class CountingRenderable:
    """A renderable that counts how many times it has been rendered."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.render_count = 0

    def __rich_console__(self, console, options):
        self.render_count += 1
        yield self.text


def make_console(width: int = 60) -> Console:
    return Console(
        width=width,
        file=io.StringIO(),
        force_terminal=True,
        legacy_windows=False,
        color_system=None,
        _environ={},
    )


def test_export_values_and_single_render_per_cell():
    """Chinese, multi-line, styled, numeric and custom renderable cells."""
    table = Table("名称", "数值", "备注")
    counting = CountingRenderable("第一行\n第二行")
    table.add_row(Text("你好", style="bold red"), "placeholder", counting)
    # A plain number is not a renderable; export mirrors Console.print and
    # converts it with str().
    table.columns[1]._cells[0] = 3.5

    exported = table.export()

    assert exported == {
        "columns": [
            {"index": 0, "name": "名称"},
            {"index": 1, "name": "数值"},
            {"index": 2, "name": "备注"},
        ],
        "rows": [
            {
                "index": 0,
                "cells": {"0": "你好", "1": "3.5", "2": "第一行\n第二行"},
            }
        ],
    }
    # Each cell is rendered exactly once per export.
    assert counting.render_count == 1
    # The result is JSON-serializable.
    assert json.loads(json.dumps(exported, ensure_ascii=False)) == exported


def test_export_does_not_wrap_or_truncate():
    """Export ignores the terminal width of the console."""
    console = make_console(width=20)
    long_text = "a" * 500
    table = Table("col")
    table.add_row(long_text)
    exported = table.export(console=console)
    assert exported["rows"][0]["cells"]["0"] == long_text


def test_export_strips_styles_and_control_characters():
    table = Table("col")
    table.add_row(Text("红色", style="red on blue"))
    table.add_row("bell\x07here")
    exported = table.export()
    assert exported["rows"][0]["cells"]["0"] == "红色"
    assert exported["rows"][1]["cells"]["0"] == "bellhere"


def test_export_empty_table():
    assert Table().export() == {"columns": [], "rows": []}
    table = Table("a", "b")
    assert table.export() == {
        "columns": [{"index": 0, "name": "a"}, {"index": 1, "name": "b"}],
        "rows": [],
    }


def test_export_duplicate_column_names():
    """Duplicate column names are distinguished by column index."""
    table = Table("name", "name")
    table.add_row("first", "second")
    exported = table.export()
    assert exported["columns"] == [
        {"index": 0, "name": "name"},
        {"index": 1, "name": "name"},
    ]
    assert exported["rows"][0]["cells"] == {"0": "first", "1": "second"}


def test_export_empty_cells():
    table = Table("a", "b")
    table.add_row(None, "")
    table.add_row("x")
    exported = table.export()
    assert exported["rows"][0]["cells"] == {"0": "", "1": ""}
    assert exported["rows"][1]["cells"] == {"0": "x", "1": ""}


def test_export_max_cell_length_exceeded():
    table = Table("名称", "备注")
    table.add_row("ok", "short")
    table.add_row("fine", "this cell is way too long")
    with pytest.raises(TableExportError) as exc_info:
        table.export(max_cell_length=10)
    message = str(exc_info.value)
    assert "row 1" in message
    assert "column 1" in message
    assert "备注" in message


def test_export_max_cell_length_not_exceeded():
    table = Table("a")
    table.add_row("hello")
    exported = table.export(max_cell_length=5)
    assert exported["rows"][0]["cells"]["0"] == "hello"


def test_export_does_not_change_table_rendering():
    """The table renders identically before and after exporting."""
    console = make_console()
    table = Table("名称", "备注", show_lines=True)
    table.add_row(Text("你好", style="bold"), "第一行\n第二行")
    table.add_row("foo", "bar")

    console.print(table)
    before = console.file.getvalue()
    table.export(console=console)
    console.file.seek(0)
    console.file.truncate()
    console.print(table)
    after = console.file.getvalue()
    assert before == after
