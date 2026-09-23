import json
import math
import threading

import pytest

from rich.progress import (
    CHECKPOINT_VERSION,
    Progress,
    ProgressCheckpointError,
    TaskID,
)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def make_source_progress():
    """Build a progress with running, paused and finished tasks, exported at t=10."""
    clock = FakeClock(0.0)
    progress = Progress(auto_refresh=False, get_time=clock)
    running = progress.add_task("running", total=100)
    paused = progress.add_task("paused", total=50, visible=False)
    finished = progress.add_task("finished", total=10)
    clock.now = 2.0
    progress.update(running, completed=20, worker="a")
    progress.update(paused, completed=10)
    clock.now = 4.0
    progress.stop_task(paused)
    progress.update(finished, completed=10)
    clock.now = 10.0
    checkpoint = progress.export_checkpoint()
    return progress, checkpoint, (running, paused, finished)


def test_checkpoint_round_trip_elapsed_and_states():
    _, checkpoint, _ = make_source_progress()
    assert checkpoint["version"] == CHECKPOINT_VERSION
    states = [task["state"] for task in checkpoint["tasks"]]
    assert states == ["running", "paused", "finished"]

    target_clock = FakeClock(100.0)
    target = Progress(auto_refresh=False, get_time=target_clock)
    id_map = target.restore_checkpoint(checkpoint)
    assert set(id_map.keys()) == {TaskID(0), TaskID(1), TaskID(2)}

    restored = {task.id: task for task in target.tasks}
    running = restored[id_map[TaskID(0)]]
    paused = restored[id_map[TaskID(1)]]
    finished = restored[id_map[TaskID(2)]]

    # Elapsed times are identical to export time, despite the new clock base.
    assert running.elapsed == pytest.approx(10.0)
    assert paused.elapsed == pytest.approx(4.0)
    assert finished.elapsed == pytest.approx(4.0)
    assert running.description == "running"
    assert paused.visible is False
    assert finished.finished
    assert paused.stop_time is not None and not paused.finished

    # Old speed samples are discarded; speed waits for new samples.
    assert running.speed is None

    # Two more seconds: only the running task accumulates elapsed time.
    target_clock.now = 102.0
    assert running.elapsed == pytest.approx(12.0)
    assert paused.elapsed == pytest.approx(4.0)
    assert finished.elapsed == pytest.approx(4.0)

    # Restoring data must not start the Live display.
    assert not target.live.is_started


def test_checkpoint_json_round_trip():
    _, checkpoint, _ = make_source_progress()
    serialized = json.dumps(checkpoint)
    target_clock = FakeClock(100.0)
    target = Progress(auto_refresh=False, get_time=target_clock)
    id_map = target.restore_checkpoint(json.loads(serialized))
    assert len(id_map) == 3
    assert [task.description for task in target.tasks] == [
        "running",
        "paused",
        "finished",
    ]
    assert target.tasks[0].fields == {"worker": "a"}


def test_restore_appends_and_remaps_ids():
    _, checkpoint, _ = make_source_progress()
    target_clock = FakeClock(100.0)
    target = Progress(auto_refresh=False, get_time=target_clock)
    existing = target.add_task("existing", total=5)
    id_map = target.restore_checkpoint(checkpoint)
    assert id_map == {TaskID(0): TaskID(1), TaskID(1): TaskID(2), TaskID(2): TaskID(3)}
    assert len(target.tasks) == 4
    assert target.tasks[0].description == "existing"
    assert existing not in id_map.values()
    # New tasks after restore get fresh, non-colliding IDs.
    new_task = target.add_task("after")
    assert new_task == TaskID(4)


def snapshot_tasks(progress):
    return [
        (task.description, task.total, task.completed, task.visible, dict(task.fields))
        for task in progress.tasks
    ]


def test_invalid_checkpoint_leaves_target_unchanged():
    _, checkpoint, _ = make_source_progress()
    target_clock = FakeClock(100.0)
    target = Progress(auto_refresh=False, get_time=target_clock)
    target.add_task("existing", total=5)
    before = snapshot_tasks(target)

    bad = json.loads(json.dumps(checkpoint))
    bad["tasks"][1]["completed"] = math.nan
    with pytest.raises(ProgressCheckpointError) as exc_info:
        target.restore_checkpoint(bad)
    assert exc_info.value.path == "tasks[1].completed"

    assert len(target.tasks) == 1
    assert snapshot_tasks(target) == before


@pytest.mark.parametrize(
    "mutate, path",
    [
        (lambda cp: cp.update(version=999), "version"),
        (lambda cp: cp["tasks"][1].update(id=0), "tasks[1].id"),
        (lambda cp: cp["tasks"][2].update(elapsed=-1.0), "tasks[2].elapsed"),
        (lambda cp: cp["tasks"][0].update(completed=math.inf), "tasks[0].completed"),
        (lambda cp: cp["tasks"][0].update(state="bogus"), "tasks[0].state"),
        (
            lambda cp: cp["tasks"][0]["fields"].update(bad=object()),
            "tasks[0].fields.bad",
        ),
        (
            lambda cp: cp["tasks"][0]["fields"].update(bad=[math.nan]),
            "tasks[0].fields.bad[0]",
        ),
    ],
)
def test_invalid_checkpoints_report_error_path(mutate, path):
    _, checkpoint, _ = make_source_progress()
    mutate(checkpoint)
    target = Progress(auto_refresh=False, get_time=FakeClock(100.0))
    with pytest.raises(ProgressCheckpointError) as exc_info:
        target.restore_checkpoint(checkpoint)
    assert exc_info.value.path == path
    assert target.tasks == []


def test_export_is_consistent_under_concurrent_updates():
    progress = Progress(auto_refresh=False)
    task_id = progress.add_task("work", total=0)
    stop = threading.Event()
    errors = []

    def updater():
        completed = 0
        while not stop.is_set():
            completed += 1
            try:
                progress.update(task_id, completed=completed, total=completed + 100)
            except Exception as error:  # pragma: no cover
                errors.append(error)
                return

    thread = threading.Thread(target=updater)
    thread.start()
    try:
        for _ in range(200):
            checkpoint = progress.export_checkpoint()
            json.dumps(checkpoint)
            task = checkpoint["tasks"][0]
            # total and completed must come from the same consistent snapshot
            assert task["completed"] + 100 == task["total"]
    finally:
        stop.set()
        thread.join()
    assert not errors


def test_checkpoint_fields_are_deep_copies():
    clock = FakeClock(0.0)
    progress = Progress(auto_refresh=False, get_time=clock)
    task_id = progress.add_task("task", total=10)
    progress.update(task_id, nested={"count": 1})

    checkpoint = progress.export_checkpoint()
    checkpoint["tasks"][0]["fields"]["nested"]["count"] = 999
    assert progress.tasks[0].fields == {"nested": {"count": 1}}

    target = Progress(auto_refresh=False, get_time=FakeClock(100.0))
    target.restore_checkpoint(checkpoint)
    checkpoint["tasks"][0]["fields"]["nested"]["count"] = -1
    assert target.tasks[0].fields == {"nested": {"count": 999}}


def test_restore_does_not_capture_source_clock():
    _, checkpoint, _ = make_source_progress()
    target_clock = FakeClock(100.0)
    target = Progress(auto_refresh=False, get_time=target_clock)
    id_map = target.restore_checkpoint(checkpoint)
    running = target.tasks[id_map[TaskID(0)]]
    # The restored task reads the target clock, not the source clock.
    assert running.get_time() == 100.0
    target_clock.now = 105.0
    assert running.elapsed == pytest.approx(15.0)
