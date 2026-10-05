"""Short terminal demo of explicit Console control-sequence policies.

Run with: python examples/control_policy_demo.py
"""
from rich.console import Console
from rich.control import Control, ControlPolicy
from rich.errors import ControlSequenceRejected
from rich.segment import ControlType

# Authorize cursor movement only; everything else is diagnosed or rejected.
policy = ControlPolicy(
    allow={
        ControlType.CURSOR_FORWARD,
        ControlType.CURSOR_BACKWARD,
        ControlType.CURSOR_UP,
        ControlType.CURSOR_DOWN,
    },
    on_disallowed="diagnose",
)
console = Console(control_policy=policy)

console.rule("diagnose mode: cursor moves allowed, clear denied")
console.print("moving right 10 columns (authorized)...", end="")
console.control(Control.move(10, 0))
console.print("<- cursor landed here")
console.print("attempting Control.clear() (not authorized):")
console.control(Control.clear())  # becomes a visible diagnostic, screen stays
console.print()
console.print(r"plain text '\x1b[2J' is just text, never an instruction")

console.rule("reject mode: denied control fails before writing")
reject_console = Console(
    control_policy=ControlPolicy(allow=set(), on_disallowed="reject")
)
try:
    reject_console.control(Control.clear())
except ControlSequenceRejected as error:
    reject_console.print(f"[green]caught before any output:[/] {error}")

console.rule("policies are per-Console")
plain_console = Console()  # no policy: everything permitted
plain_console.print("a second console without a policy is unaffected")
