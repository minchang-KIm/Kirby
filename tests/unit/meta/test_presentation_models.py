from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from windsprig.content import CatalogBundle, load_catalog_bundle
from windsprig.gameplay.snapshot import StageResult
from windsprig.localization import Localizer
from windsprig.meta.completion import CompletionDelta, apply_stage_result
from windsprig.meta.presentation_models import build_profile_cards, build_results_view
from windsprig.meta.save_models import SaveData, SaveProfile

CONTENT_DIR = Path("windsprig/content")


def _bundle() -> CatalogBundle:
    return load_catalog_bundle(CONTENT_DIR)


def _localizer(language: str = "en") -> Localizer:
    return Localizer.load(CONTENT_DIR, language)  # type: ignore[arg-type]


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


def test_profile_cards_show_three_localized_summary_views() -> None:
    save = SaveData()

    cards = build_profile_cards(save, _bundle(), _localizer())

    assert len(cards) == 3
    assert cards[0].slot_index == 1
    assert cards[0].profile_id == "profile_1"
    assert cards[0].display_name == "Sprig 1"
    assert cards[0].completion_label == "Completion 0.0%"
    assert cards[0].mote_label == "Wind Motes 0 / 90"
    assert cards[0].play_time_label == "Play time 00:00:00"
    assert cards[0].last_stage_label == "No stage played"
    assert cards[0].is_empty is True


def test_profile_card_localizes_last_stage_and_formats_long_play_time() -> None:
    save = SaveData()
    profile = replace(
        save.profiles[0],
        clear_counts={"world_1_stage_1": 1},
        collected_mote_ids=frozenset({"world_1_stage_1:mote:1"}),
        play_time_ms=3_661_999,
        last_played_stage="world_1_stage_1",
    )
    populated = replace(save, profiles=(profile, save.profiles[1], save.profiles[2]))

    english = build_profile_cards(populated, _bundle(), _localizer())[0]
    korean = build_profile_cards(populated, _bundle(), _localizer("ko"))[0]

    assert english.last_stage_label == "First Flight"
    assert english.play_time_label == "Play time 01:01:01"
    assert english.is_empty is False
    assert korean.last_stage_label == "첫 비행"
    assert korean.play_time_label == "플레이 시간 01:01:01"


def test_profile_cards_reject_unknown_last_stage_instead_of_hiding_save_drift() -> None:
    save = SaveData()
    profile = replace(save.profiles[0], last_played_stage="future_stage")
    drifted = replace(save, profiles=(profile, save.profiles[1], save.profiles[2]))

    with pytest.raises(ValueError, match="unknown last_played_stage: future_stage"):
        build_profile_cards(drifted, _bundle(), _localizer())


def test_results_view_localizes_stage_times_motes_ability_and_next_stage() -> None:
    bundle = _bundle()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    result = _result(
        mote_ids=("world_1_stage_1:mote:1", "world_1_stage_1:mote:2"),
    )
    profile, delta = apply_stage_result(before, result, bundle)

    view = build_results_view(
        result,
        delta,
        profile,
        bundle,
        _localizer(),
        before_profile=before,
    )

    assert view.stage_name == "First Flight"
    assert view.clear_time_label == "Time 01:30.000"
    assert view.best_time_label == "Best 01:30.000"
    assert view.comparison_label == "First clear"
    assert view.new_best is True
    assert tuple(mote.mote_id for mote in view.motes) == (
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
        "world_1_stage_1:mote:3",
    )
    assert tuple((mote.collected_before, mote.collected_this_run) for mote in view.motes) == (
        (False, True),
        (False, True),
        (False, False),
    )
    assert view.ability_labels == ("Galehook",)
    assert tuple((unlock.reward_id, unlock.label, unlock.kind) for unlock in view.unlocks) == (
        ("world_1_node_2", "Millstream Run", "stage"),
    )
    assert view.completion_label == "Completion 2.3%"
    assert view.can_next_stage is True
    assert view.next_stage_id == "world_1_stage_2"


def test_replay_results_compare_against_previous_best_and_preserve_mote_history() -> None:
    bundle = _bundle()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    first_result = _result(
        mote_ids=("world_1_stage_1:mote:1", "world_1_stage_1:mote:2"),
    )
    first, _ = apply_stage_result(before, first_result, bundle)
    replay_result = _result(
        clear_time_ms=80_000,
        mote_ids=("world_1_stage_1:mote:2", "world_1_stage_1:mote:3"),
    )
    replay, delta = apply_stage_result(first, replay_result, bundle)

    view = build_results_view(
        replay_result,
        delta,
        replay,
        bundle,
        _localizer(),
        before_profile=first,
    )

    assert view.comparison_label == "New best! 00:10.000 faster"
    assert tuple((mote.collected_before, mote.collected_this_run) for mote in view.motes) == (
        (True, False),
        (True, True),
        (False, True),
    )
    assert view.can_next_stage is False
    assert view.next_stage_id is None


