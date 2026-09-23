"""Demonstrate exporting and restoring Progress checkpoints.

Run from the repository root (finishes in a few seconds):

    python examples/progress_checkpoint.py

It creates running, paused and finished tasks, exports a JSON checkpoint,
restores it into a new Progress, and prints the restored states. The paused
task stays paused after the restore.
"""

import json
import os
import sys
import time

# Allow running directly from a source checkout without installing Rich.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.progress import Progress


def describe(progress, id_map, labels):
    lines = []
    for old_id, label in labels:
        task = progress.tasks[id_map[old_id]]
        if task.finished:
            state = "finished"
        elif task.stop_time is not None:
            state = "paused"
        else:
            state = "running"
        lines.append(f"  {label}: state={state} elapsed={task.elapsed:.1f}s")
    return "\n".join(lines)


def main() -> None:
    source = Progress(auto_refresh=False)
    running = source.add_task("running", total=100)
    paused = source.add_task("paused", total=100)
    finished = source.add_task("finished", total=10)
    labels = [(running, "running"), (paused, "paused"), (finished, "finished")]

    time.sleep(0.5)
    source.update(running, completed=20)
    source.stop_task(paused)
    source.update(finished, completed=10)
    time.sleep(0.5)

    checkpoint = source.export_checkpoint()
    payload = json.dumps(checkpoint)  # may be written to disk here
    print("Exported checkpoint at t=%.1fs" % 1.0)

    time.sleep(1.0)  # simulates process downtime; not counted towards elapsed

    restored = Progress(auto_refresh=False)
    id_map = restored.restore_checkpoint(json.loads(payload))
    print("Restored into a new Progress:")
    print(describe(restored, id_map, labels))

    time.sleep(1.0)
    restored.update(id_map[running], advance=10)
    print("One second later (only the running task keeps time):")
    print(describe(restored, id_map, labels))


if __name__ == "__main__":
    main()
