# encoding=utf-8
"""Tests for the independent parent/child progress aggregation layer."""

import io

import pytest

from rich.aggregate_progress import AggregateProgress
from rich.console import Console
from rich.progress_aggregate import (
    AggregateStatus,
    ProgressAggregator,
    TaskIdentity,
    TaskStatus,
)


@pytest.fixture
def aggregator():
    return ProgressAggregator()


def test_weighted_ratio_acceptance_scenario(aggregator):
    parent = aggregator.add_parent("parent")
    # weights 1 and 3; completion 100% and 0% -> 25%
    c1 = aggregator.add_child(parent, "a", weight=1, total=4, completed=4)
    c2 = aggregator.add_child(parent, "b", weight=3, total=100, completed=0)
    assert c1 is not c2

    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.RUNNING
    assert snap.percentage == pytest.approx(25.0)
    assert snap.fraction == pytest.approx(0.25)

    # Second task at 50% -> (1*1 + 3*0.5) / 4 = 62.5%
    aggregator.update_child(c2, completed=50)
    snap = aggregator.aggregate(parent)
    assert snap.percentage == pytest.approx(62.5)

    # Making the second task's total unknown makes the parent indeterminate.
    aggregator.update_child(c2, total=None)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.INDETERMINATE
    assert snap.percentage == 0.0


def test_different_totals_are_never_summed(aggregator):
    parent = aggregator.add_parent()
    aggregator.add_child(parent, weight=1, total=10, completed=5)
    aggregator.add_child(parent, weight=1, total=1000, completed=500)
    snap = aggregator.aggregate(parent)
    # 50% and 50% -> 50%, regardless of the very different totals.
    assert snap.fraction == pytest.approx(0.5)


def test_unknown_total_child_makes_parent_indeterminate(aggregator):
    parent = aggregator.add_parent()
    aggregator.add_child(parent, weight=1, total=100, completed=100)
    unknown = aggregator.add_child(parent, weight=2, total=None)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.INDETERMINATE

    # Once a total is known it aggregates normally.
    aggregator.update_child(unknown, total=10, completed=5)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.RUNNING
    assert snap.fraction == pytest.approx((1.0 * 1 + 0.5 * 2) / 3)


def test_successful_child_keeps_final_contribution(aggregator):
    parent = aggregator.add_parent()
    aggregator.add_child(parent, weight=1, total=100, completed=100)
    c2 = aggregator.add_child(parent, weight=1, total=10, completed=3)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.RUNNING
    # c1 auto-succeeded at 100%.
    assert snap.children[0].ratio == 1.0

    # Explicitly succeeding partway freezes that ratio even after more updates.
    aggregator.complete_child(c2)
    snap = aggregator.aggregate(parent)
    assert snap.children[1].ratio == pytest.approx(0.3)
    aggregator.update_child(c2, completed=9)  # later updates do not change frozen ratio
    snap = aggregator.aggregate(parent)
    assert snap.children[1].ratio == pytest.approx(0.3)
    assert snap.status is AggregateStatus.SUCCESS


def test_failed_child_makes_parent_fail_not_complete(aggregator):
    parent = aggregator.add_parent()
    aggregator.add_child(parent, weight=1, total=10, completed=10)
    c2 = aggregator.add_child(parent, weight=1, total=10, completed=10)
    aggregator.fail_child(c2)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.FAILED
    assert snap.finished is True
    # Even though mathematically all ratios are 1.0, failure wins.
    assert snap.fraction == pytest.approx(1.0)

    # Failure of an unfinished child also fails the parent.
    aggregator = ProgressAggregator()
    parent = aggregator.add_parent()
    bad = aggregator.add_child(parent, weight=1, total=10, completed=2)
    aggregator.fail_child(bad)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.FAILED
    assert snap.fraction == pytest.approx(0.2)


