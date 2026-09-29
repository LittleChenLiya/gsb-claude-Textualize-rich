"""Record and replay console output as JSON Lines of segment events.

This module provides a safe, replayable export format for recorded
:class:``~rich.console.Console` output. A recording is stored as JSON Lines
(JSONL): a header line recording the format version and the fixed canvas
width, followed by one JSON object per :class:``~rich.segment.Segment` event
with a monotonically increasing sequence number.

The format is pure JSON -- no executable code is ever emitted or evaluated.
Importing validates every line: the version, style fields and control codes
are checked against a whitelist, and any corruption raises
:class:`ReplayError` identifying the offending line number.

Replay does not require the original renderable objects; events may be
rendered either as ANSI escape sequences (honoring the color capabilities of
the target terminal) or as plain text on a simulated fixed-width canvas.
"""

import io
import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .cells import get_character_cell_size
from .errors import StyleSyntaxError
from .segment import ControlCode, ControlType, Segment
from .style import Style

__all__ = [
    "REPLAY_FORMAT",
    "REPLAY_VERSION",
    "ReplayError",
    "dump_segments",
    "load_segments",
    "replay_ansi",
    "replay_text",
]

REPLAY_FORMAT = "rich-replay"
REPLAY_VERSION = 1

# Whitelist of control codes permitted in a recording, mapped to the
# expected parameter types (used to validate imported events).
_CONTROL_PARAMETER_TYPES: Dict[ControlType, Tuple[type, ...]] = {
    ControlType.BELL: (),
    ControlType.CARRIAGE_RETURN: (),
    ControlType.HOME: (),
    ControlType.CLEAR: (),
    ControlType.SHOW_CURSOR: (),
    ControlType.HIDE_CURSOR: (),
    ControlType.ENABLE_ALT_SCREEN: (),
    ControlType.DISABLE_ALT_SCREEN: (),
    ControlType.CURSOR_UP: (int,),
    ControlType.CURSOR_DOWN: (int,),
    ControlType.CURSOR_FORWARD: (int,),
    ControlType.CURSOR_BACKWARD: (int,),
    ControlType.CURSOR_MOVE_TO_COLUMN: (int,),
    ControlType.CURSOR_MOVE_TO: (int, int),
    ControlType.ERASE_IN_LINE: (int,),
    ControlType.SET_WINDOW_TITLE: (str,),
}

_CONTROL_TYPES_BY_NAME: Dict[str, ControlType] = {
    control_type.name: control_type for control_type in _CONTROL_PARAMETER_TYPES
}

_EVENT_KEYS = frozenset({"seq", "text", "style", "control"})


class ReplayError(Exception):
    """Raised when a recording cannot be imported or replayed.

    Attributes:
        line_no (int): The 1-based line number of the offending record.
    """

    def __init__(self, line_no: int, message: str) -> None:
        self.line_no = line_no
        super().__init__(f"line {line_no}: {message}")


def _is_int(value: object) -> bool:
    """Check a value is an int (but not a bool, which JSON conflates)."""
    return isinstance(value, int) and not isinstance(value, bool)


