"""Tests for rich.frame_diff: terminal frame differencing."""

import pytest

from rich.cells import cell_len, get_character_cell_size
from rich.frame_diff import (
    ClearToEndOfLine,
    FrameDiffError,
    Move,
    SimulatedTerminal,
    Write,
    diff_frames,
)
from rich.segment import Segment
from rich.style import Style


def apply_plan(old_lines, new_lines):
    """Diff two frames and apply the plan to a simulated terminal."""
    plan = diff_frames(old_lines, new_lines)
    terminal = SimulatedTerminal.from_lines(old_lines)
    terminal.apply(plan)
    return plan, terminal


def writes(plan):
    return [op for op in plan.operations if isinstance(op, Write)]


def clears(plan):
    return [op for op in plan.operations if isinstance(op, ClearToEndOfLine)]


def moves(plan):
    return [op for op in plan.operations if isinstance(op, Move)]


def test_double_width_replaced_by_two_narrow_characters():
    old = [[Segment("x中y")]]
    new = [[Segment("xaby")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert terminal.render_text() == "xaby"
    # Only the changed cells are rewritten; the untouched "x" and "y" stay.
    assert len(writes(plan)) == 1
    move = moves(plan)[0]
    assert (move.row, move.column) == (0, 1)
    assert writes(plan)[0].segments == (Segment("ab"),)


def test_shorter_line_clears_tail():
    # The second line keeps the frame width stable, so this is a line diff.
    old = [[Segment("hello world")], [Segment("abcdefghijk")]]
    new = [[Segment("hello")], [Segment("abcdefghijk")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert terminal.render_text() == "hello\nabcdefghijk"
    # A clear is emitted from the end of the new line.
    assert len(clears(plan)) == 1
    clear_move = moves(plan)[-1]
    assert (clear_move.row, clear_move.column) == (0, 5)


def test_single_line_shortened_repaints_frame():
    # Shortening the only line changes the frame width: full repaint.
    old = [[Segment("hello world")]]
    new = [[Segment("hello")]]
    plan, terminal = apply_plan(old, new)
    assert plan.full_repaint
    assert terminal.matches(new)
    assert terminal.render_text() == "hello"


def test_style_only_change_rewrites_same_text():
    old = [[Segment("plain", Style(color="red"))]]
    new = [[Segment("plain", Style(color="blue"))]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert writes(plan)[0].segments == (Segment("plain", Style(color="blue")),)


def test_partial_style_change():
    old = [[Segment("abc", Style(color="red")), Segment("def", Style(color="red"))]]
    new = [[Segment("abc", Style(color="red")), Segment("def", Style(color="green"))]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert len(writes(plan)) == 1
    assert moves(plan)[0].column == 3
    assert writes(plan)[0].segments == (Segment("def", Style(color="green")),)


def test_empty_frames():
    plan = diff_frames([], [])
    assert plan.operations == []
    assert not plan


def test_empty_old_frame_writes_new_content():
    new = [[Segment("foo")], [Segment("bar")]]
    plan = diff_frames([], new)
    terminal = SimulatedTerminal(3, 0)
    terminal.apply(plan)
    assert terminal.matches(new)
    assert terminal.render_text() == "foo\nbar"


def test_empty_new_frame_clears_old_content():
    old = [[Segment("foo")], [Segment("bar")]]
    plan, terminal = apply_plan(old, [])
    assert terminal.matches([])
    assert terminal.render_text() == "\n"
    assert len(clears(plan)) == 2


def test_trailing_spaces_removed():
    old = [[Segment("abc   ")]]
    new = [[Segment("abc")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert terminal.render_text() == "abc"
    assert len(clears(plan)) == 1


def test_trailing_spaces_added():
    old = [[Segment("abc")]]
    new = [[Segment("abc   ")]]
    plan = diff_frames(old, new)
    # A wider frame triggers a full repaint after the terminal is resized.
    assert plan.full_repaint
    terminal = SimulatedTerminal.from_lines(old)
    terminal.resize(6, 1)
    terminal.apply(plan)
    assert terminal.matches(new)
    # render_text trims trailing blanks; matches() checks the exact cells.
    assert terminal.render_text() == "abc"


def test_trailing_spaces_styled_are_significant():
    old = [[Segment("abc", None, None), Segment("  ", Style(bgcolor="red"))]]
    new = [[Segment("abc")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert clears(plan)


def test_emoji_width_uses_rich_rules():
    emoji = "\U0001F525"  # fire, two cells wide
    assert get_character_cell_size(emoji) == 2
    old = [[Segment(f"a{emoji}b")]]
    new = [[Segment("aXYb")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert terminal.render_text() == "aXYb"
    # The write starts at cell 1 and covers exactly the two emoji cells.
    move = moves(plan)[0]
    assert (move.row, move.column) == (0, 1)
    written = "".join(segment.text for segment in writes(plan)[0].segments)
    assert cell_len(written) == 2


def test_narrow_characters_replaced_by_emoji():
    emoji = "\U0001F525"
    old = [[Segment("aXYb")]]
    new = [[Segment(f"a{emoji}b")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert terminal.render_text() == f"a{emoji}b"


def test_no_half_double_width_character_left():
    # A wide character straddling the change boundary must be fully rewritten.
    old = [[Segment("ab中cd")]]
    new = [[Segment("abXYcd")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    for row in terminal.cell_rows():
        for index, (character, _style) in enumerate(row):
            if character is None:
                # A continuation cell must follow a wide character.
                previous = row[index - 1][0]
                assert previous is not None
                assert get_character_cell_size(previous) == 2
    # The span is expanded to cover the whole wide character.
    move = moves(plan)[0]
    assert (move.row, move.column) == (0, 2)
    written = "".join(segment.text for segment in writes(plan)[0].segments)
    assert written == "XY"
    assert terminal.render_text() == "abXYcd"


def test_change_before_wide_character_expands_span():
    old = [[Segment("中ab")]]
    new = [[Segment("X中b")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert terminal.render_text() == "X中b"


def test_adjacent_changes_merged_into_one_span():
    old = [[Segment("aXbYc")]]
    new = [[Segment("a1b2c")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    # "X" -> "1" and "Y" -> "2" are separated by an unchanged "b", so two spans.
    assert len(writes(plan)) == 2
    # Adjacent changes merge: rewrite "XY" as a single span.
    old2 = [[Segment("aXYc")]]
    new2 = [[Segment("a12c")]]
    plan2, terminal2 = apply_plan(old2, new2)
    assert terminal2.matches(new2)
    assert len(writes(plan2)) == 1
    assert writes(plan2)[0].segments == (Segment("12"),)


def test_unchanged_cells_not_rewritten():
    old = [[Segment("abcdef")]]
    new = [[Segment("abcXef")]]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    assert len(writes(plan)) == 1
    assert moves(plan)[0].column == 3
    assert writes(plan)[0].segments == (Segment("X"),)


def test_width_change_triggers_full_repaint():
    old = [[Segment("abc")], [Segment("def")]]
    new = [[Segment("abcdef")], [Segment("gh")]]
    plan = diff_frames(old, new)
    assert plan.full_repaint
    terminal = SimulatedTerminal.from_lines(old)
    # The terminal is resized before the repaint, as a real terminal would be.
    terminal.resize(6, 2)
    terminal.apply(plan)
    assert terminal.matches(new)


def test_width_change_repaint_clears_extra_rows():
    old = [[Segment("aaaa")], [Segment("bbbb")], [Segment("cccc")]]
    new = [[Segment("xy")]]
    plan = diff_frames(old, new)
    assert plan.full_repaint
    terminal = SimulatedTerminal.from_lines(old)
    terminal.apply(plan)
    assert terminal.matches(new)
    assert terminal.render_text() == "xy\n\n"


def test_control_segments_rejected():
    control_segment = Segment("foo", None, [("cursor_move_to", 1, 1)])
    with pytest.raises(FrameDiffError):
        diff_frames([[control_segment]], [[Segment("bar")]])
    with pytest.raises(FrameDiffError):
        diff_frames([[Segment("bar")]], [[control_segment]])


def test_newline_in_segment_rejected():
    with pytest.raises(FrameDiffError):
        diff_frames([[Segment("a\nb")]], [[Segment("ab")]])


def test_original_segments_not_modified():
    old_segments = [Segment("x中y", Style(color="red"))]
    new_segments = [Segment("xaby", Style(color="blue"))]
    old = [list(old_segments)]
    new = [list(new_segments)]
    diff_frames(old, new)
    assert old == [old_segments]
    assert new == [new_segments]


def test_multi_row_diff():
    old = [
        [Segment("one")],
        [Segment("two")],
        [Segment("three")],
    ]
    new = [
        [Segment("one")],
        [Segment("TWO")],
        [Segment("three")],
    ]
    plan, terminal = apply_plan(old, new)
    assert terminal.matches(new)
    # Only the middle row is touched.
    assert all(op.row == 1 for op in moves(plan))


def test_identical_frames_produce_empty_plan():
    frame = [[Segment("same", Style(color="red"))], [Segment("lines")]]
    plan = diff_frames(frame, frame)
    assert plan.operations == []
