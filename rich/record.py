from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    TextIO,
    Tuple,
    Union,
)

from .control import CONTROL_CODES_FORMAT
from .segment import ControlCode, ControlType, Segment
from .style import Style

RECORD_FORMAT_VERSION = 1

# Printable text may contain tabs, newlines and carriage returns, but no
# other C0 control characters (which could smuggle escape sequences in to a
# replayed terminal).
_ALLOWED_TEXT_CONTROLS = frozenset("\t\n\r")

# Control actions that may appear in a recording. Each entry maps the
# numeric ControlType value to the number of additional parameters it
# takes (0, 1 or 2).
_CONTROL_ARITY: Dict[ControlType, int] = {
    ControlType.BELL: 0,
    ControlType.CARRIAGE_RETURN: 0,
    ControlType.HOME: 0,
    ControlType.CLEAR: 0,
    ControlType.SHOW_CURSOR: 0,
    ControlType.HIDE_CURSOR: 0,
    ControlType.ENABLE_ALT_SCREEN: 0,
    ControlType.DISABLE_ALT_SCREEN: 0,
    ControlType.CURSOR_UP: 1,
    ControlType.CURSOR_DOWN: 1,
    ControlType.CURSOR_FORWARD: 1,
    ControlType.CURSOR_BACKWARD: 1,
    ControlType.CURSOR_MOVE_TO_COLUMN: 1,
    ControlType.CURSOR_MOVE_TO: 2,
    ControlType.ERASE_IN_LINE: 1,
    ControlType.SET_WINDOW_TITLE: 1,
}

CONTROL_WHITELIST: Dict[int, int] = {
    int(control_type): arity for control_type, arity in _CONTROL_ARITY.items()
}


class RecordError(ValueError):
    """Raised when a JSONL recording can not be parsed.

    Attributes:
        line_number: 1-based number of the offending line in the recording,
            or None if the error is not tied to a particular line.
    """

    def __init__(self, message: str, line_number: Optional[int] = None) -> None:
        if line_number is not None:
            message = f"line {line_number}: {message}"
        super().__init__(message)
        self.line_number = line_number


