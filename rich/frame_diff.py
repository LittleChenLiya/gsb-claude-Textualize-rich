from __future__ import annotations

from enum import IntEnum
from typing import Iterable, List, NamedTuple, Optional, Tuple

from .cells import split_graphemes
from .segment import Segment
from .style import Style


class FrameOpType(IntEnum):
    """The kind of operation in a :class:`FrameDiffPlan`.

    The operations are intentionally generic; they describe *what* to do rather than
    committing to any particular ANSI encoding.
    """

    MOVE_TO = 1
    """Move the cursor to an absolute cell position ``(x, y)`` (zero based)."""

    WRITE = 2
    """Write one or more text segments at the current cursor position."""

    ERASE_TO_LINE_END = 3
    """Erase from the current cursor position to the end of the line."""


class FrameOp(NamedTuple):
    """A single, structured frame update operation.

    Attributes:
        type: The kind of operation.
        x: Target column for ``MOVE_TO``.
        y: Target row for ``MOVE_TO``.
        segments: Text segments for ``WRITE`` (``None`` for other operations).
    """

    type: FrameOpType
    x: int = 0
    y: int = 0
    segments: Optional[List[Segment]] = None


class FrameDiffPlan(NamedTuple):
    """The result of diffing two frames.

    Applying the operations in order to a terminal showing the old frame produces
    the new frame.

    Attributes:
        full_redraw: ``True`` when the whole frame must be repainted.
        old_width: Width (in cells) of the old frame.
        new_width: Width (in cells) of the new frame.
        old_height: Number of rows in the old frame.
        new_height: Number of rows in the new frame.
        ops: Ordered operations that turn the old frame in to the new frame.
    """

    full_redraw: bool
    old_width: int
    new_width: int
    old_height: int
    new_height: int
    ops: List[FrameOp]


FrameLine = List[Segment]
Frame = List[FrameLine]


class ControlSegmentError(ValueError):
    """Raised when a frame contains a control (cursor movement) segment.

    Frame diffs operate purely on the visible cell grid, so arbitrary cursor
    control segments embedded in the text can not be handled.
    """


class _Grapheme(NamedTuple):
    text: str
    style: Optional[Style]
    start: int
    width: int


def _reject_control(lines: Iterable[List[Segment]], frame_name: str) -> None:
    for line_index, line in enumerate(lines):
        for column_index, segment in enumerate(line):
            if segment.control is not None:
                raise ControlSegmentError(
                    f"Control segments are not supported in frame diffs; found a "
                    f"control segment in the {frame_name} frame at line {line_index}, "
                    f"segment {column_index}: {segment!r}"
                )


def _flatten_line(line: List[Segment]) -> Tuple[List[_Grapheme], int]:
    """Split a line in to graphemes positioned on the cell grid."""
    graphemes: List[_Grapheme] = []
    cell_position = 0
    for segment in line:
        spans, _line_length = split_graphemes(segment.text)
        for start_index, end_index, width in spans:
            graphemes.append(
                _Grapheme(
                    segment.text[start_index:end_index],
                    segment.style,
                    cell_position,
                    width,
                )
            )
            cell_position += width
    return graphemes, cell_position


def _owners(graphemes: List[_Grapheme], length: int) -> List[int]:
    """Map each cell to the index of the grapheme that occupies it."""
    owner = [-1] * length
    for index, grapheme in enumerate(graphemes):
        for cell in range(grapheme.start, grapheme.start + grapheme.width):
            owner[cell] = index
    return owner


def _write_segments(graphemes: List[_Grapheme]) -> List[Segment]:
    """Build (possibly merged) text segments from graphemes."""
    return list(
        Segment.simplify(
            Segment(grapheme.text, grapheme.style) for grapheme in graphemes
        )
    )


def _diff_line(
    old_line: List[Segment],
    new_line: List[Segment],
    y: int,
    cursor: Optional[Tuple[int, int]],
) -> Tuple[List[FrameOp], Optional[Tuple[int, int]]]:
    """Compute the operations required to update a single line."""
    old_graphemes, old_length = _flatten_line(old_line)
    new_graphemes, new_length = _flatten_line(new_line)
    old_owners = _owners(old_graphemes, old_length)
    new_owners = _owners(new_graphemes, new_length)

    max_length = max(old_length, new_length)
    changed = bytearray(max_length)
    for cell in range(max_length):
        old_index = old_owners[cell] if cell < old_length else -1
        new_index = new_owners[cell] if cell < new_length else -1
        if old_index == -1 or new_index == -1:
            changed[cell] = 1
            continue
        old_grapheme = old_graphemes[old_index]
        new_grapheme = new_graphemes[new_index]
        # Graphemes only match when they occupy the exact same cells.
        # Per-character equality that merely coincides at one cell of two
        # differently aligned double-width glyphs is not a match.
        if old_grapheme.start != new_grapheme.start:
            changed[cell] = 1
            continue
        if (
            old_grapheme.text != new_grapheme.text
            or old_grapheme.style != new_grapheme.style
        ):
            changed[cell] = 1

    # Never split a double-width grapheme: expand changed regions so that a run
    # always starts and ends on grapheme boundaries of the new line.
    for grapheme in new_graphemes:
        if grapheme.width == 0:
            continue
        end = grapheme.start + grapheme.width
        if any(changed[cell] for cell in range(grapheme.start, end)):
            for cell in range(grapheme.start, end):
                changed[cell] = 1

    ops: List[FrameOp] = []

    # Merge adjacent changed cells in to a single rewrite run; untouched cells
    # between runs are never rewritten.
    cell = 0
    while cell < new_length:
        if not changed[cell]:
            cell += 1
            continue
        start = cell
        while cell < new_length and changed[cell]:
            cell += 1
        end = cell
        start_grapheme = new_graphemes[new_owners[start]]
        end_grapheme = new_graphemes[new_owners[end - 1]]
        start = start_grapheme.start
        end = end_grapheme.start + end_grapheme.width

        run_graphemes = [
            grapheme
            for grapheme in new_graphemes
            if start <= grapheme.start < end
            or (grapheme.width == 0 and start <= grapheme.start <= end)
        ]
        if cursor != (start, y):
            ops.append(FrameOp(FrameOpType.MOVE_TO, start, y))
        ops.append(FrameOp(FrameOpType.WRITE, start, y, _write_segments(run_graphemes)))
        cursor = (end, y)

    # The new line is shorter: remove anything left behind by the old line.
    if old_length > new_length:
        if cursor != (new_length, y):
            ops.append(FrameOp(FrameOpType.MOVE_TO, new_length, y))
        ops.append(FrameOp(FrameOpType.ERASE_TO_LINE_END, new_length, y))
        cursor = (new_length, y)

    return ops, cursor