def test_failure_keeps_parent_failed_after_other_children_finish(aggregator):
    parent = aggregator.add_parent()
    good = aggregator.add_child(parent, weight=2, total=5, completed=0)
    bad = aggregator.add_child(parent, weight=1, total=5, completed=1)
    aggregator.fail_child(bad)
    aggregator.update_child(good, completed=5)
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.FAILED
    assert snap.status is not AggregateStatus.SUCCESS


def test_empty_parent_is_indeterminate(aggregator):
    parent = aggregator.add_parent()
    snap = aggregator.aggregate(parent)
    assert snap.status is AggregateStatus.INDETERMINATE
    assert snap.fraction == 0.0


def test_task_identity_is_distinct_from_plain_id(aggregator):
    parent = aggregator.add_parent(task_id=7)
    identity = aggregator.add_child(parent, "old", weight=1, total=10, task_id=42)
    assert identity == TaskIdentity(task_id=42, generation=0)
    assert aggregator.get_identity(42) == identity
    old_snapshot = aggregator.aggregate(parent)

    # Remove and rebuild with the SAME plain integer id.
    aggregator.remove_child(parent, identity)
    assert aggregator.get_identity(42) is None
    assert aggregator.is_live(identity) is False

    new_identity = aggregator.add_child(
        parent, "new", weight=1, total=99, completed=99, task_id=42
    )
    assert new_identity.task_id == 42
    assert new_identity != identity
    assert new_identity.generation == identity.generation + 1
    assert aggregator.is_live(identity) is False
    assert aggregator.is_live(new_identity) is True

    # The old snapshot must still describe the old task (ratio 0), and must
    # not associate with the new task even though ids match numerically.
    assert old_snapshot.children[0].identity == identity
    assert old_snapshot.children[0].identity != new_identity
    assert old_snapshot.children[0].total == 10

    new_snapshot = aggregator.aggregate(parent)
    assert new_snapshot.children[0].identity == new_identity
    assert new_snapshot.status is AggregateStatus.SUCCESS


def test_duplicate_live_id_rejected(aggregator):
    aggregator.add_parent(task_id=1)
    with pytest.raises(ValueError):
        aggregator.add_parent(task_id=1)


def test_unknown_identity_lookups_raise(aggregator):
    ghost = TaskIdentity(task_id=999, generation=0)
    with pytest.raises(KeyError):
        aggregator.add_child(ghost, total=1)
    with pytest.raises(KeyError):
        aggregator.aggregate(ghost)
    parent = aggregator.add_parent()
    with pytest.raises(KeyError):
        aggregator.update_child(ghost, advance=1)
    # Removing a child that is not attached must not raise (best effort pop).
    aggregator.remove_child(parent, ghost)


def test_weight_must_be_positive(aggregator):
    parent = aggregator.add_parent()
    with pytest.raises(ValueError):
        aggregator.add_child(parent, weight=0, total=10)
    child = aggregator.add_child(parent, weight=1, total=10)
    with pytest.raises(ValueError):
        aggregator.update_child(child, weight=-2)


def test_snapshots_are_immutable(aggregator):
    from dataclasses import FrozenInstanceError

    parent = aggregator.add_parent()
    aggregator.add_child(parent, weight=1, total=10, completed=5)
    snap = aggregator.aggregate(parent)
    with pytest.raises(FrozenInstanceError):
        snap.fraction = 0.9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snap.children[0].ratio = 0.9  # type: ignore[misc]


def test_auto_assigned_ids_do_not_collide(aggregator):
    p1 = aggregator.add_parent(task_id=1)
    auto_child = aggregator.add_child(p1, total=1)
    auto_parent = aggregator.add_parent()
    assert auto_child.task_id != 1
    assert auto_parent.task_id not in (1, auto_child.task_id)


# ------------------------------------------------------------- rendering


