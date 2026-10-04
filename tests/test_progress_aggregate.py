"""Tests for the weighted parent-child progress aggregation layer."""

import pytest

from rich.progress import Progress, TaskID
from rich.progress_aggregate import (
    AGG_STATUS_FIELD,
    AggregatedProgress,
    AggregateState,
    AggregateStatusColumn,
    ChildState,
)


def make_progress() -> Progress:
    """A Progress instance with rendering disabled (deterministic, no TTY)."""
    return Progress(disable=True)


def test_weighted_ratio_25_percent() -> None:
    """Weights 1:3, children 100% / 0% -> parent 25%."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta = agg.task_id(a)

    progress.update(ta, completed=4)  # 100%
    # b stays at 0%
    state = agg.sync()

    assert isinstance(state, AggregateState)
    assert state.ratio == pytest.approx(0.25)
    assert state.completed == pytest.approx(25.0)
    assert state.total == pytest.approx(100.0)
    assert state.indeterminate is False
    assert state.failed is False
    assert state.finished is False

    # The parent task is driven through the ordinary Progress display.
    parent_task = progress._tasks[parent]
    assert parent_task.total == pytest.approx(100.0)
    assert parent_task.completed == pytest.approx(25.0)
    assert parent_task.fields[AGG_STATUS_FIELD] == "active"


def test_weighted_ratio_62_5_percent() -> None:
    """Weights 1:3, children 100% / 50% -> parent 62.5%."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)

    progress.update(ta, completed=4)
    progress.update(tb, completed=2)  # 50%
    state = agg.sync()

    assert state.ratio == pytest.approx(0.625)
    assert state.completed == pytest.approx(62.5)
    assert state.indeterminate is False
    assert state.failed is False


def test_indeterminate_unknown_total() -> None:
    """An active child with unknown total makes the parent indeterminate."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)

    progress.update(ta, completed=4)
    progress.update(tb, completed=2)
    agg.sync()
    assert progress._tasks[parent].total == pytest.approx(100.0)

    # Make the total unknown (rich's update() treats total=None as
    # "no change", so set it directly on the task object).
    progress._tasks[tb].total = None
    state = agg.sync()

    assert state.indeterminate is True
    assert state.ratio is None
    assert state.total is None
    assert state.completed == 0.0
    # The parent task pulses (total=None) in the existing Progress display.
    parent_task = progress._tasks[parent]
    assert parent_task.total is None
    assert parent_task.fields[AGG_STATUS_FIELD] == "indeterminate"

    # When the total comes back, the aggregate is known again.
    progress.update(tb, total=4)
    state = agg.sync()
    assert state.indeterminate is False
    assert state.ratio == pytest.approx(0.625)
    assert progress._tasks[parent].total == pytest.approx(100.0)


def test_finished_child_keeps_frozen_snapshot() -> None:
    """A finished child's contribution is frozen at its final ratio."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)

    progress.update(ta, completed=4)  # a finished at 100%
    progress.update(tb, completed=4)  # b finished at 100%
    state = agg.sync()
    assert state.finished is True
    assert state.ratio == pytest.approx(1.0)
    assert progress._tasks[parent].finished_time is not None

    # Later changes to the finished tasks must not change the snapshot.
    progress.update(ta, completed=0)
    progress.update(tb, completed=0)
    state = agg.sync()
    assert state.ratio == pytest.approx(1.0)
    assert state.finished is True
    assert all(child.state == ChildState.FINISHED for child in state.children)
    assert all(child.ratio == pytest.approx(1.0) for child in state.children)


def test_failed_child_makes_parent_fail() -> None:
    """A failed child makes the parent fail, not auto-complete."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)

    progress.update(ta, completed=4)  # 100%
    progress.update(tb, completed=4)  # 100% would sum to 100% ...
    agg.fail_child(b)  # ... but b failed
    state = agg.sync()

    assert state.failed is True
    assert state.finished is False
    assert state.children[1].state == ChildState.FAILED
    # The parent must never be marked finished.
    parent_task = progress._tasks[parent]
    assert parent_task.finished_time is None
    assert parent_task.fields[AGG_STATUS_FIELD] == "failed"

    # Even with all ratios at 100%, failure dominates.
    assert state.ratio == pytest.approx(1.0)
    assert state.finished is False


def test_failed_child_with_unknown_total() -> None:
    """Failure with unknown total still shows failed (not indeterminate)."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)

    progress.update(ta, completed=4)
    progress._tasks[tb].total = None
    agg.fail_child(b)
    state = agg.sync()

    assert state.failed is True
    # Failed dominates: the parent shows failure, not a pulse.
    assert state.indeterminate is False
    assert progress._tasks[parent].fields[AGG_STATUS_FIELD] == "failed"
    assert progress._tasks[parent].finished_time is None