def test_slower_replay_has_no_false_comparison_or_new_best_badge() -> None:
    bundle = _bundle()
    first, _ = apply_stage_result(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _result(clear_time_ms=80_000),
        bundle,
    )
    slower_result = _result(clear_time_ms=90_000)
    replay, delta = apply_stage_result(first, slower_result, bundle)

    view = build_results_view(
        slower_result,
        delta,
        replay,
        bundle,
        _localizer(),
        before_profile=first,
    )

    assert view.comparison_label == ""
    assert view.new_best is False


def test_boss_result_lists_stage_world_and_threshold_unlocks_in_canonical_order() -> None:
    bundle = _bundle()
    known_motes = tuple(
        mote.mote_id
        for stage in bundle.campaign.stages.values()
        for mote in stage.motes
        if mote.mote_id != "world_1_stage_5:mote:1"
    )[:17]
    before = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        unlocked_nodes=frozenset({"world_1_node_5"}),
        collected_mote_ids=frozenset(known_motes),
    )
    result = _result(
        stage_id="world_1_stage_5",
        world_id="world_1",
        node_id="world_1_node_5",
        mote_ids=("world_1_stage_5:mote:1",),
        ability_ids=("bloomblade",),
    )
    profile, delta = apply_stage_result(before, result, bundle)

    view = build_results_view(
        result,
        delta,
        profile,
        bundle,
        _localizer(),
        before_profile=before,
    )

    assert tuple((unlock.reward_id, unlock.kind) for unlock in view.unlocks) == (
        ("world_2_node_1", "stage"),
        ("world_2", "world"),
        ("gallery.sunleaf", "gallery"),
        ("palette.mint", "palette"),
        ("challenge.sunleaf", "challenge"),
    )
    assert tuple(unlock.label for unlock in view.unlocks) == (
        "Kilnwalk",
        "Emberglass Works",
        "Sunleaf gallery",
        "Mint palette",
        "Sunleaf challenge",
    )


def test_results_view_is_fully_localized_in_korean() -> None:
    bundle = _bundle()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    result = _result(mote_ids=("world_1_stage_1:mote:1",))
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )

    view = build_results_view(
        result,
        delta,
        profile,
        bundle,
        _localizer("ko"),
        before_profile=before,
    )

    assert view.stage_name == "첫 비행"
    assert view.clear_time_label == "기록 01:30.000"
    assert view.best_time_label == "최고 01:30.000"
    assert view.comparison_label == "첫 완료"
    assert view.ability_labels == ("질풍갈고리",)
    assert view.unlocks[0].label == "물레바람 질주"
    assert view.completion_label == "달성도 2.0%"


def test_results_reject_unknown_delta_reward_instead_of_displaying_internal_id() -> None:
    bundle = _bundle()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    result = _result()
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )
    forged = replace(delta, new_reward_ids=("future.reward",))

    with pytest.raises(
        ValueError,
        match="completion delta does not match canonical result application",
    ):
        build_results_view(
            result,
            forged,
            profile,
            bundle,
            _localizer(),
            before_profile=before,
        )


def test_presentation_models_are_frozen_slotted_and_hold_only_immutable_values() -> None:
    bundle = _bundle()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    result = _result()
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )
    results = build_results_view(
        result,
        delta,
        profile,
        bundle,
        _localizer(),
        before_profile=before,
    )
    cards = build_profile_cards(SaveData(), bundle, _localizer())

    assert not hasattr(results, "__dict__")
    assert not hasattr(results.motes[0], "__dict__")
    assert not hasattr(cards[0], "__dict__")
    assert isinstance(results.unlocks, tuple)
    with pytest.raises(FrozenInstanceError):
        results.new_best = False  # type: ignore[misc]


def test_results_reject_inconsistent_delta_identity() -> None:
    bundle = _bundle()
    result = _result()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    profile, _ = apply_stage_result(
        before,
        result,
        bundle,
    )
    forged = CompletionDelta(
        first_clear=True,
        new_mote_ids=(),
        newly_discovered_abilities=(),
        newly_unlocked_node_ids=("missing_node",),
        newly_unlocked_world_ids=(),
        new_reward_ids=(),
        previous_best_ms=None,
        is_new_best=True,
    )

    with pytest.raises(
        ValueError,
        match="completion delta does not match canonical result application",
    ):
        build_results_view(
            result,
            forged,
            profile,
            bundle,
            _localizer(),
            before_profile=before,
        )


