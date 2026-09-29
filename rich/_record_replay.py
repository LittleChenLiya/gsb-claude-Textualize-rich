"""Replay recorded segments without the original renderable objects.

The functions in this module turn an ordered sequence of
:class:`~rich.segment.Segment` objects back in to terminal output. Two modes
are supported:

* ANSI output, where styled text and control codes are rendered as escape
  sequences for a chosen color system.
* Plain text output, where the control actions are interpreted by a small
  fixed-width virtual terminal so that the final visible screen can be read
  even on a terminal with no color support.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Union

from .cells import get_character_cell_size
from .color import ColorSystem
from .record import control_to_ansi
from .segment import ControlType, Segment

COLOR_SYSTEMS = {
    "standard": ColorSystem.STANDARD,
    "256": ColorSystem.EIGHT_BIT,
    "truecolor": ColorSystem.TRUECOLOR,
    "windows": ColorSystem.WINDOWS,
    "8bit": ColorSystem.EIGHT_BIT,
}


def replay_segments(
    segments: Sequence[Segment],
    *,
    width: int,
    color_system: Optional[Union[str, ColorSystem]],
) -> str:
    """Render recorded segments to a string containing ANSI escape codes.

    Args:
        segments: Recorded segments, in order.
        width: Fixed canvas width (used to keep the recording self
            describing; the raw output preserves the recorded layout).
        color_system: Color system name accepted by :class:`~rich.style.Style`,
            or ``None`` to strip styling entirely.

    Returns:
        str: Terminal output.
    """
    resolved_color_system: Optional[ColorSystem]
    if color_system is None:
        resolved_color_system = None
    elif isinstance(color_system, ColorSystem):
        resolved_color_system = color_system
    else:
        resolved_color_system = COLOR_SYSTEMS[color_system]

    output: List[str] = []
    append = output.append
    for text, style, control in segments:
        if control is not None:
            append(control_to_ansi(control))
        elif style is not None and resolved_color_system is not None:
            # Reset the per-Style ANSI cache so the chosen color system is
            # honored regardless of how the style was rendered before it was
            # recorded.
            style._ansi = None
            append(style.render(text, color_system=resolved_color_system))
        else:
            append(text)
    return "".join(output)


class _VirtualTerminal:
    """A minimal fixed-width terminal that tracks the visible text screen."""

    def __init__(self, width: int) -> None:
        self._width = width
        # Each line is a list of single-cell entries. A wide character (such
        # as a CJK glyph) occupies its leading cell plus a "" continuation
        # marker.
        self._lines: List[List[str]] = [[]]
        self._column = 0
        self._row = 0

    @property
    def _line(self) -> List[str]:
        while len(self._lines) <= self._row:
            self._lines.append([])
        return self._lines[self._row]

    def _clamp_cursor(self) -> None:
        if self._column > self._width - 1:
            self._column = self._width - 1
        if self._column < 0:
            self._column = 0

    def write(self, text: str) -> None:
        line = self._line
        column = self._column
        for char in text:
            if char == "\n":
                self._row += 1
                column = 0
                line = self._line
                continue
            if char == "\r":
                column = 0
                continue
            cell_size = get_character_cell_size(char)
            if column >= self._width:
                continue
            if column >= len(line):
                line.extend([" "] * (column + 1 - len(line)))
            line[column] = char
            if cell_size == 2 and column + 1 < self._width:
                if column + 1 >= len(line):
                    line.extend([" "] * (column + 2 - len(line)))
                line[column + 1] = ""
                column += 2
            else:
                column += 1
        self._column = column

    def run_control(self, code: ControlType, *parameters: Any) -> None:
        if code == ControlType.CARRIAGE_RETURN:
            self._column = 0
        elif code == ControlType.HOME:
            self._row = 0
            self._column = 0
        elif code == ControlType.CLEAR:
            self._lines = [[]]
            self._row = 0
            self._column = 0
        elif code in (ControlType.CURSOR_UP, ControlType.CURSOR_DOWN):
            (distance,) = parameters
            if code == ControlType.CURSOR_UP:
                self._row = max(0, self._row - distance)
            else:
                self._row += distance
                self._line  # grow the screen as the cursor moves down
            self._clamp_cursor()
        elif code in (
            ControlType.CURSOR_FORWARD,
            ControlType.CURSOR_BACKWARD,
        ):
            (distance,) = parameters
            if code == ControlType.CURSOR_FORWARD:
                self._column += distance
            else:
                self._column -= distance
            self._clamp_cursor()
        elif code == ControlType.CURSOR_MOVE_TO_COLUMN:
            (column,) = parameters
            self._column = column
            self._clamp_cursor()
        elif code == ControlType.CURSOR_MOVE_TO:
            column, row = parameters
            self._column = column
            self._row = row
            self._line  # grow the screen as the cursor moves down
            self._clamp_cursor()
        elif code == ControlType.ERASE_IN_LINE:
            (mode,) = parameters
            line = self._line
            column = self._column
            if mode == 0:
                start = min(column, len(line))
                for index in range(start, len(line)):
                    line[index] = " "
            elif mode == 1:
                for index in range(min(column + 1, len(line))):
                    line[index] = " "
            elif mode == 2:
                for index in range(len(line)):
                    line[index] = " "
        # BELL, SHOW/HIDE_CURSOR, alt screen and window title do not change
        # the visible text.

    def render(self) -> str:
        rendered_lines = []
        for line in self._lines:
            text = "".join(cell for cell in line if cell != "").rstrip()
            rendered_lines.append(text)
        while rendered_lines and rendered_lines[-1] == "":
            rendered_lines.pop()
        return "\n".join(rendered_lines)


def replay_segments_plain(segments: Sequence[Segment], *, width: int) -> str:
    """Interpret recorded segments against a virtual terminal (plain text).

    Args:
        segments: Recorded segments, in order.
        width: Fixed canvas width in columns.

    Returns:
        str: Final visible screen with all styling and escape codes removed.
    """
    terminal = _VirtualTerminal(width)
    for segment in segments:
        if segment.control is not None:
            for code, *parameters in segment.control:
                terminal.run_control(code, *parameters)
        else:
            terminal.write(segment.text)
    return terminal.render()
