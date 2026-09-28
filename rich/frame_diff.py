"""Terminal frame differencing.

This module implements a standalone component that computes the minimal set of
per-line rewrite operations required to turn one rendered frame (a grid of
Segment lines) in to another frame.

Positions are expressed in terminal *cells*, so double-width characters are
never partially overwritten: any change that touches one half of a wide
character is expanded to cover the whole character. Style changes count as
changes, and lines that become shorter emit an explicit clear so no residue
from the old frame is left behind.

The component does not try to find a globally optimal ANSI encoding across
lines; it returns structured move / write / clear instructions instead. A
SimulatedTerminal is included so plans can be applied and verified
without depending on a real terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from .cells import cell_len, get_character_cell_size
from .segment import Segment
from .style import Style

__all__ = [
    "FrameDiffError",
    "Move",
    "Write",
    "ClearToEndOfLine",
    "Operation",
    "FrameDiffPlan",
    "SimulatedTerminal",
    "diff_frames",
]


class FrameDiffError(Exception):
    """Raised when a frame cannot be diffed.

    Frames must consist of plain text segments; segments carrying control
    codes (or embedded newlines) are rejected.
    """


@dataclass(frozen=True)
class Move:
    """Move the cursor to a cell position (0-based row and column)."""

    row: int
    column: int


@dataclass(frozen=True)
class Write:
    """Write segments at the current cursor position."""

    segments: Tuple[Segment, ...]


@dataclass(frozen=True)
class ClearToEndOfLine:
    """Clear cells from the cursor position to the end of the line."""


Operation = Union[Move, Write, ClearToEndOfLine]


@dataclass
class FrameDiffPlan:
    """A structured list of operations that turns an old frame in to a new one."""

    operations: List[Operation] = field(default_factory=list)
    full_repaint: bool = False

    def __bool__(self) -> bool:
        return bool(self.operations)

    def __iter__(self):
        return iter(self.operations)


# A cell is a (character, style) tuple; a character of None marks the
# continuation cell of a double-width character.
_Cell = Tuple[Optional[str], Optional[Style]]
_BLANK: _Cell = (" ", None)


def _validate_frame(lines: Sequence[Sequence[Segment]], name: str) -> None:
    for line in lines:
        for segment in line:
            if segment.is_control:
                raise FrameDiffError(
                    f"{name} frame contains a control segment: {segment!r}"
                )
            text = segment.text
            if "\n" in text or "\r" in text:
                raise FrameDiffError(
                    f"{name} frame contains a segment with a line break: {segment!r}"
                )


def _expand_line(line: Sequence[Segment]) -> List[_Cell]:
    """Expand a line of segments in to a list of per-cell tuples.

    Zero-width characters (such as combining marks) are attached to the
    cell they combine with, following Rich's cell width rules.
    """
    cells: List[_Cell] = []
    pending = ""
    for segment in line:
        text, style, _ = segment
        for character in text:
            cell_size = get_character_cell_size(character)
            if cell_size == 0:
                for index in range(len(cells) - 1, -1, -1):
                    previous, previous_style = cells[index]
                    if previous is not None:
                        cells[index] = (previous + character, previous_style)
                        break
                else:
                    pending += character
                continue
            cells.append((pending + character, style))
            pending = ""
            for _ in range(cell_size - 1):
                cells.append((None, style))
    return cells


def _line_length(line: Sequence[Segment]) -> int:
    return sum(segment.cell_length for segment in line)


def _frame_width(lines: Sequence[Sequence[Segment]]) -> int:
    return max((_line_length(line) for line in lines), default=0)


def _changed_spans(old_cells: List[_Cell], new_cells: List[_Cell]) -> List[Tuple[int, int]]:
    """Find merged (start, end) cell spans that differ between two lines."""
    width = max(len(old_cells), len(new_cells))
    old_padded = old_cells + [_BLANK] * (width - len(old_cells))
    new_padded = new_cells + [_BLANK] * (width - len(new_cells))

    spans: List[List[int]] = []
    start: Optional[int] = None
    for index in range(width):
        if old_padded[index] != new_padded[index]:
            if start is None:
                start = index
        elif start is not None:
            spans.append([start, index])
            start = None
    if start is not None:
        spans.append([start, width])

    # Expand spans so they never cut a double-width character in half.
    for span in spans:
        span_start, span_end = span
        while span_start > 0 and (
            old_padded[span_start][0] is None or new_padded[span_start][0] is None
        ):
            span_start -= 1
        while span_end < width and (
            old_padded[span_end][0] is None or new_padded[span_end][0] is None
        ):
            span_end += 1
        span[0], span[1] = span_start, span_end

    # Merge spans that now overlap or touch after expansion.
    merged: List[Tuple[int, int]] = []
    for span_start, span_end in spans:
        if merged and span_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], span_end))
        else:
            merged.append((span_start, span_end))
    return merged


def _crop_line(line: Sequence[Segment], start: int, end: int) -> List[Segment]:
    """Crop a line of segments to the cell range [start, end)."""
    if end <= start:
        return []
    if start == 0 and end >= _line_length(line):
        return [segment for segment in line if segment.text]
    divided = list(Segment.divide(line, [start, end]))
    middle = divided[1] if len(divided) > 1 else []
    return [segment for segment in middle if segment.text]


def _repaint_plan(
    old_lines: Sequence[Sequence[Segment]], new_lines: Sequence[Sequence[Segment]]
) -> FrameDiffPlan:
    """Build a full repaint plan, used when the frame width has changed."""
    plan = FrameDiffPlan(full_repaint=True)
    operations = plan.operations
    for row, line in enumerate(new_lines):
        operations.append(Move(row, 0))
        segments = tuple(segment for segment in line if segment.text)
        if segments:
            operations.append(Write(segments))
        operations.append(ClearToEndOfLine())
    for row in range(len(new_lines), len(old_lines)):
        operations.append(Move(row, 0))
        operations.append(ClearToEndOfLine())
    return plan


def diff_frames(
    old_lines: Sequence[Sequence[Segment]], new_lines: Sequence[Sequence[Segment]]
) -> FrameDiffPlan:
    """Compute a plan that rewrites *old_lines* in to *new_lines*.

    Args:
        old_lines: The currently displayed frame, as a list of lines of segments.
        new_lines: The desired frame, as a list of lines of segments.

    Returns:
        A FrameDiffPlan with structured move / write / clear operations.

    Raises:
        FrameDiffError: If either frame contains control segments or line breaks.
    """
    old = [list(line) for line in old_lines]
    new = [list(line) for line in new_lines]
    _validate_frame(old, "old")
    _validate_frame(new, "new")

    if old and new and _frame_width(old) != _frame_width(new):
        return _repaint_plan(old, new)

    plan = FrameDiffPlan()
    operations = plan.operations
    row_count = max(len(old), len(new))
    for row in range(row_count):
        if row >= len(new):
            operations.append(Move(row, 0))
            operations.append(ClearToEndOfLine())
            continue
        if row >= len(old):
            operations.append(Move(row, 0))
            segments = tuple(segment for segment in new[row] if segment.text)
            if segments:
                operations.append(Write(segments))
            continue

        old_cells = _expand_line(old[row])
        new_cells = _expand_line(new[row])
        new_length = len(new_cells)
        for start, end in _changed_spans(old_cells, new_cells):
            segments = _crop_line(new[row], start, min(end, new_length))
            if segments:
                operations.append(Move(row, start))
                operations.append(Write(tuple(segments)))
        if len(old_cells) > new_length:
            operations.append(Move(row, new_length))
            operations.append(ClearToEndOfLine())
    return plan


class SimulatedTerminal:
    """A minimal cell-based terminal used to apply and verify diff plans.

    The terminal tracks a grid of (character, style) cells plus a cursor, and
    understands the three plan operations. It models double-width characters
    the way a real terminal does: overwriting one half of a wide character
    blanks the other half.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._cells: List[List[_Cell]] = [
            [_BLANK] * width for _ in range(height)
        ]
        self.cursor_row = 0
        self.cursor_column = 0

    @classmethod
    def from_lines(
        cls, lines: Sequence[Sequence[Segment]], height: Optional[int] = None
    ) -> "SimulatedTerminal":
        """Create a terminal displaying the given frame."""
        width = _frame_width(lines)
        terminal = cls(width, max(len(lines), height or 0))
        for row, line in enumerate(lines):
            terminal.cursor_row = row
            terminal.cursor_column = 0
            terminal._write_segments(line)
        terminal.cursor_row = 0
        terminal.cursor_column = 0
        return terminal

    def _grow_to(self, row: int) -> None:
        while self.height <= row:
            self._cells.append([_BLANK] * self.width)
            self.height += 1

    def resize(self, width: int, height: int) -> None:
        """Resize the terminal, preserving cells that still fit."""
        for row in self._cells:
            if len(row) < width:
                row.extend([_BLANK] * (width - len(row)))
            else:
                del row[width:]
        self.width = width
        self._grow_to(height - 1)
        del self._cells[height:]
        self.height = height

    def _put_character(self, character: str, style: Optional[Style]) -> None:
        row = self.cursor_row
        column = self.cursor_column
        self._grow_to(row)
        cell_size = get_character_cell_size(character)
        if cell_size == 0:
            # Zero-width characters combine with the previous cell.
            for index in range(column - 1, -1, -1):
                previous, previous_style = self._cells[row][index]
                if previous is not None:
                    self._cells[row][index] = (previous + character, previous_style)
                    break
            return
        if column >= self.width:
            return
        # Overwriting half of an existing wide character blanks the other half.
        existing, _ = self._cells[row][column]
        if existing is None:
            self._cells[row][column - 1] = _BLANK
        elif cell_len(existing) == 2 and column + 1 < self.width:
            self._cells[row][column + 1] = _BLANK
        if cell_size == 2 and column + 1 >= self.width:
            # A wide character does not fit in the last column; leave a blank.
            self._cells[row][column] = _BLANK
            self.cursor_column += 1
            return
        self._cells[row][column] = (character, style)
        if cell_size == 2:
            following, _ = self._cells[row][column + 1]
            if following is not None and cell_len(following) == 2 and column + 2 < self.width:
                self._cells[row][column + 2] = _BLANK
            self._cells[row][column + 1] = (None, style)
        self.cursor_column += cell_size

    def _write_segments(self, segments: Sequence[Segment]) -> None:
        for segment in segments:
            text, style, _ = segment
            for character in text:
                self._put_character(character, style)

    def _clear_to_end_of_line(self) -> None:
        row = self.cursor_row
        self._grow_to(row)
        column = self.cursor_column
        if column < self.width and self._cells[row][column][0] is None:
            # Cursor sits on the second half of a wide character.
            self._cells[row][column - 1] = _BLANK
        for index in range(column, self.width):
            self._cells[row][index] = _BLANK

    def apply(self, plan: FrameDiffPlan) -> None:
        """Apply a diff plan to this terminal."""
        for operation in plan.operations:
            if isinstance(operation, Move):
                self.cursor_row = operation.row
                self.cursor_column = operation.column
                self._grow_to(operation.row)
            elif isinstance(operation, Write):
                self._write_segments(operation.segments)
            elif isinstance(operation, ClearToEndOfLine):
                self._clear_to_end_of_line()
            else:  # pragma: no cover - defensive
                raise TypeError(f"unknown operation: {operation!r}")

    def cell_rows(self) -> List[List[_Cell]]:
        """Return the grid of (character, style) cells."""
        return [list(row) for row in self._cells]

    def matches(self, lines: Sequence[Sequence[Segment]]) -> bool:
        """Check the terminal displays exactly the given frame."""
        expected = [_expand_line(line) for line in lines]
        row_count = max(len(expected), self.height)
        for row in range(row_count):
            expected_row = expected[row] if row < len(expected) else []
            actual_row = self._cells[row] if row < self.height else []
            padded = expected_row + [_BLANK] * (self.width - len(expected_row))
            if list(actual_row) != padded:
                return False
        return True

    def to_lines(self) -> List[List[Segment]]:
        """Render the grid back to lines of segments (trailing blanks trimmed)."""
        lines: List[List[Segment]] = []
        for row in self._cells:
            segments: List[Segment] = []
            text_parts: List[str] = []
            current_style: Optional[Style] = None
            for character, style in row:
                if character is None:
                    continue
                if style != current_style and text_parts:
                    segments.append(Segment("".join(text_parts), current_style))
                    text_parts = []
                current_style = style
                text_parts.append(character)
            if text_parts:
                segments.append(Segment("".join(text_parts), current_style))
            if segments and segments[-1].style is None:
                trimmed = segments[-1].text.rstrip(" ")
                if trimmed:
                    segments[-1] = Segment(trimmed)
                else:
                    segments.pop()
            lines.append(segments)
        while lines and not lines[-1]:
            lines.pop()
        return lines

    def render_text(self) -> str:
        """Render the grid as plain text, one string per row.

        Trailing blank cells are trimmed from each row.
        """
        rows = []
        for row in self._cells:
            end = len(row)
            while end > 0 and row[end - 1] == _BLANK:
                end -= 1
            rows.append(
                "".join(character for character, _ in row[:end] if character is not None)
            )
        return "\n".join(rows)