def test_results_require_the_post_application_best_time() -> None:
    bundle = _bundle()
    result = _result()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )
    inconsistent = replace(profile, best_times_ms={})

    with pytest.raises(
        ValueError,
        match="post profile progression does not match canonical result application: best_times_ms",
    ):
        build_results_view(
            result,
            delta,
            inconsistent,
            bundle,
            _localizer(),
            before_profile=before,
        )


@pytest.mark.parametrize(
    ("delta_changes", "profile_changes"),
    [
        (
            {"newly_unlocked_node_ids": ("world_6_node_1",)},
            {"unlocked_nodes": frozenset({"world_1_node_1", "world_6_node_1"})},
        ),
        (
            {"newly_unlocked_world_ids": ("world_6",)},
            {"unlocked_worlds": frozenset({"world_1", "world_6"})},
        ),
        (
            {"new_reward_ids": ("challenge.stillstar",)},
            {"challenge_rewards": frozenset({"challenge.stillstar"})},
        ),
    ],
)
def test_results_reject_persisted_but_semantically_unrelated_known_delta_ids(
    delta_changes: dict[str, object],
    profile_changes: dict[str, object],
) -> None:
    bundle = _bundle()
    result = _result()
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )
    forged_delta = replace(delta, **delta_changes)  # type: ignore[arg-type]
    forged_profile = replace(profile, **profile_changes)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="completion delta does not match canonical result application",
    ):
        build_results_view(
            result,
            forged_delta,
            forged_profile,
            bundle,
            _localizer(),
            before_profile=before,
        )


def test_replay_cannot_forge_the_following_node_to_enable_next_stage() -> None:
    bundle = _bundle()
    first, _ = apply_stage_result(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _result(clear_time_ms=80_000),
        bundle,
    )
    replay_result = _result(clear_time_ms=90_000)
    replay, delta = apply_stage_result(first, replay_result, bundle)
    forged = replace(delta, newly_unlocked_node_ids=("world_1_node_2",))

    with pytest.raises(
        ValueError,
        match="completion delta does not match canonical result application",
    ):
        build_results_view(
            replay_result,
            forged,
            replay,
            bundle,
            _localizer(),
            before_profile=first,
        )


@pytest.mark.parametrize(
    ("profile_changes", "message"),
    [
        (
            {"clear_counts": {}},
            "post profile progression does not match canonical result application: clear_counts",
        ),
        (
            {"collected_mote_ids": frozenset()},
            "post profile progression does not match canonical result application: collected_mote_ids",
        ),
        (
            {"discovered_abilities": frozenset()},
            "post profile progression does not match canonical result application: discovered_abilities",
        ),
        (
            {"last_played_stage": None},
            "post profile progression does not match canonical result application: last_played_stage",
        ),
        (
            {"best_times_ms": {"world_1_stage_1": 95_000}},
            "post profile progression does not match canonical result application: best_times_ms",
        ),
        (
            {"clear_counts": {"world_1_stage_1": 2}},
            "post profile progression does not match canonical result application: clear_counts",
        ),
    ],
)
def test_results_require_all_applied_result_facts_in_the_post_profile(
    profile_changes: dict[str, object],
    message: str,
) -> None:
    bundle = _bundle()
    result = _result(mote_ids=("world_1_stage_1:mote:1",))
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )
    forged_profile = replace(profile, **profile_changes)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=message):
        build_results_view(
            result,
            delta,
            forged_profile,
            bundle,
            _localizer(),
            before_profile=before,
        )


def test_results_require_every_reported_new_fact_in_the_post_profile() -> None:
    bundle = _bundle()
    result = _result(mote_ids=("world_1_stage_1:mote:1",))
    before = SaveProfile(profile_id="profile_1", display_name="Sprig")
    profile, delta = apply_stage_result(
        before,
        result,
        bundle,
    )
    missing_node = replace(
        profile,
        unlocked_nodes=frozenset({"world_1_node_1"}),
    )

    with pytest.raises(
        ValueError,
        match="post profile progression does not match canonical result application: unlocked_nodes",
    ):
        build_results_view(
            result,
            delta,
            missing_node,
            bundle,
            _localizer(),
            before_profile=before,
        )

    known_motes = tuple(
        mote.mote_id
        for stage in bundle.campaign.stages.values()
        for mote in stage.motes
        if mote.mote_id != "world_1_stage_1:mote:1"
    )[:5]
    reward_before = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        collected_mote_ids=frozenset(known_motes),
    )
    reward_profile, reward_delta = apply_stage_result(
        reward_before,
        result,
        bundle,
    )
    missing_reward = replace(reward_profile, challenge_rewards=frozenset())

    with pytest.raises(
        ValueError,
        match="post profile progression does not match canonical result application: challenge_rewards",
    ):
        build_results_view(
            result,
            reward_delta,
            missing_reward,
            bundle,
            _localizer(),
            before_profile=reward_before,
        )


