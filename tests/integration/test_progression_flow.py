from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from windsprig.content import load_catalog_bundle
from windsprig.gameplay.snapshot import StageResult
from windsprig.localization import Localizer
from windsprig.meta.completion import apply_stage_result, completion_breakdown, completion_percent
from windsprig.meta.presentation_models import build_profile_cards, build_results_view
from windsprig.meta.save_models import SaveData
from windsprig.meta.world_map import NodeState, build_world_map_view

CONTENT_DIR = Path("windsprig/content")


def test_complete_campaign_progression_is_idempotent_localized_and_camera_ready() -> None:
    bundle = load_catalog_bundle(CONTENT_DIR)
    localizer = Localizer.load(CONTENT_DIR, "en")
    save = SaveData()
    profile = save.profiles[0]
    ordered_worlds = tuple(sorted(bundle.campaign.world_specs.values(), key=lambda world: world.order))
    ordered_nodes = tuple(node for world in ordered_worlds for node in world.nodes)
    last_result: StageResult | None = None
    last_delta = None

    for node in ordered_nodes:
        stage = bundle.campaign.stages[node.stage_id]
        ability_id = next(enemy.ability_id for enemy in stage.enemy_spawns if enemy.ability_id is not None)
        result = StageResult(
            stage_id=stage.stage_id,
            world_id=stage.world_id,
            node_id=stage.node_id,
            clear_time_ms=stage.target_time_ms,
            collected_mote_ids=tuple(mote.mote_id for mote in stage.motes),
            discovered_ability_ids=(ability_id,),
            active_slots=(1,),
            deaths_by_slot=((1, 0),),
        )
        profile, delta = apply_stage_result(profile, result, bundle)
        assert profile.clear_counts[stage.stage_id] == 1
        assert delta.first_clear is True
        last_result = result
        last_delta = delta

    assert last_result is not None and last_delta is not None
    breakdown = completion_breakdown(profile, bundle)
    assert (
        breakdown.cleared_stages,
        breakdown.collected_motes,
        breakdown.cleared_bosses,
        breakdown.challenge_rewards,
    ) == (30, 90, 6, 6)
    assert completion_percent(profile, bundle) == Decimal("100.0")
    assert len(profile.challenge_rewards) == 18
    assert profile.unlocked_worlds == frozenset(f"world_{index}" for index in range(1, 7))

    map_view = build_world_map_view(profile, bundle, "world_6_node_5", localizer)
    assert all(node.state is NodeState.CLEARED for world in map_view.worlds for node in world.nodes)
    assert all(connector.unlocked for world in map_view.worlds for connector in world.connectors)
    assert map_view.total_motes_label == "Wind Motes 90 / 90"
    assert map_view.completion_label == "Completion 100.0%"

    results = build_results_view(last_result, last_delta, profile, bundle, localizer)
    assert results.stage_name == "The Stillness"
    assert results.can_next_stage is False
    assert results.next_stage_id is None

    populated = replace(save, profiles=(profile, save.profiles[1], save.profiles[2]))
    card = build_profile_cards(populated, bundle, localizer)[0]
    assert card.completion_label == "Completion 100.0%"
    assert card.mote_label == "Wind Motes 90 / 90"
    assert card.last_stage_label == "The Stillness"

    faster_replay = replace(last_result, clear_time_ms=last_result.clear_time_ms - 1_000)
    replayed, replay_delta = apply_stage_result(profile, faster_replay, bundle)
    assert replayed.clear_counts[last_result.stage_id] == 2
    assert len(replayed.collected_mote_ids) == 90
    assert replay_delta.new_mote_ids == ()
    assert replay_delta.new_reward_ids == ()
    assert replay_delta.newly_unlocked_node_ids == ()
    assert completion_percent(replayed, bundle) == Decimal("100.0")
