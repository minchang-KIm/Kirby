from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from windsprig.config import GameConfig
from windsprig.content import CatalogBundle, load_catalog_bundle
from windsprig.feasibility import FoundationProbe
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.snapshot import StageOutcome, StageResult
from windsprig.input.roster import ActiveRoster, DeviceRef
from windsprig.localization import Localizer
from windsprig.meta import SaveLoadResult, SaveWriteResult, migration_catalog
from windsprig.meta.completion import (
    apply_stage_result,
    completion_breakdown,
    completion_percent,
)
from windsprig.meta.presentation_models import build_profile_cards, build_results_view
from windsprig.meta.save_models import SaveData
from windsprig.meta.world_map import NodeState, build_world_map_view
from windsprig.screens.foundation import FoundationScreen

CONTENT_DIR = Path("windsprig/content")


class _ProgressionSaveService:
    def __init__(self, data: SaveData) -> None:
        self.data = data
        self.saved: list[SaveData] = []

    def load(self) -> SaveLoadResult:
        return SaveLoadResult(self.data)

    def save(self, data: SaveData) -> SaveWriteResult:
        self.saved.append(data)
        self.data = data
        return SaveWriteResult(ok=True)

    def confirm_reset(self, data: SaveData) -> SaveWriteResult:
        return self.save(data)


class _ProbeStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read_text(self, key: str) -> str | None:
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(key for key in sorted(self.values) if key.startswith(prefix))


def _foundation_screen(
    bundle: CatalogBundle,
    save_data: SaveData,
) -> tuple[FoundationScreen, _ProgressionSaveService]:
    config = GameConfig()
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    save_service = _ProgressionSaveService(save_data)
    return (
        FoundationScreen(
            config=config,
            roster=roster,
            save_service=save_service,
            catalog=bundle.campaign,
            ability_registry=create_default_registry(CONTENT_DIR),
            migration_catalog=migration_catalog(bundle.campaign),
            probe=FoundationProbe(_ProbeStorage(), enabled=False),
            progression_catalog=bundle,
        ),
        save_service,
    )


def test_complete_campaign_progression_is_idempotent_localized_and_camera_ready() -> None:
    bundle = load_catalog_bundle(CONTENT_DIR)
    localizer = Localizer.load(CONTENT_DIR, "en")
    save = SaveData()
    profile = save.profiles[0]
    ordered_worlds = tuple(sorted(bundle.campaign.world_specs.values(), key=lambda world: world.order))
    ordered_nodes = tuple(node for world in ordered_worlds for node in world.nodes)
    last_result: StageResult | None = None
    last_delta = None
    last_before = profile

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
        last_before = profile
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

    results = build_results_view(
        last_result,
        last_delta,
        profile,
        bundle,
        localizer,
        before_profile=last_before,
    )
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


def test_foundation_completion_projects_the_canonical_result_without_count_synthesis() -> None:
    bundle = load_catalog_bundle(CONTENT_DIR)
    stage = bundle.campaign.stages["world_1_stage_1"]
    exact_mote_id = "world_1_stage_1:mote:3"
    prior_motes = tuple(
        mote.mote_id
        for candidate in bundle.campaign.stages.values()
        if candidate.stage_id != stage.stage_id
        for mote in candidate.motes
    )[:5]
    baseline = SaveData()
    profile = replace(
        baseline.profiles[0],
        collected_mote_ids=frozenset(prior_motes),
    )
    save_data = replace(
        baseline,
        profiles=(profile, baseline.profiles[1], baseline.profiles[2]),
    )
    screen, save_service = _foundation_screen(bundle, save_data)
    frame_index = 625
    screen.runtime = SimpleNamespace(
        stage=stage,
        result=None,
        player_entities={1: 1001},
        world=SimpleNamespace(
            frame_index=frame_index,
            resources={
                "run_energy_spheres": 3,
                "collected_mote_ids": {exact_mote_id},
                "discovered_ability_ids": {"galehook"},
                "deaths_by_slot": {1: 2},
            },
        ),
        snapshot=lambda: SimpleNamespace(outcome=StageOutcome.COMPLETED),
    )
    expected_result = StageResult(
        stage_id=stage.stage_id,
        world_id=stage.world_id,
        node_id=stage.node_id,
        clear_time_ms=frame_index * screen.config.fixed_dt_ms,
        collected_mote_ids=(exact_mote_id,),
        discovered_ability_ids=("galehook",),
        active_slots=(1,),
        deaths_by_slot=((1, 2),),
    )
    expected_profile, _ = apply_stage_result(profile, expected_result, bundle)

    assert screen._on_stage_progress() is True

    actual_profile = screen.save_data.profiles[0]
    assert actual_profile == expected_profile
    assert save_service.saved[-1].profiles[0] == expected_profile
    assert actual_profile.collected_mote_ids - frozenset(prior_motes) == frozenset({exact_mote_id})
    assert actual_profile.discovered_abilities == frozenset({"galehook"})
    assert actual_profile.challenge_rewards == frozenset({"gallery.sunleaf"})
    assert actual_profile.unlocked_nodes == frozenset({"world_1_node_1", "world_1_node_2"})
    assert actual_profile.clear_counts == {stage.stage_id: 1}
    assert actual_profile.best_times_ms == {stage.stage_id: frame_index * screen.config.fixed_dt_ms}
    assert screen.tracker.collected_mote_ids == set(actual_profile.collected_mote_ids)
    assert screen.tracker.discovered_abilities == {"galehook"}
    assert screen.tracker.challenge_rewards == {"gallery.sunleaf"}
