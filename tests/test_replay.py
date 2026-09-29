import io
import json

import pytest

from rich.console import Console
from rich.control import Control
from rich.replay import (
    REPLAY_FORMAT,
    REPLAY_VERSION,
    ReplayError,
    dump_segments,
    load_segments,
    replay_ansi,
    replay_text,
)
from rich.segment import ControlType, Segment
from rich.style import Style

EXPECTED_FRAME = "中文标题 示例链接\n橙色\n下载进度 100%"


def record_session(width: int = 40) -> Console:
    """Record a session with a link, styled Chinese text and cursor updates."""
    console = Console(
        record=True,
        width=width,
        height=24,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
        file=io.StringIO(),
    )
    console.print(
        "[bold magenta]中文标题[/bold magenta] "
        "[link=https://example.com]示例链接[/link]"
    )
    console.print("[#ff8800]橙色[/]")
    for percent in (10, 50, 100):
        console.print(
            Control((ControlType.CARRIAGE_RETURN,), (ControlType.ERASE_IN_LINE, 2)),
            end="",
        )
        console.print(f"下载进度 [green]{percent:3d}%[/green]", end="")
    console.print()
    return console


def make_header(width: int = 40) -> str:
    return json.dumps(
        {"format": REPLAY_FORMAT, "version": REPLAY_VERSION, "width": width}
    )


def make_event(seq: int, **overrides) -> str:
    event = {"seq": seq, "text": "", "style": None, "control": None}
    event.update(overrides)
    return json.dumps(event)


def test_export_jsonl_format_and_sequence():
    console = record_session()
    data = console.export_jsonl()
    lines = data.splitlines()
    header = json.loads(lines[0])
    assert header == {"format": REPLAY_FORMAT, "version": REPLAY_VERSION, "width": 40}
    events = [json.loads(line) for line in lines[1:]]
    # Sequence numbers are monotonically increasing from 1.
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    # The export is pure JSON on every line; no executable code.
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_record_replay_plain_text_matches_capture():
    console = record_session()
    data = console.export_jsonl(clear=False)
    width, segments = load_segments(data)
    assert width == 40
    # The final frame matches the captured record buffer exactly.
    assert replay_text(segments, width) == EXPECTED_FRAME
    assert replay_text(console._record_buffer, width) == EXPECTED_FRAME
    # Styles (including the link) survive the round trip.
    assert any(
        segment.style is not None and segment.style.link == "https://example.com"
        for segment in segments
    )
    # Control events (cursor updates) survive the round trip.
    assert any(segment.control for segment in segments)


def test_save_jsonl_round_trip(tmp_path):
    console = record_session()
    path = tmp_path / "recording.jsonl"
    console.save_jsonl(str(path))
    width, segments = load_segments(path.read_text(encoding="utf-8"))
    assert replay_text(segments, width) == EXPECTED_FRAME


def test_export_jsonl_requires_record():
    console = Console(file=io.StringIO())
    with pytest.raises(AssertionError):
        console.export_jsonl()


def test_dump_load_round_trip_preserves_segments():
    segments = [
        Segment("链接", Style.parse("bold link https://example.com")),
        Segment("样式", Style.parse("italic red on white")),
        Segment("", None, [(ControlType.CURSOR_UP, 1)]),
        Segment("\n"),
    ]
    width, loaded = load_segments(dump_segments(segments, 80))
    assert width == 80
    assert loaded == segments


def make_color_segments():
    """Build segments with fresh Style instances (Style caches ANSI codes)."""
    return [
        Segment("橙色", Style(color="#ff8800")),
        Segment(" "),
        Segment("链接", Style(link="https://example.com")),
        Segment(" "),
        Segment("绿色", Style(color="green")),
        Segment("\n"),
    ]


