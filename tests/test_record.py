import io
import json

import pytest

from rich._record_replay import replay_segments, replay_segments_plain
from rich.color import Color
from rich.console import Console
from rich.control import Control
from rich.progress import BarColumn, Progress, TextColumn
from rich.record import (
    CONTROL_WHITELIST,
    RECORD_FORMAT_VERSION,
    RecordError,
    Recording,
)
from rich.segment import ControlType, Segment
from rich.style import Style


def test_roundtrip_text_style_and_newlines():
    segments = [
        Segment("hello", Style.parse("bold red")),
        Segment(" "),
        Segment.line(),
        Segment("world", Style.parse("link https://example.com")),
    ]
    recording = Recording.from_segments(segments, width=30)
    restored = Recording.from_jsonl(recording.to_jsonl().splitlines(keepends=True))
    assert restored.width == 30
    assert restored.segments == segments


def test_roundtrip_control_actions():
    control = Control(
        ControlType.CARRIAGE_RETURN,
        (ControlType.ERASE_IN_LINE, 2),
        (ControlType.CURSOR_UP, 3),
        (ControlType.CURSOR_MOVE_TO, 5, 7),
        (ControlType.SET_WINDOW_TITLE, "hi"),
    ).segment.control
    recording = Recording.from_segments([Segment("", None, control)], width=20)
    restored = Recording.from_jsonl(recording.to_jsonl().splitlines(keepends=True))
    assert list(restored.segments[0].control) == list(control)


def test_jsonl_is_data_only():
    recording = Recording.from_segments(
        [Segment("x", Style.parse("red")), Segment.line()], width=10
    )
    for line in recording.to_jsonl().splitlines():
        event = json.loads(line)
        assert "__class__" not in event
        # JSONL is data, not Python source
        assert not line.lstrip().startswith(("import ", "from ", "exec", "eval"))


