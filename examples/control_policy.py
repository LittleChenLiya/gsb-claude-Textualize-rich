"""Demonstrate the Console control sequence policy.

A control policy lets you explicitly authorize which
:class:`~rich.segment.ControlType` values a Console may write. Unauthorized
controls are either replaced with a visible diagnostic (``mode="diagnose"``)
or rejected before anything is written (``mode="reject"``).

Run it with::

    python examples/control_policy.py
"""

import os
import sys

# Make sure we import the local copy of rich (not an installed one).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io

from rich.console import Console
from rich.control import Control
from rich.segment import ControlType

# Authorize cursor movement, but not screen clearing.
cursor_controls = {
    ControlType.CURSOR_UP,
    ControlType.CURSOR_DOWN,
    ControlType.CURSOR_FORWARD,
    ControlType.CURSOR_BACKWARD,
    ControlType.CURSOR_MOVE_TO,
    ControlType.CURSOR_MOVE_TO_COLUMN,
}


def diagnose_demo() -> None:
    print("=== diagnose mode: cursor moves allowed, clear is visible ===\n")
    console = Console(file=io.StringIO(), force_terminal=True, _environ={},
                      control_policy=cursor_controls)
    console.control(Control.move(3, 4))
    console.control(Control.clear())
    output = console.file.getvalue()
    print(repr(output))
    assert "\x1b[3C" in output and "\x1b[4B" in output
    assert "\x1b[2J" not in output
    assert "blocked control: CLEAR" in output
    print()


def reject_demo() -> None:
    print("=== reject mode: clear raises before writing ===\n")
    from rich.errors import ControlPolicyError

    console = Console(file=io.StringIO(), force_terminal=True, _environ={},
                      control_policy=cursor_controls, control_policy_mode="reject")
    console.control(Control.move(1, 1))
    try:
        console.control(Control.clear())
    except ControlPolicyError as error:
        print(f"raised: {error}")
    output = console.file.getvalue()
    print(repr(output))
    assert "\x1b[2J" not in output
    print()


def text_is_not_a_control_demo() -> None:
    print("=== text that looks like a control is not treated as one ===\n")
    console = Console(file=io.StringIO(), force_terminal=True, _environ={},
                      highlight=False, control_policy=cursor_controls,
                      control_policy_mode="reject")
    console.print("\x1b[2J")  # ordinary text, not a Control instruction
    output = console.file.getvalue()
    print(repr(output))
    assert "\x1b[2J" in output
    print()


def independent_consoles_demo() -> None:
    print("=== two consoles, two independent policies ===\n")
    from rich.errors import ControlPolicyError

    cursor_console = Console(file=io.StringIO(), force_terminal=True, _environ={},
                             control_policy=cursor_controls, control_policy_mode="reject")
    clear_console = Console(file=io.StringIO(), force_terminal=True, _environ={},
                            control_policy={ControlType.CLEAR}, control_policy_mode="reject")
    cursor_console.control(Control.move(1, 1))
    try:
        cursor_console.control(Control.clear())
    except ControlPolicyError:
        print("cursor console rejected clear")
    clear_console.control(Control.clear())
    try:
        clear_console.control(Control.move(1, 1))
    except ControlPolicyError:
        print("clear console rejected cursor move")
    assert "\x1b[2J" not in cursor_console.file.getvalue()
    assert "\x1b[2J" in clear_console.file.getvalue()
    print()


def record_matches_writer_demo() -> None:
    print("=== recording matches the writer output ===\n")
    console = Console(file=io.StringIO(), force_terminal=True, _environ={},
                      record=True, control_policy=cursor_controls)
    console.control(Control.move(2, 2))
    console.control(Control.clear())
    writer_output = console.file.getvalue()
    recorded = console.export_text(styles=True, clear=False)
    print("writer:", repr(writer_output))
    print("record:", repr(recorded))
    assert writer_output == recorded
    print()


if __name__ == "__main__":
    diagnose_demo()
    reject_demo()
    text_is_not_a_control_demo()
    independent_consoles_demo()
    record_matches_writer_demo()
    print("All control policy demos passed.")