def dump_segments(segments: Iterable[Segment], width: int) -> str:
    """Serialize segments to the JSONL replay format.

    Args:
        segments (Iterable[Segment]): The segments to serialize.
        width (int): The fixed canvas width the events were recorded at.

    Returns:
        str: A JSON Lines document with a header line followed by one
            event per segment, numbered from 1 with monotonically
            increasing sequence numbers.
    """
    lines = [
        json.dumps(
            {"format": REPLAY_FORMAT, "version": REPLAY_VERSION, "width": width},
            ensure_ascii=False,
        )
    ]
    append = lines.append
    for seq, segment in enumerate(segments, start=1):
        text, style, control = segment
        event = {
            "seq": seq,
            "text": text,
            "style": None if style is None else str(style),
            "control": (
                None
                if control is None
                else [
                    [control_type.name, *parameters]
                    for control_type, *parameters in control
                ]
            ),
        }
        append(json.dumps(event, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def load_segments(data: str) -> Tuple[int, List[Segment]]:
    """Load and validate segments from the JSONL replay format.

    Every line is validated: the header version, the monotonically
    increasing sequence numbers, style fields and the control code
    whitelist. Any corruption aborts the import.

    Args:
        data (str): The JSON Lines document to load.

    Raises:
        ReplayError: If any line fails validation; the error identifies
            the offending line number.

    Returns:
        Tuple[int, List[Segment]]: The canvas width and the segments.
    """
    width: Optional[int] = None
    segments: List[Segment] = []
    expected_seq = 1
    for line_no, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            raise ReplayError(line_no, "unexpected blank line")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReplayError(line_no, f"invalid JSON ({error.msg})") from None
        if not isinstance(record, dict):
            raise ReplayError(line_no, "expected a JSON object")
        if line_no == 1:
            width = _parse_header(record, line_no)
        else:
            segments.append(_parse_event(record, line_no, expected_seq))
            expected_seq += 1
    if width is None:
        raise ReplayError(1, "missing header line")
    return width, segments


def _parse_header(record: Dict[str, object], line_no: int) -> int:
    """Validate the header line and return the canvas width."""
    if record.get("format") != REPLAY_FORMAT:
        raise ReplayError(line_no, "missing or invalid 'format' marker")
    version = record.get("version")
    if not _is_int(version):
        raise ReplayError(line_no, "missing or invalid 'version'")
    if version != REPLAY_VERSION:
        raise ReplayError(
            line_no,
            f"unsupported version {version!r} (expected {REPLAY_VERSION})",
        )
    width = record.get("width")
    if not _is_int(width) or width <= 0:
        raise ReplayError(line_no, "missing or invalid 'width'")
    return width  # type: ignore[return-value]


def _parse_event(record: Dict[str, object], line_no: int, expected_seq: int) -> Segment:
    """Validate a single event line and convert it to a Segment."""
    unknown_keys = sorted(set(record) - _EVENT_KEYS)
    if unknown_keys:
        raise ReplayError(line_no, f"unexpected field(s): {', '.join(unknown_keys)}")
    seq = record.get("seq")
    if not _is_int(seq):
        raise ReplayError(line_no, "missing or invalid 'seq'")
    if seq != expected_seq:
        raise ReplayError(line_no, f"out-of-order seq {seq}, expected {expected_seq}")
    text = record.get("text")
    if not isinstance(text, str):
        raise ReplayError(line_no, "missing or invalid 'text'")
    style = _parse_style(record.get("style"), line_no)
    control = _parse_control(record.get("control"), line_no)
    return Segment(text, style, control)


def _parse_style(value: object, line_no: int) -> Optional[Style]:
    """Validate and parse a style field."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReplayError(line_no, "'style' must be a string or null")
    try:
        return Style.parse(value)
    except StyleSyntaxError as error:
        raise ReplayError(line_no, f"invalid style: {error}") from None


def _parse_control(value: object, line_no: int) -> Optional[List[ControlCode]]:
    """Validate control codes against the whitelist."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ReplayError(line_no, "'control' must be a list or null")
    control_codes: List[ControlCode] = []
    for item in value:
        if not isinstance(item, list) or not item:
            raise ReplayError(line_no, "control code must be a non-empty list")
        name, *parameters = item
        control_type = (
            _CONTROL_TYPES_BY_NAME.get(name) if isinstance(name, str) else None
        )
        if control_type is None:
            raise ReplayError(line_no, f"unknown control code {name!r}")
        expected_types = _CONTROL_PARAMETER_TYPES[control_type]
        if len(parameters) != len(expected_types):
            raise ReplayError(
                line_no,
                f"control code {name!r} expects {len(expected_types)} "
                f"parameter(s), got {len(parameters)}",
            )
        for parameter, expected_type in zip(parameters, expected_types):
            if expected_type is int:
                if not _is_int(parameter) or parameter < 0:
                    raise ReplayError(
                        line_no,
                        f"control code {name!r} expects a non-negative "
                        f"integer parameter, got {parameter!r}",
                    )
            elif not isinstance(parameter, str) or _has_unsafe_characters(parameter):
                raise ReplayError(
                    line_no,
                    f"control code {name!r} expects a plain string parameter",
                )
        control_codes.append(tuple([control_type, *parameters]))  # type: ignore[arg-type]
    return control_codes


def _has_unsafe_characters(text: str) -> bool:
    """Check a string parameter for characters that could inject escape codes."""
    return any(ord(character) < 32 or ord(character) == 0x7F for character in text)


def replay_ansi(
    segments: Iterable[Segment],
    *,
    color_system: Optional[str] = "truecolor",
    no_color: bool = False,
    width: int = 80,
) -> str:
    """Replay segments as a string of ANSI escape sequences.

    The output honors the requested color capabilities; on a terminal
    without color support (`no_color=True` or `color_system=None`)
    the output contains no color codes and remains readable.

    Args:
        segments (Iterable[Segment]): The segments to replay.
        color_system (str, optional): Color system to render for, one of
            `"standard"`, `"256"`, `"truecolor"` or `None` for no
            color support. Defaults to `"truecolor"`.
        no_color (bool, optional): Strip all color from the output.
            Defaults to `False`.
        width (int, optional): Canvas width of the replay console.
            Defaults to 80.

    Returns:
        str: The segments rendered as ANSI escape sequences.
    """
    from .console import Console

    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        color_system=color_system,  # type: ignore[arg-type]
        no_color=no_color,
        width=width,
        legacy_windows=False,
    )
    return console._render_buffer(list(segments))


def replay_text(segments: Iterable[Segment], width: int = 80) -> str:
    """Replay segments as plain text on a simulated fixed-width canvas.

    Control codes (cursor movement, erase, clear) are applied to the
    canvas so the result reflects the final visible frame; no ANSI
    escape sequences appear in the output.

    Args:
        segments (Iterable[Segment]): The segments to replay.
        width (int, optional): Canvas width in terminal cells.
            Defaults to 80.

    Returns:
        str: The final canvas contents as plain text.
    """
    canvas = _Canvas(width)
    for segment in segments:
        if segment.control:
            canvas.apply_control(segment.control)
        else:
            canvas.write_text(segment.text)
    return canvas.getvalue()


class _Canvas:
    """A minimal fixed-width terminal canvas for plain-text replay."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.lines: List[List[str]] = [[]]
        self.x = 0
        self.y = 0

    def _ensure_line(self) -> None:
        while len(self.lines) <= self.y:
            self.lines.append([])

    def write_text(self, text: str) -> None:
        """Write printable text at the cursor position."""
        for character in text:
            if character == "\n":
                self.y += 1
                self.x = 0
                self._ensure_line()
                continue
            if character == "\r":
                self.x = 0
                continue
            cell_size = get_character_cell_size(character)
            if cell_size == 0:
                continue
            if self.x + cell_size > self.width:
                self.y += 1
                self.x = 0
            self._ensure_line()
            line = self.lines[self.y]
            while len(line) < self.x:
                line.append(" ")
            if self.x == len(line):
                line.append(character)
            else:
                line[self.x] = character
            if cell_size == 2:
                if self.x + 1 == len(line):
                    line.append("")
                else:
                    line[self.x + 1] = ""
            self.x += cell_size

    def apply_control(self, control_codes: Sequence[ControlCode]) -> None:
        """Apply control codes that affect the canvas."""
        for control_code in control_codes:
            code = control_code[0]
            parameters = control_code[1:]
            if code == ControlType.CARRIAGE_RETURN:
                self.x = 0
            elif code == ControlType.HOME:
                self.x = 0
                self.y = 0
            elif code == ControlType.CLEAR:
                self.lines = [[]]
                self.x = 0
                self.y = 0
            elif code == ControlType.CURSOR_UP:
                self.y = max(0, self.y - int(parameters[0]))
            elif code == ControlType.CURSOR_DOWN:
                self.y += int(parameters[0])
                self._ensure_line()
            elif code == ControlType.CURSOR_FORWARD:
                self.x = min(self.width, self.x + int(parameters[0]))
            elif code == ControlType.CURSOR_BACKWARD:
                self.x = max(0, self.x - int(parameters[0]))
            elif code == ControlType.CURSOR_MOVE_TO_COLUMN:
                self.x = min(self.width, max(0, int(parameters[0])))
            elif code == ControlType.CURSOR_MOVE_TO:
                self.x = min(self.width, max(0, int(parameters[0])))
                self.y = max(0, int(parameters[1]))
                self._ensure_line()
            elif code == ControlType.ERASE_IN_LINE:
                self._erase_in_line(int(parameters[0]))
            # BELL, SHOW_CURSOR, HIDE_CURSOR, ENABLE_ALT_SCREEN,
            # DISABLE_ALT_SCREEN and SET_WINDOW_TITLE have no canvas effect.

    def _erase_in_line(self, parameter: int) -> None:
        self._ensure_line()
        line = self.lines[self.y]
        if parameter == 0:
            del line[self.x :]
        elif parameter == 1:
            for index in range(min(self.x + 1, len(line))):
                line[index] = " "
        else:
            del line[:]

    def getvalue(self) -> str:
        """Return the final canvas contents as plain text."""
        lines = ["".join(line).rstrip() for line in self.lines]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)