def test_replay_can_canonically_repair_a_missing_following_node() -> None:
    bundle = _bundle()
    first, _ = apply_stage_result(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _result(clear_time_ms=80_000),
        bundle,
    )
    before_repair = replace(
        first,
        unlocked_nodes=frozenset({"world_1_node_1"}),
    )
    replay_result = _result(clear_time_ms=90_000)
    repaired, delta = apply_stage_result(before_repair, replay_result, bundle)

    view = build_results_view(
        replay_result,
        delta,
        repaired,
        bundle,
        _localizer(),
        before_profile=before_repair,
    )

    assert delta.first_clear is False
    assert delta.newly_unlocked_node_ids == ("world_1_node_2",)
    assert view.can_next_stage is True
    assert view.next_stage_id == "world_1_stage_2"


@pytest.mark.parametrize(
    ("before", "expected_best_label"),
    [
        (
            SaveProfile(
                profile_id="profile_1",
                display_name="Sprig",
                clear_counts={"world_1_stage_1": 5},
            ),
            "Best 01:30.000",
        ),
        (
            SaveProfile(
                profile_id="profile_1",
                display_name="Sprig",
                best_times_ms={"world_1_stage_1": 70_000},
            ),
            "Best 01:10.000",
        ),
    ],
    ids=("clear-count-without-best", "best-without-clear-count"),
)
def test_results_accept_canonical_application_from_independently_drifted_stage_maps(
    before: SaveProfile,
    expected_best_label: str,
) -> None:
    bundle = _bundle()
    result = _result(clear_time_ms=90_000)
    profile, delta = apply_stage_result(before, result, bundle)

    view = build_results_view(
        result,
        delta,
        profile,
        bundle,
        _localizer(),
        before_profile=before,
    )

    assert view.new_best is delta.is_new_best
    assert view.best_time_label == expected_best_label


@pytest.mark.parametrize(
    ("delta_field", "old_fact"),
    [
        ("new_mote_ids", "world_1_stage_1:mote:1"),
        ("newly_discovered_abilities", "galehook"),
        ("new_reward_ids", "gallery.sunleaf"),
    ],
)
def test_replay_cannot_forge_already_owned_facts_as_new(
    delta_field: str,
    old_fact: str,
) -> None:
    bundle = _bundle()
    old_mote_id = "world_1_stage_1:mote:1"
    other_motes = tuple(
        mote.mote_id for stage in bundle.campaign.stages.values() for mote in stage.motes if mote.mote_id != old_mote_id
    )[:5]
    known_motes = (old_mote_id, *other_motes)
    before = SaveProfile(
        profile_id="profile_1",
        display_name="Sprig",
        unlocked_nodes=frozenset({"world_1_node_1", "world_1_node_2"}),
        collected_mote_ids=frozenset(known_motes),
        best_times_ms={"world_1_stage_1": 80_000},
        clear_counts={"world_1_stage_1": 1},
        discovered_abilities=frozenset({"galehook"}),
        challenge_rewards=frozenset({"gallery.sunleaf"}),
        last_played_stage="world_1_stage_1",
    )
    replay_result = _result(
        clear_time_ms=90_000,
        mote_ids=("world_1_stage_1:mote:1",),
    )
    profile, delta = apply_stage_result(before, replay_result, bundle)
    forged = replace(delta, **{delta_field: (old_fact,)})  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="completion delta does not match canonical result application",
    ):
        build_results_view(
            replay_result,
            forged,
            profile,
            bundle,
            _localizer(),
            before_profile=before,
        )


def test_ordinary_replay_cannot_forge_next_node_with_its_actual_before_profile() -> None:
    bundle = _bundle()
    before, _ = apply_stage_result(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _result(clear_time_ms=80_000),
        bundle,
    )
    replay_result = _result(clear_time_ms=90_000)
    profile, delta = apply_stage_result(before, replay_result, bundle)
    forged = replace(delta, newly_unlocked_node_ids=("world_1_node_2",))

    with pytest.raises(
        ValueError,
        match="completion delta does not match canonical result application",
    ):
        build_results_view(
            replay_result,
            forged,
            profile,
            bundle,
            _localizer(),
            before_profile=before,
        )