def test_aggregate_progress_renders_with_existing_progress():
    aggregator = ProgressAggregator()
    console = Console(file=io.StringIO(), width=80, legacy_windows=False)
    ap = AggregateProgress(aggregator, console=console, auto_refresh=False)
    parent = aggregator.add_parent("overall")
    aggregator.add_child(parent, "a", weight=1, total=4, completed=4)
    c2 = aggregator.add_child(parent, "b", weight=3, total=10, completed=0)

    ap.sync()
    rich_parent = ap._parent_tasks[parent]
    rich_task = ap.progress._tasks[rich_parent]
    assert rich_task.total == 100
    assert rich_task.completed == pytest.approx(25.0)

    # Indeterminate -> total None on the Progress task.
    aggregator.update_child(c2, total=None)
    ap.sync()
    assert ap.progress._tasks[rich_parent].total is None

    # Failed -> bar kept unfinished and FAILED marker shown.
    aggregator.update_child(c2, total=10, completed=5)
    aggregator.fail_child(c2)
    ap.sync()
    rich_task = ap.progress._tasks[rich_parent]
    assert rich_task.finished_time is None
    assert rich_task.fields["aggregate_status"] == "FAILED"

    # Success of all -> finished. c2 froze its contribution at 0.5 when it
    # failed, completing it later reports SUCCESS with that frozen ratio.
    aggregator.complete_child(c2)
    ap.sync()
    rich_task = ap.progress._tasks[rich_parent]
    assert rich_task.fields["aggregate_status"] == "SUCCESS"
    assert rich_task.completed == pytest.approx(62.5)

    # A clean run where every child really reaches its total renders as a
    # fully finished Progress bar.
    aggregator = ProgressAggregator()
    ap = AggregateProgress(aggregator, console=console, auto_refresh=False)
    parent = aggregator.add_parent("clean")
    aggregator.add_child(parent, weight=1, total=2, completed=2)
    b = aggregator.add_child(parent, weight=1, total=8)
    aggregator.update_child(b, completed=8)
    ap.sync()
    rich_task = ap.progress._tasks[ap._parent_tasks[parent]]
    assert rich_task.fields["aggregate_status"] == "SUCCESS"
    assert rich_task.finished_time is not None
    assert rich_task.completed == pytest.approx(100.0)


def test_aggregate_progress_identity_removal_removes_render_row():
    aggregator = ProgressAggregator()
    console = Console(file=io.StringIO(), width=80, legacy_windows=False)
    ap = AggregateProgress(aggregator, console=console, auto_refresh=False)
    parent = aggregator.add_parent("p")
    child = aggregator.add_child(parent, "c", weight=1, total=10, completed=5)
    ap.sync()
    assert len(ap.progress._tasks) == 1

    aggregator.remove_child(parent, child)
    ap.sync()
    # Parent remains (now indeterminate, empty); child row never existed
    # because show_children defaults to False.
    assert parent in ap._parent_tasks
    assert child not in ap._child_tasks

    # Rebuild with reused id -> new render identity, stale row cleaned.
    new_child = aggregator.add_child(
        parent, "c2", weight=1, total=10, task_id=child.task_id
    )
    ap.sync()
    assert new_child.generation == child.generation + 1
    aggregator.remove_parent(parent)
    ap.sync()
    assert ap._parent_tasks == {}
    assert len(ap.progress._tasks) == 0


def test_aggregate_progress_show_children_rows():
    aggregator = ProgressAggregator()
    console = Console(file=io.StringIO(), width=80, legacy_windows=False)
    ap = AggregateProgress(
        aggregator, console=console, auto_refresh=False, show_children=True
    )
    parent = aggregator.add_parent("p")
    child = aggregator.add_child(parent, "kid", weight=1, total=10, completed=3)
    ap.sync()
    assert len(ap.progress._tasks) == 2
    ap.progress.console.print(ap.progress)
    rendered = ap.progress.console.file.getvalue()
    assert "kid" in rendered
    aggregator.remove_child(parent, child)
    ap.sync()
    assert len(ap.progress._tasks) == 1


def test_state_layer_has_no_render_dependency():
    import inspect

    import rich.progress_aggregate as mod

    source = inspect.getsource(mod)
    assert "from rich" not in source
    assert "import rich" not in source
    assert TaskStatus.RUNNING.active
    assert not TaskStatus.SUCCESS.active
