import json
import math
import time
from threading import Thread

import pytest

from rich.progress import CHECKPOINT_VERSION, Progress, TaskID


class Clock:
    """A manually advanced, thread-safe monotonic clock."""

    def __init__(self, time: float = 0.0) -> None:
        self.time = time

    def __call__(self) -> float:
        return self.time

    def tick(self, advance: float = 1.0) -> None:
        self.time += advance


def build_source(clock: Clock) -> Progress:
    progress = Progress(get_time=clock, auto_refresh=False)
    running = progress.add_task("running", total=100)
    progress.update(running, completed=40)
    paused = progress.add_task("paused", total=50, completed=10)
    clock.tick(5)
    progress.stop_task(paused)
    finished = progress.add_task("finished", total=10)
    clock.tick(3)
    progress.update(finished, completed=10)
    clock.tick(2)
    return progress


def states(progress: Progress):
    return [
        (
            task.description,
            (
                "finished"
                if task.finished
                else (
                    "paused"
                    if task.stop_time is not None
                    else "running" if task.started else "pending"
                )
            ),
        )
        for task in progress.tasks
    ]


def test_checkpoint_three_states_elapsed_rebased() -> None:
    """Export at t=10, restore with a clock at t=100."""
    source_clock = Clock()
    source = build_source(source_clock)
    assert source_clock.time == 10.0

    expected_elapsed = [task.elapsed for task in source.tasks]
    checkpoint = source.export_checkpoint()
    assert [task["state"] for task in checkpoint["tasks"]] == [
        "running",
        "paused",
        "finished",
    ]
    assert checkpoint["version"] == CHECKPOINT_VERSION

    restored_clock = Clock(100.0)
    restored = Progress(get_time=restored_clock, auto_refresh=False)
    id_map = restored.restore_checkpoint(checkpoint)

    assert id_map == {TaskID(0): TaskID(0), TaskID(1): TaskID(1), TaskID(2): TaskID(2)}
    assert not restored.live.is_started
    for task, expected in zip(restored.tasks, expected_elapsed):
        assert task.elapsed == expected
    assert states(restored) == [
        ("running", "running"),
        ("paused", "paused"),
        ("finished", "finished"),
    ]

    restored_clock.tick(2)
    assert [task.elapsed for task in restored.tasks] == [
        expected_elapsed[0] + 2,
        expected_elapsed[1],
        expected_elapsed[2],
    ]
    assert states(restored)[1] == ("paused", "paused")


def test_checkpoint_json_roundtrip() -> None:
    source_clock = Clock()
    source = build_source(source_clock)
    progress_with_fields = Progress(get_time=source_clock, auto_refresh=False)
    progress_with_fields.add_task(
        "with fields", total=None, visible=False, n=1, tags=["a", 1, None]
    )
    checkpoint = progress_with_fields.export_checkpoint()

    restored = Progress(get_time=Clock(100.0), auto_refresh=False)
    restored.restore_checkpoint(json.loads(json.dumps(checkpoint)))
    task = restored.tasks[0]
    assert task.description == "with fields"
    assert task.total is None
    assert task.visible is False
    assert task.fields == {"n": 1, "tags": ["a", 1, None]}

    # Full round trip preserves all data.
    again = restored.export_checkpoint()
    assert json.loads(json.dumps(again)) == again


def test_checkpoint_fields_are_deep_copied() -> None:
    clock = Clock()
    source = Progress(get_time=clock, auto_refresh=False)
    source.add_task("t", total=None, meta={"nested": [1, 2, 3]})
    checkpoint = source.export_checkpoint()

    source.tasks[0].fields["meta"]["nested"].append(4)
    assert checkpoint["tasks"][0]["fields"] == {"meta": {"nested": [1, 2, 3]}}

    checkpoint["tasks"][0]["fields"]["meta"]["nested"].append(99)
    restored = Progress(get_time=Clock(100.0), auto_refresh=False)
    restored.restore_checkpoint(checkpoint)
    assert restored.tasks[0].fields == {"meta": {"nested": [1, 2, 3, 99]}}

    restored.tasks[0].fields["meta"]["nested"].append(1000)
    assert checkpoint["tasks"][0]["fields"] == {"meta": {"nested": [1, 2, 3, 99]}}


def test_restore_appends_and_remaps_ids() -> None:
    source_clock = Clock()
    source = build_source(source_clock)
    checkpoint = source.export_checkpoint()

    restored = Progress(get_time=Clock(100.0), auto_refresh=False)
    existing = restored.add_task("existing", total=5, completed=2)
    id_map = restored.restore_checkpoint(checkpoint)
    assert existing == TaskID(0)
    assert id_map == {TaskID(0): TaskID(1), TaskID(1): TaskID(2), TaskID(2): TaskID(3)}
    assert restored.task_ids == [TaskID(i) for i in range(4)]
    assert restored.tasks[0].description == "existing"
    assert [task.description for task in restored.tasks[1:]] == [
        "running",
        "paused",
        "finished",
    ]

    # Restored tasks behave like ordinary tasks afterwards.
    restored.advance(id_map[TaskID(0)], 5)
    assert restored.tasks[1].completed == 45
    restored.stop_task(id_map[TaskID(0)])
    restored.reset(id_map[TaskID(0)])