def test_console_export_and_save_jsonl(tmp_path):
    console = Console(width=24, record=True, file=io.StringIO())
    console.print("[bold cyan]hello[/bold cyan]")
    console.control(Control.home())
    path = tmp_path / "recording.jsonl"
    console.save_jsonl(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {
        "version": RECORD_FORMAT_VERSION,
        "width": 24,
    }
    sequence_numbers = [json.loads(line)["seq"] for line in lines[1:]]
    assert sequence_numbers == list(range(1, len(lines)))
    recording = Recording.load(str(path))
    assert any(segment.is_control for segment in recording)
    assert console._record_buffer == []


def test_ansi_replay_with_color_systems():
    segments = [
        Segment(
            "rgb",
            Style(
                color=Color.from_rgb(16, 32, 48),
                bgcolor=Color.from_rgb(64, 80, 96),
                bold=True,
            ),
        ),
        Segment(" plain"),
    ]
    truecolor = replay_segments(segments, width=20, color_system="truecolor")
    eight_bit = replay_segments(segments, width=20, color_system="256")
    plain = replay_segments(segments, width=20, color_system=None)
    assert "38;2;16;32;48" in truecolor
    assert "38;5;" in eight_bit
    assert truecolor != eight_bit
    assert plain == "rgb plain"


def test_no_color_replay_is_readable():
    segments = [Segment("A", Style.parse("bold red")), Segment("B")]
    recording = Recording.from_segments(segments, width=10)
    assert recording.replay(no_color=True) == "AB"


def _record_progress():
    stream = io.StringIO()
    console = Console(
        width=60,
        record=True,
        force_terminal=True,
        color_system="truecolor",
        file=stream,
    )
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[link=https://example.com]{task.percentage:>3.0f}%[/link]"),
        console=console,
        auto_refresh=False,
    )
    with progress:
        task = progress.add_task("\u4e0b\u8f7d\u4e2d\u6587", total=100)
        progress.update(task, completed=30, refresh=True)
        progress.update(task, completed=100, refresh=True)
    return console, stream, progress


def test_progress_recording_plain_matches_capture():
    console, stream, progress = _record_progress()
    jsonl = console.export_jsonl()
    recording = Recording.from_jsonl(jsonl.splitlines(keepends=True))

    # Independently render the final progress state as plain text and compare
    # it with the replayed final screen. Trailing padding spaces are not part
    # of the visible screen.
    expected = "\n".join(
        "".join(segment.text for segment in line if not segment.control).rstrip()
        for line in console.render_lines(progress, console.options)
    )
    final_screen = recording.replay_text()
    assert final_screen == expected

    # Chinese description, link rendered as its visible text, full bar and
    # final percentage are all visible on the colorless final screen.
    assert "\u4e0b\u8f7d\u4e2d\u6587" in expected
    assert "100%" in expected
    assert expected.endswith("100%")
    assert "\x1b" not in final_screen
    # Raw bytes carried cursor-update control codes between frames.
    assert "\x1b[2K" in stream.getvalue()
    assert "\x1b[?25l" in stream.getvalue()


def test_ansi_replay_contains_link_and_color():
    console, _, _ = _record_progress()
    recording = Recording.from_jsonl(console.export_jsonl().splitlines(keepends=True))
    ansi = recording.replay(color_system="256")
    assert "\x1b]8;" in ansi
    assert "https://example.com" in ansi
    # no-color output drops all styling but keeps cursor-control sequences
    colorless = recording.replay(no_color=True)
    assert "\x1b[1m" not in colorless
    assert "\x1b]8;" not in colorless
    assert "\x1b[2K" in colorless


def test_plain_replay_cursor_updates():
    segments = [
        Segment("frame 1"),
        Segment(
            "",
            None,
            Control(
                (ControlType.CURSOR_UP, 1),
            ).segment.control,
        ),
        Segment("\r"),
        Segment("frame 2"),
    ]
    assert replay_segments_plain(segments, width=20) == "frame 2"


def test_event_order_must_be_sequential():
    jsonl = (
        '{"version":1,"width":10}\n' '{"seq":1,"text":"a"}\n' '{"seq":3,"text":"b"}\n'
    )
    with pytest.raises(RecordError) as exc_info:
        Recording.from_jsonl(io.StringIO(jsonl))
    assert exc_info.value.line_number == 3
    assert "expected seq 2" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_line,message",
    [
        ('{"version":99,"width":10}', "unsupported recording version"),
        ('{"version":"1","width":10}', "'version' must be an integer"),
        ('{"width":10}', "header"),
        ('{"version":1}', "header"),
        ('{"version":1,"width":10,"extra":1}', "header"),
    ],
)
def test_bad_headers(bad_line, message):
    with pytest.raises(RecordError) as exc_info:
        Recording.from_jsonl(io.StringIO(bad_line + "\n"))
    assert message in str(exc_info.value)


def test_empty_recording_rejected():
    with pytest.raises(RecordError, match="missing recording header"):
        Recording.from_jsonl(io.StringIO(""))


@pytest.mark.parametrize(
    "event,message",
    [
        ('{"seq":1}', "must contain 'text' or 'control'"),
        ('{"seq":1,"text":5}', "'text' must be a string"),
        ('{"seq":1,"text":"a","style":3}', "'style' must be a string"),
        ('{"seq":1,"text":"a","style":"this is not a style!!!"}', "invalid style"),
        ('{"seq":1,"control":[]}', "non-empty list"),
        ('{"seq":1,"control":[[999]]}', "not allowed"),
        ('{"seq":1,"control":[["home"]]}', "control type must be an integer"),
        ('{"seq":1,"control":[[9,"1"]]}', "must be an integer"),
        ('{"seq":1,"control":[[9,-1]]}', "must not be negative"),
        ('{"seq":1,"control":[[9]]}', "requires 1 parameter"),
        ('{"seq":1,"control":[[14,1,2,3]]}', "requires 2 parameter"),
        ('{"seq":1,"control":[[16,123]]}', "must be a string"),
        (
            '{"seq":1,"control":[[16,"\\u001b]8;;evil\\u0007"]]}',
            "disallowed control character",
        ),
        ('{"seq":1,"text":"a","control":[[3]]}', "may only contain"),
        ('{"seq":"x","text":"a"}', "'seq' must be an integer"),
        ('{"text":"a"}', "missing 'seq'"),
        ('{"seq":1,"text":"\\u001b[31mevil"}', "disallowed control character"),
    ],
)
def test_bad_events(event, message):
    jsonl = '{"version":1,"width":10}\n' + event + "\n"
    with pytest.raises(RecordError) as exc_info:
        Recording.from_jsonl(io.StringIO(jsonl))
    assert exc_info.value.line_number == 2
    assert message in str(exc_info.value)