@dataclass
class Recording:
    """A replayable recording of terminal output as JSONL events.

    A recording stores the fixed canvas (terminal) width and an ordered list
    of :class:`~rich.segment.Segment` objects. Segments cover printable text
    (including newlines), styled text and whitelisted control actions; no
    executable code is ever stored.

    Args:
        width: Fixed canvas width in columns.
        segments: Ordered segments making up the recording.
    """

    width: int
    segments: List[Segment] = field(default_factory=list)

    def __iter__(self) -> Iterator[Segment]:
        return iter(self.segments)

    def __len__(self) -> int:
        return len(self.segments)

    @classmethod
    def from_segments(cls, segments: Iterable[Segment], *, width: int) -> "Recording":
        """Create a recording from an iterable of segments.

        Args:
            segments: Segments to record.
            width: Fixed canvas width in columns.

        Returns:
            Recording: A new recording.
        """
        return cls(width=int(width), segments=list(segments))

    def to_jsonl(self) -> str:
        """Serialize the recording to a JSONL document.

        The first line is a header carrying the format version and the fixed
        canvas width. Every subsequent line is a single event with a sequence
        number that increases by one.

        Returns:
            str: JSONL document (ends with a newline).
        """
        lines: List[str] = [
            json.dumps(
                {"version": RECORD_FORMAT_VERSION, "width": self.width},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        ]
        for sequence, segment in enumerate(self.segments, start=1):
            event: Dict[str, Any] = {"seq": sequence}
            if segment.control is not None:
                event["control"] = [
                    [int(code), *parameters] for code, *parameters in segment.control
                ]
            else:
                event["text"] = segment.text
                if segment.style is not None:
                    style_definition = str(segment.style)
                    if style_definition:
                        event["style"] = style_definition
            lines.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        return "\n".join(lines) + "\n"

    def save(self, path: str) -> None:
        """Write the recording to a JSONL file.

        Args:
            path: Destination file path.
        """
        with open(path, "w", encoding="utf-8", newline="\n") as jsonl_file:
            jsonl_file.write(self.to_jsonl())

    @classmethod
    def load(cls, source: Union[str, TextIO]) -> "Recording":
        """Load a recording from a path or a text file object.

        Every line is validated individually; the first corrupt line aborts
        loading and raises :class:`RecordError` annotated with the line number.

        Args:
            source: A file path or an open text stream.

        Raises:
            RecordError: If any line is invalid.
        """
        if isinstance(source, str):
            with open(source, "r", encoding="utf-8") as jsonl_file:
                return cls.from_jsonl(jsonl_file)
        return cls.from_jsonl(source)

    @classmethod
    def from_jsonl(cls, lines: Iterable[str]) -> "Recording":
        """Parse a recording from an iterable of JSONL lines.

        Args:
            lines: JSONL lines, with or without trailing newlines.

        Raises:
            RecordError: If the header or any event line is invalid.
        """
        width: Optional[int] = None
        segments: List[Segment] = []
        expected_seq = 1
        saw_line = False
        for line_number, raw_line in enumerate(lines, start=1):
            saw_line = True
            line = raw_line.strip()
            if not line:
                raise RecordError("empty line", line_number)
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise RecordError(f"invalid JSON ({error.msg})", line_number) from error
            if not isinstance(event, dict):
                raise RecordError("event must be a JSON object", line_number)

            if width is None:
                width = _parse_header(event, line_number)
                continue

            segments.append(_parse_event(event, line_number, expected_seq))
            expected_seq += 1

        if not saw_line or width is None:
            raise RecordError("missing recording header")
        return cls(width=width, segments=segments)

    def replay(
        self,
        *,
        color_system: Optional[str] = "truecolor",
        no_color: bool = False,
    ) -> str:
        """Replay the recording into a terminal output string.

        Args:
            color_system: Color system used to render styles, e.g.
                "truecolor", "256", "standard" or None for plain text.
            no_color: If True, strip all styling. Control actions are still
                emitted as escape sequences, as cursor control is independent
                of color support.

        Returns:
            str: The terminal output produced by replaying the events.
        """
        from ._record_replay import replay_segments

        return replay_segments(
            self.segments,
            width=self.width,
            color_system=None if no_color else color_system,
        )

    def replay_text(self) -> str:
        """Replay the recording as plain text, interpreting control actions.

        Cursor movement, line erasure and other supported control actions are
        emulated against a fixed-width virtual terminal, so the result matches
        what a user would have seen on screen without relying on the original
        renderable objects.

        Returns:
            str: The final visible screen as plain text.
        """
        from ._record_replay import replay_segments_plain

        return replay_segments_plain(self.segments, width=self.width)


def _parse_header(event: Dict[str, Any], line_number: int) -> int:
    """Validate the header line and return the canvas width."""
    if set(event) != {"version", "width"}:
        raise RecordError(
            "header must contain exactly 'version' and 'width'", line_number
        )
    version = event["version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise RecordError("'version' must be an integer", line_number)
    if version != RECORD_FORMAT_VERSION:
        raise RecordError(
            f"unsupported recording version {version}; expected "
            f"{RECORD_FORMAT_VERSION}",
            line_number,
        )
    width = event["width"]
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise RecordError("'width' must be a positive integer", line_number)
    return width


def _parse_event(event: Dict[str, Any], line_number: int, expected_seq: int) -> Segment:
    """Validate one event line and return the segment it describes."""
    if "seq" not in event:
        raise RecordError("event missing 'seq'", line_number)
    seq = event["seq"]
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise RecordError("'seq' must be an integer", line_number)
    if seq != expected_seq:
        raise RecordError(f"expected seq {expected_seq}, found {seq}", line_number)

    keys = set(event)
    keys.discard("seq")
    if "control" in keys:
        if keys != {"control"}:
            raise RecordError(
                "control event may only contain 'seq' and 'control'",
                line_number,
            )
        return Segment("", None, _parse_control(event["control"], line_number))

    if "text" not in keys:
        raise RecordError("event must contain 'text' or 'control'", line_number)
    if not keys <= {"text", "style"}:
        raise RecordError(
            "text event may only contain 'seq', 'text' and 'style'",
            line_number,
        )
    text = event["text"]
    if not isinstance(text, str):
        raise RecordError("'text' must be a string", line_number)
    _validate_safe_text(text, line_number)
    style: Optional[Style] = None
    if "style" in keys:
        style_definition = event["style"]
        if not isinstance(style_definition, str):
            raise RecordError("'style' must be a string", line_number)
        _validate_safe_text(style_definition, line_number)
        try:
            style = Style.parse(style_definition)
        except Exception as error:
            raise RecordError(f"invalid style: {error}", line_number) from error
    return Segment(text, style)


def _validate_safe_text(text: str, line_number: int) -> None:
    """Reject control characters that could inject terminal escapes."""
    for char in text:
        codepoint = ord(char)
        is_c0 = codepoint < 0x20 and char not in _ALLOWED_TEXT_CONTROLS
        is_delete_or_c1 = 0x7F <= codepoint <= 0x9F
        if is_c0 or is_delete_or_c1:
            raise RecordError(
                f"text contains disallowed control character U+{codepoint:04X}",
                line_number,
            )


def _parse_control(value: Any, line_number: int) -> Tuple[ControlCode, ...]:
    """Validate the control field against the control whitelist."""
    if not isinstance(value, list) or not value:
        raise RecordError(
            "'control' must be a non-empty list of control codes", line_number
        )
    codes: List[ControlCode] = []
    for code_entry in value:
        if not isinstance(code_entry, list) or not code_entry:
            raise RecordError("each control code must be a non-empty list", line_number)
        control_value = code_entry[0]
        if not isinstance(control_value, int) or isinstance(control_value, bool):
            raise RecordError("control type must be an integer", line_number)
        arity = CONTROL_WHITELIST.get(control_value)
        if arity is None:
            raise RecordError(
                f"control action {control_value!r} is not allowed", line_number
            )
        parameters = code_entry[1:]
        if len(parameters) != arity:
            raise RecordError(
                f"control action {control_value} requires {arity} parameter(s)",
                line_number,
            )
        parsed_parameters: List[Any] = []
        for index, parameter in enumerate(parameters):
            if control_value == int(ControlType.SET_WINDOW_TITLE):
                if not isinstance(parameter, str):
                    raise RecordError(
                        "SET_WINDOW_TITLE parameter must be a string",
                        line_number,
                    )
                _validate_safe_text(parameter, line_number)
            else:
                if not isinstance(parameter, int) or isinstance(parameter, bool):
                    raise RecordError(
                        f"control parameter {index} must be an integer",
                        line_number,
                    )
                if parameter < 0:
                    raise RecordError(
                        f"control parameter {index} must not be negative",
                        line_number,
                    )
            parsed_parameters.append(parameter)
        codes.append((ControlType(control_value), *parsed_parameters))
    return tuple(codes)


def control_to_ansi(control: Sequence[ControlCode]) -> str:
    """Render validated control codes to their ANSI representation."""
    return "".join(
        CONTROL_CODES_FORMAT[code](*parameters) for code, *parameters in control
    )
