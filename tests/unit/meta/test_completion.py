from __future__ import annotations

import pytest

from windsprig.meta import CompletionTracker


def test_stage_clear_tracks_best_non_negative_time_and_clear_count() -> None:
    tracker = CompletionTracker()

    tracker.mark_stage_clear("world_1_node_1", "world_1_stage_1", 10000)
    tracker.mark_stage_clear("world_1_node_1", "world_1_stage_1", 12000)
    tracker.mark_stage_clear("world_1_node_1", "world_1_stage_1", 9000)

    assert tracker.cleared_nodes == {"world_1_node_1"}
    assert tracker.best_times_ms == {"world_1_stage_1": 9000}
    assert tracker.clear_counts == {"world_1_stage_1": 3}


@pytest.mark.parametrize("elapsed_ms", [-1, True, 1.5])
def test_stage_clear_rejects_invalid_elapsed_time(elapsed_ms: object) -> None:
    tracker = CompletionTracker()

    with pytest.raises(ValueError, match="elapsed_ms"):
        tracker.mark_stage_clear(  # type: ignore[arg-type]
            "world_1_node_1",
            "world_1_stage_1",
            elapsed_ms,
        )

    assert tracker.cleared_nodes == set()


def test_stage_clear_rejects_invalid_stage_id_before_mutating_progression() -> None:
    tracker = CompletionTracker()

    with pytest.raises(ValueError, match="stage_id"):
        tracker.mark_stage_clear("world_1_node_1", " ", 1000)

    assert tracker.cleared_nodes == set()


def test_collect_mote_uses_stable_id_and_is_idempotent() -> None:
    tracker = CompletionTracker()

    tracker.collect_mote("world_1_stage_1:mote:1")
    tracker.collect_mote("world_1_stage_1:mote:1")

    assert tracker.collected_mote_ids == {"world_1_stage_1:mote:1"}


@pytest.mark.parametrize("mote_id", ["", " ", " padded", 1])
def test_collect_mote_rejects_invalid_ids(mote_id: object) -> None:
    with pytest.raises(ValueError, match="mote_id"):
        CompletionTracker().collect_mote(mote_id)  # type: ignore[arg-type]