def _full_redraw_plan(
    old_width: int,
    new_width: int,
    old_height: int,
    new_height: int,
    new_lines: Frame,
) -> FrameDiffPlan:
    """Build a plan that repaints every cell of the new frame."""
    ops: List[FrameOp] = [FrameOp(FrameOpType.MOVE_TO, 0, 0)]
    for y, line in enumerate(new_lines):
        if y > 0:
            ops.append(FrameOp(FrameOpType.MOVE_TO, 0, y))
        if line:
            ops.append(FrameOp(FrameOpType.WRITE, 0, y, list(line)))
        _graphemes, length = _flatten_line(line)
        ops.append(FrameOp(FrameOpType.MOVE_TO, length, y))
        ops.append(FrameOp(FrameOpType.ERASE_TO_LINE_END, length, y))
    # Rows that existed in the old frame but not in the new one must be cleared.
    for y in range(new_height, old_height):
        ops.append(FrameOp(FrameOpType.MOVE_TO, 0, y))
        ops.append(FrameOp(FrameOpType.ERASE_TO_LINE_END, 0, y))
    return FrameDiffPlan(True, old_width, new_width, old_height, new_height, ops)


def diff_frames(
    old: Frame,
    new: Frame,
    *,
    old_width: Optional[int] = None,
    new_width: Optional[int] = None,
) -> FrameDiffPlan:
    """Diff two frames (grids of segments) and return a minimal inline rewrite plan.

    Cells are located by terminal cell width, so double-width characters are always
    rewritten as a whole. Style changes count as changes. Adjacent changed cells in a
    line are merged in to a single write run and completely unchanged cells between
    runs are not rewritten. If the new line is shorter than the old line, a clear
    operation removes the trailing residue. No attempt is made to find a globally
    optimal ANSI encoding across rows.

    Args:
        old: The old frame, as a list of lines (each line a list of segments
            without newlines or control segments).
        new: The new frame, in the same format.
        old_width: Width of the old frame in cells. Defaults to the widest line.
        new_width: Width of the new frame in cells. Defaults to the widest line.

    Raises:
        ControlSegmentError: If either frame contains a control segment.

    Returns:
        FrameDiffPlan: Structured move, write and erase operations.
    """
    _reject_control(old, "old")
    _reject_control(new, "new")

    old_height = len(old)
    new_height = len(new)
    if old_width is None:
        old_width = max((Segment.get_line_length(line) for line in old), default=0)
    if new_width is None:
        new_width = max((Segment.get_line_length(line) for line in new), default=0)

    # A geometry change makes incremental updates unsafe; repaint everything.
    if old_width != new_width:
        return _full_redraw_plan(old_width, new_width, old_height, new_height, new)

    ops: List[FrameOp] = []
    cursor: Optional[Tuple[int, int]] = None
    for y in range(max(old_height, new_height)):
        old_line = old[y] if y < old_height else []
        new_line = new[y] if y < new_height else []
        line_ops, cursor = _diff_line(old_line, new_line, y, cursor)
        ops.extend(line_ops)

    return FrameDiffPlan(False, old_width, new_width, old_height, new_height, ops)


if __name__ == "__main__":  # pragma: no cover
    from .console import Console
    from .segment import Segments

    console = Console(force_terminal=True)

    examples = [
        (
            "Chinese character replaced by two narrow characters",
            [(None, ["中ab"])],
            [(None, ["xyab"])],
        ),
        (
            "one line shortened (trailing residue cleared)",
            [(None, ["hello"]), (None, ["world"])],
            [(None, ["hi"]), (None, ["world"])],
        ),
        (
            "only the color changes",
            [("red", ["hello"]), (None, ["world"])],
            [("green", ["hello"]), (None, ["world"])],
        ),
    ]

    def _frame(rows):
        return [
            [
                Segment(text, console.get_style(style) if style else None)
                for text in parts
            ]
            for style, parts in rows
        ]

    for title, before_rows, after_rows in examples:
        before = _frame(before_rows)
        after = _frame(after_rows)
        console.rule(title)
        console.print("before:")
        for line in before:
            console.print(Segments(line))
        console.print("after:")
        for line in after:
            console.print(Segments(line))
        plan = diff_frames(before, after)
        console.print(plan)
        console.print()