def test_truncated_final_line_reports_line_number():
    jsonl = '{"version":1,"width":10}\n{"seq":1,"text":'  # no newline, truncated
    with pytest.raises(RecordError) as exc_info:
        Recording.from_jsonl(io.StringIO(jsonl))
    assert exc_info.value.line_number == 2
    assert "invalid JSON" in str(exc_info.value)


def test_blank_line_rejected():
    jsonl = '{"version":1,"width":10}\n{"seq":1,"text":"a"}\n   \n'
    with pytest.raises(RecordError) as exc_info:
        Recording.from_jsonl(io.StringIO(jsonl))
    assert exc_info.value.line_number == 3


def test_corruption_aborts_and_points_at_line():
    jsonl = (
        '{"version":1,"width":10}\n'
        '{"seq":1,"text":"ok"}\n'
        '{"seq":2,"text":' + '"x' + "\n"
    )
    with pytest.raises(RecordError) as exc_info:
        Recording.from_jsonl(io.StringIO(jsonl))
    assert exc_info.value.line_number == 3


def test_every_whitelisted_control_roundtrips():
    assert set(CONTROL_WHITELIST) == {int(value) for value in ControlType}
    codes = []
    for control_value, arity in CONTROL_WHITELIST.items():
        control_type = ControlType(control_value)
        if control_type == ControlType.SET_WINDOW_TITLE:
            codes.append((control_type, "title"))
        elif arity == 0:
            codes.append((control_type,))
        elif arity == 1:
            codes.append((control_type, 1))
        else:
            codes.append((control_type, 1, 2))
    segment = Segment("", None, codes)
    recording = Recording.from_segments([segment], width=20)
    restored = Recording.from_jsonl(recording.to_jsonl().splitlines(keepends=True))
    assert restored.segments[0].control == tuple(codes)


def test_fixed_width_recorded_in_header():
    recording = Recording.from_segments([Segment("x")], width=77)
    header = json.loads(recording.to_jsonl().splitlines()[0])
    assert header == {"version": 1, "width": 77}
    restored = Recording.from_jsonl(recording.to_jsonl().splitlines(keepends=True))
    assert restored.width == 77


def test_load_from_file_roundtrip(tmp_path):
    path = tmp_path / "session.jsonl"
    recording = Recording.from_segments(
        [Segment("a", Style.parse("bold")), Segment.line(), Segment("b")],
        width=15,
    )
    recording.save(str(path))
    loaded = Recording.load(str(path))
    assert loaded.width == 15
    assert loaded.segments == recording.segments

    with open(str(path), encoding="utf-8") as jsonl_file:
        assert Recording.load(jsonl_file).segments == recording.segments


def test_replay_downgrades_to_standard_colors():
    style = Style(color=Color.from_rgb(16, 32, 48))
    recording = Recording.from_segments([Segment("x", style)], width=10)
    standard = recording.replay(color_system="standard")
    assert standard == "\x1b[30mx\x1b[0m"
    assert recording.replay(color_system="256").startswith("\x1b[38;5;")
