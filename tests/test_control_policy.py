import io

import pytest

from rich.console import Console
from rich.control import Control, ControlPolicy
from rich.errors import ControlSequenceRejected
from rich.segment import ControlType, Segment

CURSOR_MOVES = (
    ControlType.CURSOR_UP,
    ControlType.CURSOR_DOWN,
    ControlType.CURSOR_FORWARD,
    ControlType.CURSOR_BACKWARD,
)


def make_console(policy=None, **kwargs) -> Console:
    """Create a deterministic terminal-like console writing to a StringIO."""
    file = io.StringIO()
    console = Console(
        file=file,
        force_terminal=True,
        legacy_windows=False,
        color_system="standard",
        width=80,
        control_policy=policy,
        _environ={"TERM": "xterm-256color"},  # ensure not a dumb terminal
        **kwargs,
    )
    console._test_file = file
    return console


def get_output(console: Console) -> str:
    return console._test_file.getvalue()


def test_allowed_control_passes_and_denied_becomes_diagnostic():
    # Authorize cursor movement only; clearing the screen is not authorized.
    policy = ControlPolicy(allow=CURSOR_MOVES, on_disallowed="diagnose")
    console = make_console(policy)
    console.control(Control.move(3, 0), Control.clear())
    output = get_output(console)
    # Authorized cursor movement is emitted...
    assert "\x1b[3C" in output
    # ...the denied clear-screen sequence is not...
    assert "\x1b[2J" not in output
    # ...and a visible diagnostic replaces it.
    assert "<control CLEAR denied>" in output


def test_plain_text_that_looks_like_control_is_not_interpreted():
    # A reject-everything policy must not mistake plain text for control codes.
    policy = ControlPolicy(allow=(), on_disallowed="reject")
    console = make_console(policy)
    sneaky_text = "text with \x1b[2J escape inside"
    console.print(sneaky_text, markup=False, highlight=False)  # must not raise
    output = get_output(console)
    assert sneaky_text in output
    assert "<control" not in output


def test_plain_text_not_diagnosed_in_diagnose_mode():
    policy = ControlPolicy(allow=(), on_disallowed="diagnose")
    console = make_console(policy)
    console.print("plain \x1b[2J text", markup=False, highlight=False)
    output = get_output(console)
    assert "plain \x1b[2J text" in output
    assert "<control" not in output


def test_reject_fails_before_writing():
    policy = ControlPolicy(allow=CURSOR_MOVES, on_disallowed="reject")
    console = make_console(policy, record=True)
    with pytest.raises(ControlSequenceRejected):
        console.control(Control.clear())
    # Nothing was written: no half-written control sequence.
    assert get_output(console) == ""
    assert console._buffer == []
    # The record buffer made the same decision: nothing recorded.
    assert console.export_text(styles=True) == ""


def test_reject_via_print_path_fails_before_writing():
    policy = ControlPolicy(allow=(), on_disallowed="reject")
    console = make_console(policy)
    with pytest.raises(ControlSequenceRejected):
        console.print(Control.clear())
    assert get_output(console) == ""
    assert console._buffer == []


def test_reject_never_writes_partial_sequence():
    # ENABLE_ALT_SCREEN + HOME is a single segment; authorizing HOME alone
    # must not emit the HOME half of a rejected sequence.
    policy = ControlPolicy(allow={ControlType.HOME}, on_disallowed="reject")
    console = make_console(policy)
    with pytest.raises(ControlSequenceRejected):
        console.control(Control.alt_screen(True))
    assert get_output(console) == ""


def test_record_matches_writer_output():
    policy = ControlPolicy(allow=CURSOR_MOVES, on_disallowed="diagnose")
    console = make_console(policy, record=True)
    console.print("hello", markup=False)
    console.control(Control.move(2, 0), Control.clear())
    console.print("world", markup=False)
    written = get_output(console)
    recorded = console.export_text(styles=True)
    # The record used the same policy decision as the writer.
    assert recorded == written
    assert "\x1b[2C" in recorded
    assert "\x1b[2J" not in recorded
    assert "<control CLEAR denied>" in recorded


def test_record_matches_writer_output_on_reject():
    policy = ControlPolicy(allow=(), on_disallowed="reject")
    console = make_console(policy, record=True)
    with pytest.raises(ControlSequenceRejected):
        console.control(Control.clear())
    assert get_output(console) == ""
    assert console.export_text(styles=True) == ""


def test_policies_are_independent_between_consoles():
    restrictive = make_console(ControlPolicy(allow=(), on_disallowed="reject"))
    permissive = make_console()  # no policy: everything permitted
    permissive.control(Control.clear())
    assert "\x1b[2J" in get_output(permissive)
    with pytest.raises(ControlSequenceRejected):
        restrictive.control(Control.clear())
    assert get_output(restrictive) == ""
    # Re-arming one console's policy does not affect the other.
    restrictive.control_policy = None
    restrictive.control(Control.clear())
    assert "\x1b[2J" in get_output(restrictive)
    permissive.control(Control.home())
    assert "\x1b[H" in get_output(permissive)


def test_no_policy_permits_all_control_codes():
    console = make_console()
    console.control(Control.clear(), Control.home(), Control.move(1, 0))
    output = get_output(console)
    assert "\x1b[2J" in output
    assert "\x1b[H" in output
    assert "\x1b[1C" in output


def test_policy_apply_on_plain_segment_is_identity():
    policy = ControlPolicy(allow=(), on_disallowed="reject")
    segment = Segment("just text")
    assert list(policy.apply(segment)) == [segment]


def test_invalid_on_disallowed_raises():
    with pytest.raises(ValueError):
        ControlPolicy(on_disallowed="explode")


def test_policy_repr():
    policy = ControlPolicy(
        allow={ControlType.CLEAR}, on_disallowed="diagnose"
    )
    assert "CLEAR" in repr(policy)
    assert "diagnose" in repr(policy)