def test_remove_task_freezes_snapshot() -> None:
    """Removing a task from Progress freezes the child's last contribution."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    ta = agg.task_id(a)

    progress.update(ta, completed=2)  # 50%
    agg.sync()
    progress.remove_task(ta)
    state = agg.sync()

    child = state.children[0]
    assert child.state == ChildState.FINISHED
    assert child.ratio == pytest.approx(0.5)
    assert state.ratio == pytest.approx(0.5)


def test_task_id_reuse_does_not_associate_new_task() -> None:
    """Reusing a TaskID must never associate a new task with an old snapshot."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    ta = agg.task_id(a)

    progress.update(ta, completed=4)  # 100%
    agg.sync()

    # Remove the task and force reuse of the same TaskID.
    progress.remove_task(ta)
    progress._task_index = TaskID(int(ta))
    new_id = progress.add_task("new", total=4)
    assert new_id == ta  # the new task reuses the old TaskID
    progress.update(new_id, completed=0)  # new task at 0%

    state = agg.sync()
    child = state.children[0]
    # The old child keeps its 100% snapshot; the new task's 0% is never read.
    assert child.ratio == pytest.approx(1.0)
    assert child.state == ChildState.FINISHED
    assert state.ratio == pytest.approx(1.0)


def test_identity_is_independent_of_task_id() -> None:
    """Children are identified by a unique identity, not their TaskID."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    ta = progress.add_task("a", total=4)
    tb = progress.add_task("b", total=4)

    ia = agg.add_child(ta, weight=1, name="A")
    ib = agg.add_child(tb, weight=3, name="B")

    assert ia != ib
    assert agg.task_id(ia) == ta
    assert agg.task_id(ib) == tb
    assert agg.identities == [ia, ib]

    state = agg.sync()
    by_name = {child.name: child for child in state.children}
    assert by_name["A"].task_id == ta
    assert by_name["B"].task_id == tb
    assert by_name["A"].weight == 1.0
    assert by_name["B"].weight == 3.0


def test_remove_child_detaches_contribution() -> None:
    """remove_child drops the child's contribution from the parent."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    agg.add_child_task("b", total=4, weight=3)

    agg.remove_child(a)
    assert len(agg.identities) == 1
    state = agg.sync()
    assert len(state.children) == 1
    assert state.finished is False  # a single active child cannot finish


def test_state_is_pure_and_does_not_touch_display() -> None:
    """state() must not modify the parent task; sync() does."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    ta = agg.task_id(a)
    progress.update(ta, completed=2)

    parent_task = progress._tasks[parent]
    before = (parent_task.total, parent_task.completed)
    agg.state()  # pure read
    assert (parent_task.total, parent_task.completed) == before

    agg.sync()
    assert parent_task.completed == pytest.approx(50.0)


def test_invalid_arguments() -> None:
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    with pytest.raises(ValueError):
        AggregatedProgress(progress, parent, total=0)
    agg = AggregatedProgress(progress, parent)
    with pytest.raises(ValueError):
        agg.add_child_task("a", total=4, weight=0)
    with pytest.raises(KeyError):
        agg.add_child(TaskID(9999))


def test_aggregate_status_column_renders_status() -> None:
    """The status column renders fail / indeterminate / done from task fields."""
    progress = Progress(AggregateStatusColumn(), disable=True)
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=4, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)
    column = AggregateStatusColumn()

    progress.update(ta, completed=4)
    progress.update(tb, completed=2)
    agg.sync()
    assert column.render(progress._tasks[parent]).plain == ""

    progress._tasks[tb].total = None
    agg.sync()
    assert "...." in column.render(progress._tasks[parent]).plain

    progress.update(tb, total=4)
    agg.fail_child(b)
    agg.sync()
    assert "FAIL" in column.render(progress._tasks[parent]).plain

    progress.update(tb, completed=4)
    agg.sync()
    # Failure dominates even at 100%: FAIL, never DONE.
    assert "FAIL" in column.render(progress._tasks[parent]).plain
    assert "DONE" not in column.render(progress._tasks[parent]).plain

    agg.remove_child(b)
    progress.update(ta, completed=4)
    # a alone is finished -> DONE
    agg.sync()
    assert "DONE" in column.render(progress._tasks[parent]).plain


def test_children_with_different_totals_use_ratios() -> None:
    """A 4-step and a 1000-step task contribute by ratio, not raw steps."""
    progress = make_progress()
    parent = progress.add_task("parent", total=100)
    agg = AggregatedProgress(progress, parent)
    a = agg.add_child_task("a", total=4, weight=1)
    b = agg.add_child_task("b", total=1000, weight=3)
    ta, tb = agg.task_id(a), agg.task_id(b)

    progress.update(ta, completed=4)  # 100% of 4 steps
    progress.update(tb, completed=500)  # 50% of 1000 steps
    state = agg.sync()
    assert state.ratio == pytest.approx(0.625)  # weights 1:3
