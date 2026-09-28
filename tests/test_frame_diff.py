import random

import pytest

from rich.cells import cell_len, get_character_cell_size, split_graphemes
from rich.control import Control
from rich.frame_diff import (
    ControlSegmentError,
    FrameDiffPlan,
    FrameOp,
    FrameOpType,
    diff_frames,
)
from rich.segment import Segment
from rich.style import Style


class SimulatedTerminal:
    """A width-aware cell grid simulator (no real terminal required)."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cells = [[None] * width for _ in range(height)]
        self.x = 0
        self.y = 0

    def apply(self, plan):
        for op in plan.ops:
            if op.type == FrameOpType.MOVE_TO:
                self.x, self.y = op.x, op.y
            elif op.type == FrameOpType.WRITE:
                self._write(op.segments)
            elif op.type == FrameOpType.ERASE_TO_LINE_END:
                self._erase()

    def _write(self, segments):
        for segment in segments:
            assert not segment.control
            spans, _length = split_graphemes(segment.text)
            for start, end, width in spans:
                text = segment.text[start:end]
                if width == 0:
                    continue
                # Writing into the second cell of a standing double-width
                # character must never leave half of it behind.
                if (
                    self.x > 0
                    and self.cells[self.y][self.x] is not None
                    and self.cells[self.y][self.x - 1] is None
                ):
                    self.cells[self.y][self.x] = None
                for cell in range(width):
                    if self.x + cell < self.width:
                        self.cells[self.y][self.x + cell] = (text, segment.style)
                for cell in range(1, width):
                    if self.x + cell < self.width:
                        self.cells[self.y][self.x + cell] = None
                self.x += width

    def _erase(self):
        for cell in range(self.x, self.width):
            self.cells[self.y][cell] = None
        self.x = self.width

    def _render_frame(self, frame, width, height):
        expected = [[None] * width for _ in range(height)]
        for y, line in enumerate(frame):
            x = 0
            for segment in line:
                assert not segment.control
                spans, _length = split_graphemes(segment.text)
                for start, end, glyph_width in spans:
                    if glyph_width == 0:
                        continue
                    text = segment.text[start:end]
                    expected[y][x] = (text, segment.style)
                    for cell in range(1, glyph_width):
                        expected[y][x + cell] = None
                    x += glyph_width
        return expected

    def paint_initial(self, frame):
        self.cells = self._render_frame(frame, self.width, self.height)

    def assert_matches(self, frame, width, height):
        expected = self._render_frame(frame, width, height)
        assert self.cells == expected

        # No half double-width characters anywhere: every occupied cell must
        # either start a glyph or be the continuation cell of one.
        for y in range(height):
            for x in range(width):
                cell = self.cells[y][x]
                if cell is None:
                    continue
                text, _style = cell
                glyph_width = get_character_cell_size(text[0])
                if glyph_width == 2:
                    assert x + 1 < width
                    assert self.cells[y][x + 1] is None
                elif x > 0:
                    previous = self.cells[y][x - 1]
                    assert not (
                        previous is not None
                        and get_character_cell_size(previous[0][0]) == 2
                    )


def _run(old, new, width, height, **kwargs):
    plan = diff_frames(old, new, **kwargs)
    terminal = SimulatedTerminal(width, height)
    terminal.paint_initial(old)
    terminal.apply(plan)
    terminal.assert_matches(new, width, height)
    return plan


def test_chinese_replaced_by_two_narrow_chars():
    old = [[Segment("中ab")]]
    new = [[Segment("xyab")]]
    plan = _run(old, new, 4, 1)
    assert plan.full_redraw is False
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 0, 0),
        FrameOp(FrameOpType.WRITE, 0, 0, [Segment("xy")]),
    ]


def test_narrow_replaced_by_double_width():
    old = [[Segment("xyab")]]
    new = [[Segment("中ab")]]
    plan = _run(old, new, 4, 1)
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 0, 0),
        FrameOp(FrameOpType.WRITE, 0, 0, [Segment("中")]),
    ]


def test_line_shortened_clears_tail():
    old = [[Segment("hello")], [Segment("world")]]
    new = [[Segment("hi")], [Segment("world")]]
    plan = _run(old, new, 5, 2)
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 1, 0),
        FrameOp(FrameOpType.WRITE, 1, 0, [Segment("i")]),
        FrameOp(FrameOpType.ERASE_TO_LINE_END, 2, 0),
    ]


def test_line_shortened_double_width_tail():
    old = [[Segment("a中")]]
    new = [[Segment("a")]]
    plan = _run(old, new, 3, 1, old_width=3, new_width=3)
    assert plan.full_redraw is False
    assert FrameOpType.ERASE_TO_LINE_END in [op.type for op in plan.ops]
    # Only erasing is required; the double-width character is never
    # partially overwritten by a write.
    assert [op for op in plan.ops if op.type == FrameOpType.WRITE] == []


def test_only_color_changes():
    old = [[Segment("hello", Style(color="red"))]]
    new = [[Segment("hello", Style(color="green"))]]
    plan = _run(old, new, 5, 1)
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 0, 0),
        FrameOp(FrameOpType.WRITE, 0, 0, [Segment("hello", Style(color="green"))]),
    ]


def test_unchanged_frame_is_noop():
    old = [[Segment("abc")]]
    new = [[Segment("abc")]]
    assert diff_frames(old, new).ops == []


def test_adjacent_changes_merged_untouched_gap_kept():
    old = [[Segment("abcdef")]]
    new = [[Segment("axcdef")]]
    plan = _run(old, new, 6, 1)
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 1, 0),
        FrameOp(FrameOpType.WRITE, 1, 0, [Segment("x")]),
    ]

    new = [[Segment("xbydez")]]
    plan = _run(old, new, 6, 1)
    write_ops = [op for op in plan.ops if op.type == FrameOpType.WRITE]
    assert [op.x for op in write_ops] == [0, 2, 5]
    assert [op.segments for op in write_ops] == [
        [Segment("x")],
        [Segment("y")],
        [Segment("z")],
    ]


def test_style_change_is_change():
    old = [[Segment("abcdef", Style(bold=True))]]
    new = [
        [
            Segment("ab", Style(bold=True)),
            Segment("cd", Style(bold=True, color="blue")),
            Segment("ef", Style(bold=True)),
        ]
    ]
    plan = _run(old, new, 6, 1)
    write_ops = [op for op in plan.ops if op.type == FrameOpType.WRITE]
    assert [op.x for op in write_ops] == [2]
    assert write_ops[0].segments == [Segment("cd", Style(bold=True, color="blue"))]


def test_empty_frames():
    plan = diff_frames([], [])
    assert plan.ops == []
    assert plan.old_width == 0
    assert plan.new_width == 0
    _run([], [], 0, 0)


def test_empty_new_frame_clears_rows():
    old = [[Segment("abc")], [Segment("def")]]
    plan = _run(old, [], 3, 2, old_width=3, new_width=3)
    assert plan.full_redraw is False
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 0, 0),
        FrameOp(FrameOpType.ERASE_TO_LINE_END, 0, 0),
        FrameOp(FrameOpType.MOVE_TO, 0, 1),
        FrameOp(FrameOpType.ERASE_TO_LINE_END, 0, 1),
    ]


def test_trailing_spaces_are_significant():
    plan = _run([[Segment("abc")]], [[Segment("ab ")]], 3, 1)
    assert plan.ops == [
        FrameOp(FrameOpType.MOVE_TO, 2, 0),
        FrameOp(FrameOpType.WRITE, 2, 0, [Segment(" ")]),
    ]

    plan = _run([[Segment("ab ")]], [[Segment("abc")]], 3, 1)
    write_ops = [op for op in plan.ops if op.type == FrameOpType.WRITE]
    assert write_ops[0].x == 2


def test_emoji_width_uses_rich_rules():
    assert cell_len("😀") == 2
    assert cell_len("👨‍👩‍👧") == 2

    plan = _run([[Segment("a😀b")]], [[Segment("a😀x")]], 4, 1)
    write_ops = [op for op in plan.ops if op.type == FrameOpType.WRITE]
    assert [op.x for op in write_ops] == [3]
    assert write_ops[0].segments == [Segment("x")]

    plan = _run([[Segment("a👨‍👩‍👧b")]], [[Segment("a👨‍👩‍👧x")]], 4, 1)
    write_ops = [op for op in plan.ops if op.type == FrameOpType.WRITE]
    assert write_ops[0].x == 3


def test_width_change_forces_full_redraw():
    old = [[Segment("hello")]]
    new = [[Segment("hi")]]

    plan = diff_frames(old, new, old_width=5, new_width=5)
    assert plan.full_redraw is False

    plan = diff_frames(old, new)
    assert plan.full_redraw is True
    assert plan.ops[0] == FrameOp(FrameOpType.MOVE_TO, 0, 0)
    assert any(op.type == FrameOpType.ERASE_TO_LINE_END for op in plan.ops)

    terminal = SimulatedTerminal(5, 1)
    terminal.apply(plan)
    assert terminal.cells == [[("h", None), ("i", None), None, None, None]]


def test_full_redraw_clears_tail_and_extra_rows():
    old = [[Segment("hello")], [Segment("world")]]
    new = [[Segment("hi")]]
    plan = diff_frames(old, new, old_width=5, new_width=3)
    assert plan.full_redraw is True
    terminal = SimulatedTerminal(5, 2)
    terminal.apply(plan)
    assert terminal.cells == [
        [("h", None), ("i", None), None, None, None],
        [None, None, None, None, None],
    ]


def test_control_segments_rejected():
    control = Control.move_to(1, 1).segment
    with pytest.raises(ControlSegmentError):
        diff_frames([[control]], [[Segment("a")]])
    with pytest.raises(ControlSegmentError):
        diff_frames([[Segment("a")]], [[control]])


def test_inputs_not_modified():
    old = [[Segment("hello")]]
    new = [[Segment("hi")]]
    old_before = [list(line) for line in old]
    new_before = [list(line) for line in new]
    diff_frames(old, new, old_width=5, new_width=5)
    assert old == old_before
    assert new == new_before


GLYPH_POOL = ["a", "b", "c", "中", "é", "😀"]


def test_random_frames_never_leave_half_wide_chars():
    rng = random.Random(42)
    width = 8
    height = 3

    def make_frame():
        lines = []
        for _ in range(height):
            cells_left = rng.randint(0, width)
            text = ""
            while cells_left > 0:
                glyph = rng.choice(GLYPH_POOL)
                glyph_width = cell_len(glyph)
                if glyph_width > cells_left:
                    continue
                text += glyph
                cells_left -= glyph_width
            style = (
                Style(color=rng.choice(["red", "green"]))
                if rng.random() < 0.5
                else None
            )
            lines.append([Segment(text, style)])
        return lines

    for _ in range(200):
        old = make_frame()
        new = make_frame()
        _run(old, new, width, height, old_width=width, new_width=width)


def test_demo_runs_without_real_terminal():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "rich.frame_diff"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "before:" in out
    assert "after:" in out
    assert "MOVE_TO" in out
    assert "ERASE_TO_LINE_END" in out