def test_restore_discards_speed_samples() -> None:
    source_clock = Clock()
    source = Progress(get_time=source_clock, auto_refresh=False)
    task_id = source.add_task("t", total=100)
    source.update(task_id, completed=10)
    source_clock.tick(5)
    source.update(task_id, completed=20)
    assert source.tasks[0].speed is not None

    restored_clock = Clock(100.0)
    restored = Progress(get_time=restored_clock, auto_refresh=False)
    new_id = restored.restore_checkpoint(source.export_checkpoint())[task_id]
    assert restored.tasks[0].speed is None

    restored.update(new_id, completed=30)
    restored_clock.tick(5)
    restored.update(new_id, completed=40)
    assert restored.tasks[0].speed == pytest.approx(2.0)


def test_pending_task_roundtrip() -> None:
    source = Progress(get_time=Clock(), auto_refresh=False)
    source.add_task("pending", start=False, total=10)
    checkpoint = source.export_checkpoint()
    assert checkpoint["tasks"][0]["state"] == "pending"
    assert checkpoint["tasks"][0]["elapsed"] is None

    restored = Progress(get_time=Clock(100.0), auto_refresh=False)
    restored.restore_checkpoint(checkpoint)
    assert not restored.tasks[0].started
    assert restored.tasks[0].elapsed is None


def test_failed_restore_leaves_existing_tasks_untouched() -> None:
    source = build_source(Clock())
    checkpoint = source.export_checkpoint()
    checkpoint["tasks"][1]["completed"] = float("nan")

    restored = Progress(get_time=Clock(100.0), auto_refresh=False)
    restored.add_task("existing", total=5, completed=2)
    snapshot = [
        (task.id, task.description, task.total, task.completed, task.visible)
        for task in restored.tasks
    ]

    with pytest.raises(ValueError, match=r"tasks\[1\]\.completed"):
        restored.restore_checkpoint(checkpoint)

    assert len(restored.tasks) == 1
    assert not restored.live.is_started
    assert [
        (task.id, task.description, task.total, task.completed, task.visible)
        for task in restored.tasks
    ] == snapshot


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda cp: cp.update(version=2), "version"),
        (lambda cp: cp.update(tasks="nope"), "tasks"),
        (lambda cp: cp.update(tasks=[42]), r"tasks\[0\]"),
        (lambda cp: cp["tasks"][1].__setitem__("id", 0), r"tasks\[1\]\.id"),
        (
            lambda cp: cp["tasks"][0].__setitem__("total", float("nan")),
            r"tasks\[0\]\.total",
        ),
        (
            lambda cp: cp["tasks"][0].__setitem__("completed", float("inf")),
            r"tasks\[0\]\.completed",
        ),
        (
            lambda cp: cp["tasks"][0].__setitem__("elapsed", -1.5),
            r"tasks\[0\]\.elapsed",
        ),
        (
            lambda cp: cp["tasks"][0].__setitem__("state", "asleep"),
            r"tasks\[0\]\.state",
        ),
        (lambda cp: cp["tasks"][0].__setitem__("visible", 1), r"tasks\[0\]\.visible"),
        (
            lambda cp: cp["tasks"][0].__setitem__("description", 9),
            r"tasks\[0\]\.description",
        ),
        (
            lambda cp: cp["tasks"][0]["fields"].__setitem__("bad", object()),
            r"tasks\[0\]\.fields",
        ),
        (
            lambda cp: cp["tasks"][0]["fields"].__setitem__("tup", (1, 2)),
            r"tasks\[0\]\.fields",
        ),
        (
            lambda cp: cp["tasks"][0]["fields"].__setitem__(
                "nested", {"deep": object()}
            ),
            r"tasks\[0\]\.fields",
        ),
    ],
)
def test_invalid_checkpoints_identify_path(mutate, path) -> None:
    checkpoint = build_source(Clock()).export_checkpoint()
    mutate(checkpoint)
    progress = Progress(auto_refresh=False)
    with pytest.raises(ValueError, match=path):
        progress.restore_checkpoint(checkpoint)
    assert progress.tasks == []


def test_checkpoint_root_must_be_object() -> None:
    progress = Progress(auto_refresh=False)
    with pytest.raises(ValueError, match="<root>"):
        progress.restore_checkpoint("not a checkpoint")


def test_concurrent_updates_and_exports_are_consistent() -> None:
    progress = Progress(get_time=time.monotonic, auto_refresh=False)
    task_id = progress.add_task("concurrent", total=None)
    stop = False

    def hammer_updates() -> None:
        count = 0
        while not stop:
            count += 1
            progress.update(task_id, total=count * 2, completed=count)

    thread = Thread(target=hammer_updates)
    thread.start()
    try:
        for _ in range(200):
            checkpoint = progress.export_checkpoint()
            entry = checkpoint["tasks"][0]
            # total and completed must come from the same instant.
            assert entry["completed"] * 2 == entry["total"]
            assert math.isfinite(entry["elapsed"])
            target = Progress(auto_refresh=False)
            target.restore_checkpoint(json.loads(json.dumps(checkpoint)))
    finally:
        stop = True
        thread.join()