def test_replay_ansi_color_capabilities():
    truecolor = replay_ansi(make_color_segments(), color_system="truecolor")
    assert "\x1b[" in truecolor
    assert "38;2;255;136;0" in truecolor  # #ff8800 as truecolor
    assert ";https://example.com" in truecolor  # link preserved
    standard = replay_ansi(make_color_segments(), color_system="standard")
    assert standard != truecolor
    assert "38;2;" not in standard  # downgraded to the standard palette
    no_color = replay_ansi(make_color_segments(), no_color=True)
    assert "38;2;" not in no_color
    assert "\x1b[32m" not in no_color  # green
    no_color_system = replay_ansi(make_color_segments(), color_system=None)
    assert "\x1b" not in no_color_system
    assert no_color_system == "橙色 链接 绿色\n"


def test_replay_text_has_no_escape_sequences():
    width, segments = load_segments(record_session().export_jsonl())
    text = replay_text(segments, width)
    assert "\x1b" not in text
    assert text == EXPECTED_FRAME


def test_replay_text_cursor_movement():
    segments = [
        Segment("进度 10%"),
        Segment(
            "",
            None,
            [(ControlType.CARRIAGE_RETURN,), (ControlType.ERASE_IN_LINE, 2)],
        ),
        Segment("进度 100%"),
        Segment("\n"),
    ]
    assert replay_text(segments, 40) == "进度 100%"


def test_replay_text_matches_export_text_for_plain_output():
    console = Console(
        record=True, width=40, height=24, force_terminal=True, file=io.StringIO()
    )
    console.print("hello")
    console.print("世界")
    width, segments = load_segments(console.export_jsonl(clear=False))
    assert replay_text(segments, width) == console.export_text(styles=False).rstrip(
        "\n"
    )


def test_load_rejects_unknown_version():
    data = record_session().export_jsonl()
    bad = data.replace(f'"version": {REPLAY_VERSION}', '"version": 999', 1)
    with pytest.raises(ReplayError) as exc_info:
        load_segments(bad)
    assert exc_info.value.line_no == 1
    assert "version" in str(exc_info.value)


def test_load_rejects_truncated_last_line():
    data = record_session().export_jsonl()
    lines = data.splitlines()
    truncated = "\n".join(lines[:-1] + [lines[-1][:10]]) + "\n"
    with pytest.raises(ReplayError) as exc_info:
        load_segments(truncated)
    assert exc_info.value.line_no == len(lines)


def test_load_rejects_malicious_control_field():
    header = make_header()
    evil_controls = [
        [["__import__", "os"]],
        [["eval"]],
        [["CURSOR_UP"]],  # missing parameter
        [["CURSOR_UP", -1]],  # negative parameter
        [["CURSOR_UP", "1"]],  # wrong parameter type
        [["SET_WINDOW_TITLE", "bad\x1b[2J"]],  # escape injection
        "not-a-list",
    ]
    for control in evil_controls:
        data = header + "\n" + make_event(1, control=control) + "\n"
        with pytest.raises(ReplayError) as exc_info:
            load_segments(data)
        assert exc_info.value.line_no == 2


def test_load_rejects_bad_style_field():
    header = make_header()
    for style in ({"__class__": "Style"}, ["bold"], "bold on"):
        data = header + "\n" + make_event(1, style=style) + "\n"
        with pytest.raises(ReplayError) as exc_info:
            load_segments(data)
        assert exc_info.value.line_no == 2


def test_load_rejects_out_of_order_sequence():
    header = make_header()
    data = "\n".join([header, make_event(1, text="a"), make_event(3, text="b")])
    with pytest.raises(ReplayError) as exc_info:
        load_segments(data)
    assert exc_info.value.line_no == 3
    assert "seq" in str(exc_info.value)


def test_load_rejects_unexpected_field():
    header = make_header()
    data = header + "\n" + make_event(1, payload="exec me") + "\n"
    with pytest.raises(ReplayError) as exc_info:
        load_segments(data)
    assert exc_info.value.line_no == 2
