"""Demonstrate checkpoint export and restore for ``rich.progress.Progress``.

Run with:

    python examples/progress_checkpoint.py

A controllable clock is used instead of real time, so the whole demo
(including the simulated process downtime) finishes in well under 90 seconds.
"""

import json

from rich.console import Console
from rich.progress import Progress, Task


class Clock:
    """A manually advanced clock (monotonic, in seconds)."""

    def __init__(self, time: float = 0.0) -> None:
        self.time = time

    def __call__(self) -> float:
        return self.time

    def tick(self, advance: float) -> None:
        self.time += advance


def task_state(task: Task) -> str:
    if task.finished:
        return "finished"
    if task.stop_time is not None:
        return "paused"
    if task.started:
        return "running"
    return "pending"


def print_states(progress: Progress, title: str, console: Console) -> None:
    console.print(f"[bold]{title}")
    for task in progress.tasks:
        console.print(
            f"  id={task.id} {task.description!r:12} state={task_state(task):8} "
            f"completed={task.completed}/{task.total} elapsed={task.elapsed}"
        )


def main() -> None:
    console = Console()

    # --- Source process: three tasks in three different states -----------
    source_clock = Clock()
    source = Progress(get_time=source_clock, auto_refresh=False)
    running_id = source.add_task("running", total=100)
    source.update(running_id, completed=40)
    paused_id = source.add_task("paused", total=50)
    source.update(paused_id, completed=10)
    source_clock.tick(5)
    source.stop_task(paused_id)  # paused at t=5 with elapsed=5
    finished_id = source.add_task("finished", total=10)
    source_clock.tick(3)
    source.update(finished_id, completed=10)  # finished at t=8 with elapsed=3
    source_clock.tick(2)  # export happens at t=10

    checkpoint = source.export_checkpoint()
    print_states(source, "Source at t=10 (export):", console)
    console.print("Checkpoint JSON:")
    console.print(json.dumps(checkpoint, indent=2))

    # --- The process stops here; downtime must not count -----------------
    restored_clock = Clock(100.0)  # new process, new monotonic clock
    restored = Progress(get_time=restored_clock, auto_refresh=False)
    id_map = restored.restore_checkpoint(json.loads(json.dumps(checkpoint)))
    console.print(f"Old -> new task ids: {id_map}")
    print_states(restored, "Restored at t=100 (elapsed unchanged):", console)

    restored_clock.tick(2)
    print_states(restored, "Restored at t=102 (only 'running' advances):", console)

    # --- Restoring appends to a Progress that already has tasks ----------
    existing_id = restored.add_task("existing", total=5)
    id_map2 = restored.restore_checkpoint(checkpoint)
    console.print(
        f"Second restore id map: {id_map2} (existing task id {existing_id} kept)"
    )
    console.print(f"Task count after append: {len(restored.tasks)}")

    # --- A corrupt checkpoint is rejected atomically ---------------------
    bad_checkpoint = json.loads(json.dumps(checkpoint))
    bad_checkpoint["tasks"][1]["completed"] = float("nan")
    before = [
        (task.id, task.description, task.completed, task.total)
        for task in restored.tasks
    ]
    try:
        restored.restore_checkpoint(bad_checkpoint)
    except ValueError as error:
        console.print(f"[red]Restore rejected:[/] {error}")
    after = [
        (task.id, task.description, task.completed, task.total)
        for task in restored.tasks
    ]
    console.print(f"Tasks unchanged after failed restore: {before == after}")


if __name__ == "__main__":
    main()
