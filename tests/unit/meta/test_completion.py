from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from windsprig.content import CatalogBundle, load_catalog_bundle
from windsprig.gameplay.snapshot import StageResult
from windsprig.meta import CompletionTracker
from windsprig.meta.completion import (
    CompletionBreakdown,
    CompletionDelta,
    apply_stage_result,
    completion_breakdown,
    completion_percent,
)
from windsprig.meta.save_models import SaveProfile

CONTENT_DIR = Path("windsprig/content")


def _bundle() -> CatalogBundle:
    return load_catalog_bundle(CONTENT_DIR)


def _result(
    *,
    stage_id: str = "world_1_stage_1",
    world_id: str = "world_1",
    node_id: str = "world_1_node_1",
    clear_time_ms: int = 90_000,
    mote_ids: tuple[str, ...] = (),
    ability_ids: tuple[str, ...] = ("galehook",),
) -> StageResult:
    return StageResult(
        stage_id=stage_id,
        world_id=world_id,
        node_id=node_id,
        clear_time_ms=clear_time_ms,
        collected_mote_ids=mote_ids,
        discovered_ability_ids=ability_ids,
        active_slots=(1,),
        deaths_by_slot=((1, 0),),
    )


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


def test_replay_improves_time_and_unique_facts_without_inflation() -> None:
    bundle = _bundle()
    profile = SaveProfile(profile_id="profile_1", display_name="Sprig")
    first, first_delta = apply_stage_result(
        profile,
        _result(
            mote_ids=(
                "world_1_stage_1:mote:1",
                "world_1_stage_1:mote:2",
            )
        ),
        bundle,
    )

    replay, replay_delta = apply_stage_result(
        first,
        _result(
            clear_time_ms=80_000,
            mote_ids=(
                "world_1_stage_1:mote:2",
                "world_1_stage_1:mote:3",
            ),
        ),
        bundle,
    )

    assert replay.collected_mote_ids == frozenset(
        {
            "world_1_stage_1:mote:1",
            "world_1_stage_1:mote:2",
            "world_1_stage_1:mote:3",
        }
    )
    assert replay.best_times_ms["world_1_stage_1"] == 80_000
    assert replay.clear_counts["world_1_stage_1"] == 2
    assert first_delta.new_mote_ids == (
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
    )
    assert first_delta.newly_unlocked_node_ids == ("world_1_node_2",)
    assert replay_delta.new_mote_ids == ("world_1_stage_1:mote:3",)
    assert replay_delta.newly_unlocked_node_ids == ()
    assert replay_delta.previous_best_ms == 90_000
    assert replay_delta.is_new_best is True
    assert profile.clear_counts == {}


def test_slower_replay_never_worsens_the_best_time() -> None:
    bundle = _bundle()
    profile = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        best_times_ms={"world_1_stage_1": 75_000},
        clear_counts={"world_1_stage_1": 2},
    )

    updated, delta = apply_stage_result(profile, _result(clear_time_ms=95_000), bundle)

    assert updated.best_times_ms["world_1_stage_1"] == 75_000
    assert updated.clear_counts["world_1_stage_1"] == 3
    assert delta.previous_best_ms == 75_000
    assert delta.is_new_best is False
    assert delta.first_clear is False


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (_result(stage_id="missing_stage"), "unknown stage_id: missing_stage"),
        (_result(world_id="missing_world"), "unknown world_id: missing_world"),
        (_result(node_id="missing_node"), "unknown node_id: missing_node"),
        (_result(world_id="world_2"), "stage result identity does not match catalog"),
        (
            _result(mote_ids=("world_2_stage_1:mote:1",)),
            "world_2_stage_1:mote:1 is not in world_1_stage_1",
        ),
        (_result(ability_ids=("unknown_ability",)), "unknown ability_id: unknown_ability"),
    ],
)
def test_result_catalog_identity_is_rejected_before_progress_changes(
    result: StageResult,
    message: str,
) -> None:
    profile = SaveProfile(profile_id="profile_1", display_name="Sprig")

    with pytest.raises(ValueError, match=message):
        apply_stage_result(profile, result, _bundle())

    assert profile.clear_counts == {}
    assert profile.unlocked_nodes == frozenset({"world_1_node_1"})


@pytest.mark.parametrize("clear_time_ms", [0, -1, True, 1.5])
def test_result_rejects_non_positive_or_non_integer_clear_time(clear_time_ms: object) -> None:
    forged = replace(_result(), clear_time_ms=clear_time_ms)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="clear_time_ms must be a positive integer"):
        apply_stage_result(
            SaveProfile(profile_id="profile_1", display_name="Sprig"),
            forged,
            _bundle(),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"collected_mote_ids": ("world_1_stage_1:mote:1",) * 2},
            "collected_mote_ids must not contain duplicate IDs",
        ),
        (
            {"discovered_ability_ids": ("galehook", "galehook")},
            "discovered_ability_ids must not contain duplicate IDs",
        ),
        ({"active_slots": ()}, "active_slots must contain at least one slot"),
        ({"active_slots": (True,)}, "active_slots must contain integer slots from 1 to 4"),
        ({"active_slots": (2, 1)}, "active_slots must use canonical ascending order"),
        ({"deaths_by_slot": ((1, True),)}, "death counts must be non-negative integers"),
        ({"deaths_by_slot": ((2, 0),)}, "deaths_by_slot must exactly match active_slots"),
    ],
)
def test_result_rejects_malformed_or_duplicate_collections(
    changes: dict[str, object],
    message: str,
) -> None:
    forged = replace(_result(), **changes)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=message):
        apply_stage_result(
            SaveProfile(profile_id="profile_1", display_name="Sprig"),
            forged,
            _bundle(),
        )


def test_known_but_locked_stage_result_cannot_unlock_progression() -> None:
    profile = SaveProfile(profile_id="profile_1", display_name="Sprig")
    forged = _result(
        stage_id="world_1_stage_2",
        world_id="world_1",
        node_id="world_1_node_2",
    )

    with pytest.raises(ValueError, match="stage is locked: world_1_stage_2"):
        apply_stage_result(profile, forged, _bundle())

    assert profile.unlocked_nodes == frozenset({"world_1_node_1"})


def test_boss_clear_unlocks_the_next_world_in_canonical_campaign_order() -> None:
    profile = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        unlocked_nodes=frozenset({"world_1_node_5"}),
    )
    boss_result = _result(
        stage_id="world_1_stage_5",
        world_id="world_1",
        node_id="world_1_node_5",
        ability_ids=("bloomblade",),
    )

    updated, delta = apply_stage_result(profile, boss_result, _bundle())

    assert "world_2_node_1" in updated.unlocked_nodes
    assert "world_2" in updated.unlocked_worlds
    assert delta.newly_unlocked_node_ids == ("world_2_node_1",)
    assert delta.newly_unlocked_world_ids == ("world_2",)


def test_only_catalog_motes_can_satisfy_reward_thresholds() -> None:
    bundle = _bundle()
    known_motes = tuple(
        mote.mote_id
        for stage in bundle.campaign.stages.values()
        for mote in stage.motes
        if mote.mote_id != "world_1_stage_1:mote:1"
    )[:5]
    unknown_motes = frozenset(f"future:mote:{index}" for index in range(100))
    profile = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        collected_mote_ids=frozenset(known_motes) | unknown_motes,
    )

    updated, delta = apply_stage_result(
        profile,
        _result(mote_ids=("world_1_stage_1:mote:1",)),
        bundle,
    )

    assert delta.new_reward_ids == ("gallery.sunleaf",)
    assert "gallery.sunleaf" in updated.challenge_rewards
    assert unknown_motes < updated.collected_mote_ids

    unknown_only = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        collected_mote_ids=unknown_motes,
    )
    _, unknown_delta = apply_stage_result(
        unknown_only,
        _result(mote_ids=("world_1_stage_1:mote:1",)),
        bundle,
    )
    assert unknown_delta.new_reward_ids == ()


def test_documented_completion_weights_use_only_catalog_known_facts() -> None:
    bundle = _bundle()
    ordered_stages = tuple(sorted(bundle.campaign.stages.values(), key=lambda stage: stage.order))
    first_half = ordered_stages[:15]
    first_half_motes = tuple(mote.mote_id for stage in first_half for mote in stage.motes)
    profile = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        clear_counts={stage.stage_id: 1 for stage in first_half},
        collected_mote_ids=frozenset(first_half_motes),
        challenge_rewards=frozenset(
            {
                "challenge.sunleaf",
                "challenge.emberglass",
                "challenge.tidemoon",
            }
        ),
    )

    breakdown = completion_breakdown(profile, bundle)

    assert breakdown == CompletionBreakdown(
        cleared_stages=15,
        total_stages=30,
        collected_motes=45,
        total_motes=90,
        cleared_bosses=3,
        total_bosses=6,
        challenge_rewards=3,
        total_challenges=6,
        percent=Decimal("50.0"),
    )
    assert completion_percent(profile, bundle) == Decimal("50.0")

    future_only = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        clear_counts={"future_stage": 999},
        collected_mote_ids=frozenset({"future_mote"}),
        challenge_rewards=frozenset({"future_challenge"}),
    )
    assert completion_percent(future_only, bundle) == Decimal("0.0")


def test_completion_rounds_half_up_to_one_decimal_and_clamps_at_one_hundred() -> None:
    bundle = _bundle()
    one_stage = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        clear_counts={"world_1_stage_1": 1},
    )
    all_known = replace(
        one_stage,
        clear_counts={stage_id: 1 for stage_id in bundle.campaign.stages},
        collected_mote_ids=frozenset(mote.mote_id for stage in bundle.campaign.stages.values() for mote in stage.motes),
        challenge_rewards=frozenset(
            reward.reward_id for reward in bundle.rewards.mote_thresholds if reward.kind == "challenge"
        )
        | frozenset({"future_challenge"}),
    )

    assert completion_percent(one_stage, bundle) == Decimal("1.7")
    assert completion_percent(all_known, bundle) == Decimal("100.0")


def test_new_completion_values_are_frozen_and_slotted() -> None:
    profile, delta = apply_stage_result(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _result(),
        _bundle(),
    )
    breakdown = completion_breakdown(profile, _bundle())

    assert isinstance(delta, CompletionDelta)
    assert not hasattr(delta, "__dict__")
    assert not hasattr(breakdown, "__dict__")
    with pytest.raises(FrozenInstanceError):
        delta.first_clear = False  # type: ignore[misc]
