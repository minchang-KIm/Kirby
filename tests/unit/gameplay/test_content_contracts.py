"""Contract tests for gameplay content, tuning, events, and view DTOs."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import cast

import pytest

from tests.helpers.gameplay import make_active_player, make_stage
from windsprig.config import GameConfig
from windsprig.content.loader import (
    LEGACY_ABILITY_IDS,
    CheckpointSpec,
    ContentError,
    EnemySpawn,
    InteractionSpec,
    MoteSpec,
    StageSpec,
    load_campaign_catalog,
)
from windsprig.core.ecs import World
from windsprig.gameplay.events import GameplayTopic, make_event, publish
from windsprig.gameplay.snapshot import (
    AttackView,
    CameraTargetView,
    CheckpointView,
    EchoPickupView,
    EnemyView,
    GoalGatherView,
    InteractionView,
    PlayerView,
    StageFrame,
    StageOutcome,
    StageResult,
    StageSnapshot,
)
from windsprig.meta.save_migrations import migration_catalog

PUBLIC_ABILITY_IDS = {
    "bloomblade",
    "cinder",
    "voltsong",
    "galehook",
    "stoneheart",
    "tempest",
}


def test_current_catalog_adapts_to_stable_public_gameplay_fields() -> None:
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]

    assert tuple(mote.mote_id for mote in stage.motes) == (
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
        "world_1_stage_1:mote:3",
    )
    assert stage.checkpoints[0].checkpoint_id == "world_1_stage_1.start"
    assert all(enemy.ability_id in PUBLIC_ABILITY_IDS for enemy in stage.enemy_spawns if enemy.ability_id is not None)
    assert not hasattr(stage, "energy_spheres")
    assert not hasattr(stage.enemy_spawns[0], "copy_ability")


def test_catalog_preserves_all_thirty_stages_and_ninety_stable_mote_ids() -> None:
    catalog = load_campaign_catalog(Path("windsprig/content"))
    mote_ids = tuple(mote.mote_id for stage in catalog.stages.values() for mote in stage.motes)
    ability_ids = {
        enemy.ability_id
        for stage in catalog.stages.values()
        for enemy in stage.enemy_spawns
        if enemy.ability_id is not None
    }

    assert len(catalog.stages) == 30
    assert len(mote_ids) == len(set(mote_ids)) == 90
    assert all(
        tuple(mote.mote_id for mote in stage.motes) == tuple(f"{stage.stage_id}:mote:{index}" for index in range(1, 4))
        for stage in catalog.stages.values()
    )
    assert ability_ids == PUBLIC_ABILITY_IDS
    assert LEGACY_ABILITY_IDS == {
        "sword": "bloomblade",
        "spear": "bloomblade",
        "fighter": "bloomblade",
        "fire": "cinder",
        "monster_flame": "cinder",
        "beam": "voltsong",
        "spark": "voltsong",
        "cutter": "galehook",
        "whip": "galehook",
        "ninja": "galehook",
        "parasol": "galehook",
        "ice": "stoneheart",
        "hammer": "stoneheart",
        "grand_hammer": "stoneheart",
        "ultra_sword": "tempest",
    }
    assert all(
        isinstance(sequence, tuple)
        for stage in catalog.stages.values()
        for sequence in (
            stage.player_spawns,
            stage.enemy_spawns,
            stage.motes,
            stage.checkpoints,
            stage.interactions,
            stage.hazards,
            stage.one_way_tiles,
            stage.solids,
        )
    )


def test_gameplay_mote_ids_are_the_existing_save_migration_ids() -> None:
    catalog = load_campaign_catalog(Path("windsprig/content"))
    save_catalog = migration_catalog(catalog)

    assert {
        stage_id: tuple(mote.mote_id for mote in stage.motes) for stage_id, stage in catalog.stages.items()
    } == dict(save_catalog.mote_ids_by_stage)


def test_gameplay_tuning_is_explicit() -> None:
    config = GameConfig()

    assert (config.coyote_time_ms, config.jump_buffer_ms, config.hover_duration_ms) == (100, 120, 850)
    assert config.hover_gravity_scale == pytest.approx(0.28)
    assert (
        config.guard_damage_multiplier,
        config.guard_knockback_multiplier,
        config.guard_speed_multiplier,
    ) == pytest.approx((0.40, 0.35, 0.40))
    assert (
        config.dodge_duration_ms,
        config.dodge_invulnerable_ms,
        config.dodge_cooldown_ms,
        config.dodge_speed,
    ) == (160, 128, 520, 620.0)
    assert (
        config.draw_base_range_px,
        config.draw_range_growth_px_per_ms,
        config.draw_max_bonus_range_px,
    ) == pytest.approx((78.0, 0.20, 80.0))
    assert (
        config.respawn_delay_ms,
        config.respawn_invulnerable_ms,
        config.gather_countdown_ms,
    ) == (1800, 1200, 3000)


def test_event_factory_injects_frame_and_rejects_unknown_topics() -> None:
    event = make_event(GameplayTopic.PLAYER_DODGED, 7, entity_id=2, slot=1, direction=-1)

    assert event.topic == "PlayerDodged"
    assert event.payload == {"frame_index": 7, "entity_id": 2, "slot": 1, "direction": -1}
    with pytest.raises(TypeError, match="GameplayTopic"):
        make_event(cast(GameplayTopic, "UnknownTopic"), 7)
    with pytest.raises(TypeError, match="frame_index"):
        make_event(GameplayTopic.PLAYER_DODGED, 7, **{"frame_index": 99})


def test_gameplay_topics_match_the_presentation_contract() -> None:
    assert tuple(topic.value for topic in GameplayTopic) == (
        "PlayerJoined",
        "PlayerLeft",
        "PlayerDamaged",
        "PlayerDodged",
        "EnemyCaptured",
        "CaptureReleased",
        "EnemyLaunched",
        "HarmonizeUnavailable",
        "AbilityEquipped",
        "AbilityDropped",
        "AbilityUsed",
        "AttackSpawned",
        "AttackHit",
        "ProjectileCut",
        "EnemyDefeated",
        "MoteCollected",
        "CheckpointReached",
        "PlayerDefeated",
        "PlayerRespawned",
        "GatherStarted",
        "GatherCancelled",
        "GatherCompleted",
        "StageCompleted",
        "StageFailed",
    )


def test_publish_uses_the_world_frame_and_foundation_event_bus() -> None:
    world = World()
    world.frame_index = 19

    publish(world, GameplayTopic.MOTE_COLLECTED, mote_id="stage.mote.1", player_id=3, slot=1)

    assert world.events.peek() == [
        make_event(
            GameplayTopic.MOTE_COLLECTED,
            19,
            mote_id="stage.mote.1",
            player_id=3,
            slot=1,
        )
    ]


def test_stage_spec_retains_the_stable_gameplay_field_prefix() -> None:
    assert tuple(field.name for field in fields(MoteSpec))[:3] == ("mote_id", "tile_x", "tile_y")
    assert tuple(field.name for field in fields(CheckpointSpec)) == (
        "checkpoint_id",
        "tile_x",
        "tile_y",
    )
    assert tuple(field.name for field in fields(InteractionSpec))[:6] == (
        "interaction_id",
        "kind",
        "tile_x",
        "tile_y",
        "width_tiles",
        "height_tiles",
    )
    assert tuple(field.name for field in fields(EnemySpawn))[:6] == (
        "x",
        "y",
        "kind",
        "ability_id",
        "patrol_left",
        "patrol_right",
    )
    assert tuple(field.name for field in fields(StageSpec))[:16] == (
        "stage_id",
        "world_id",
        "node_id",
        "width_tiles",
        "height_tiles",
        "tile_size",
        "ground_y_tile",
        "player_spawns",
        "enemy_spawns",
        "motes",
        "checkpoints",
        "interactions",
        "goal_tile",
        "hazards",
        "one_way_tiles",
        "solids",
    )
    with pytest.raises(FrozenInstanceError):
        MoteSpec("stage:mote:1", 1, 2).tile_x = 9  # type: ignore[misc]
    assert all(
        hasattr(content_type, "__slots__")
        for content_type in (MoteSpec, CheckpointSpec, InteractionSpec, EnemySpawn, StageSpec)
    )


def test_authored_empty_collections_and_interactions_default_size(
    tmp_path: Path,
) -> None:
    payload = _one_stage_campaign(
        {
            "motes": [],
            "checkpoints": [],
            "interactions": [
                {
                    "interaction_id": "test.conductor",
                    "kind": "conductor",
                    "tile_x": 6,
                    "tile_y": 7,
                }
            ],
            "enemy_spawns": [
                {
                    "x": 64,
                    "y": 96,
                    "kind": "wisp",
                    "ability_id": "cinder",
                    "patrol_left": 32,
                    "patrol_right": 128,
                }
            ],
        }
    )
    (tmp_path / "campaign.json").write_text(json.dumps(payload), encoding="utf-8")

    stage = load_campaign_catalog(tmp_path).stages["test_stage"]

    assert stage.motes == ()
    assert stage.checkpoints == ()
    assert stage.enemy_spawns[0].ability_id == "cinder"
    assert (stage.interactions[0].width_tiles, stage.interactions[0].height_tiles) == (1, 1)


def test_authored_motes_checkpoints_and_interaction_bounds_load_without_legacy_names(
    tmp_path: Path,
) -> None:
    payload = _one_stage_campaign(
        {
            "motes": [{"mote_id": "test_stage:mote:1", "tile_x": 3, "tile_y": 4}],
            "checkpoints": [
                {
                    "checkpoint_id": "test_stage.midway",
                    "tile_x": 5,
                    "tile_y": 6,
                }
            ],
            "interactions": [
                {
                    "interaction_id": "test.switch",
                    "kind": "switch",
                    "tile_x": 7,
                    "tile_y": 3,
                    "width_tiles": 2,
                    "height_tiles": 3,
                }
            ],
        }
    )
    (tmp_path / "campaign.json").write_text(json.dumps(payload), encoding="utf-8")

    stage = load_campaign_catalog(tmp_path).stages["test_stage"]

    assert stage.motes == (MoteSpec("test_stage:mote:1", 3, 4),)
    assert stage.checkpoints == (CheckpointSpec("test_stage.midway", 5, 6),)
    assert stage.interactions == (InteractionSpec("test.switch", "switch", 7, 3, 2, 3),)


@pytest.mark.parametrize(
    "mote_id",
    [
        "test_stage.mote.1",
        "other_stage:mote:1",
        "test_stage:mote:0",
        "test_stage:mote:-1",
        "test_stage:mote:",
        "test_stage:mote:one",
        "test_stage:mote:+1",
        "test_stage:mote:01",
    ],
)
def test_authored_mote_ids_must_use_the_canonical_stage_owned_positive_index(
    tmp_path: Path,
    mote_id: str,
) -> None:
    payload = _one_stage_campaign({"motes": [{"mote_id": mote_id, "tile_x": 3, "tile_y": 4}]})
    (tmp_path / "campaign.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContentError, match="must match test_stage:mote"):
        load_campaign_catalog(tmp_path)


def test_authored_mote_ids_must_be_unique_within_the_stage(tmp_path: Path) -> None:
    mote = {"mote_id": "test_stage:mote:1", "tile_x": 3, "tile_y": 4}
    payload = _one_stage_campaign({"motes": [mote, mote]})
    (tmp_path / "campaign.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContentError, match=r"motes\[1\]\.mote_id: duplicate value"):
        load_campaign_catalog(tmp_path)


@pytest.mark.parametrize(
    ("enemy_fields", "message"),
    [
        ({"ability_id": "sword"}, "ability_id"),
        ({"copy_ability": "unknown"}, "copy_ability: unknown field"),
    ],
)
def test_unknown_or_non_public_enemy_ability_ids_fail_closed(
    tmp_path: Path,
    enemy_fields: dict[str, str],
    message: str,
) -> None:
    enemy = {
        "x": 64,
        "y": 96,
        "kind": "wisp",
        "patrol_left": 32,
        "patrol_right": 128,
        **enemy_fields,
    }
    payload = _one_stage_campaign({"enemy_spawns": [enemy]})
    (tmp_path / "campaign.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContentError, match=message):
        load_campaign_catalog(tmp_path)


def test_snapshot_types_are_frozen_render_facing_contracts() -> None:
    assert tuple(field.name for field in fields(PlayerView)) == (
        "entity_id",
        "slot",
        "x",
        "y",
        "width",
        "height",
        "facing",
        "actor_state",
        "hp",
        "maximum_hp",
        "lives_remaining",
        "ability_id",
        "ability_meter",
        "ability_charge_ms",
        "guard_active",
        "dodge_active",
        "invulnerable",
        "hover_remaining_ms",
        "hover_max_ms",
        "captured_ability_id",
        "captured_visual_id",
    )
    assert tuple(field.name for field in fields(EnemyView)) == (
        "entity_id",
        "enemy_kind",
        "x",
        "y",
        "width",
        "height",
        "facing",
        "actor_state",
        "hp",
        "maximum_hp",
        "ability_id",
        "captured_by",
    )
    assert tuple(field.name for field in fields(AttackView)) == (
        "entity_id",
        "owner_entity_id",
        "attack_kind",
        "visual_id",
        "x",
        "y",
        "width",
        "height",
        "facing",
        "ttl_ms",
    )
    assert tuple(field.name for field in fields(EchoPickupView)) == (
        "entity_id",
        "ability_id",
        "x",
        "y",
    )
    assert tuple(field.name for field in fields(InteractionView)) == (
        "entity_id",
        "interaction_id",
        "interaction_kind",
        "interaction_state",
        "x",
        "y",
        "width",
        "height",
    )
    assert tuple(field.name for field in fields(CheckpointView)) == (
        "checkpoint_id",
        "x",
        "y",
        "is_active",
    )
    assert tuple(field.name for field in fields(GoalGatherView)) == (
        "goal_x",
        "goal_y",
        "at_goal_slots",
        "required_slots",
        "leader_slot",
        "leader_confirmed",
        "countdown_remaining_ms",
    )
    assert tuple(field.name for field in fields(CameraTargetView)) == (
        "entity_id",
        "slot",
        "x",
        "y",
        "weight",
        "enabled",
    )
    assert tuple(field.name for field in fields(StageSnapshot)) == (
        "frame_index",
        "elapsed_ms",
        "stage_id",
        "world_id",
        "node_id",
        "outcome",
        "players",
        "enemies",
        "attacks",
        "echo_pickups",
        "interactions",
        "checkpoints",
        "goal_gather",
        "camera_targets",
        "collected_mote_ids",
    )
    assert tuple(field.name for field in fields(StageResult)) == (
        "stage_id",
        "world_id",
        "node_id",
        "clear_time_ms",
        "collected_mote_ids",
        "discovered_ability_ids",
        "active_slots",
        "deaths_by_slot",
    )
    assert tuple(field.name for field in fields(StageFrame)) == ("simulation", "view", "events", "result")
    assert tuple(outcome.value for outcome in StageOutcome) == ("running", "completed", "failed")

    player = PlayerView(
        entity_id=1,
        slot=1,
        x=64.0,
        y=160.0,
        width=24,
        height=28,
        facing=1,
        actor_state="idle",
        hp=10,
        maximum_hp=10,
        lives_remaining=3,
        ability_id="none",
        ability_meter=0,
        ability_charge_ms=0,
        guard_active=False,
        dodge_active=False,
        invulnerable=False,
        hover_remaining_ms=850,
        hover_max_ms=850,
        captured_ability_id=None,
        captured_visual_id=None,
    )
    with pytest.raises(FrozenInstanceError):
        player.hp = 9  # type: ignore[misc]


def test_gameplay_helpers_build_real_stable_contract_values() -> None:
    player = make_active_player(2, leader=True)
    stage = make_stage(player_spawns=((32.0, 64.0),))

    assert (player.slot, player.is_leader) == (2, True)
    assert (player.device.uid, player.color_token, player.icon_token) == (
        "test-kb-2",
        "player-2",
        "sprig-2",
    )
    assert stage.player_spawns == ((32.0, 64.0),)
    assert stage.interactions == ()


def _one_stage_campaign(stage_overrides: dict[str, object]) -> dict[str, object]:
    stage: dict[str, object] = {
        "stage_id": "test_stage",
        "world_id": "test_world",
        "node_id": "test_node",
        "width_tiles": 10,
        "height_tiles": 8,
        "tile_size": 32,
        "ground_y_tile": 6,
        "player_spawns": [[32, 64]],
        "enemy_spawns": [],
        "motes": [{"mote_id": "test_stage:mote:1", "tile_x": 2, "tile_y": 3}],
        "checkpoints": [{"checkpoint_id": "test_stage.start", "tile_x": 1, "tile_y": 2}],
        "interactions": [],
        "goal_tile": [8, 5],
        "hazards": [],
        "one_way_tiles": [],
        "solids": [],
    }
    stage.update(stage_overrides)
    return {
        "worlds": [
            {
                "world_id": "test_world",
                "nodes": [
                    {
                        "node_id": "test_node",
                        "stage_id": "test_stage",
                        "requires": [],
                        "rewards": [],
                        "position": [0, 0],
                        "is_boss": False,
                    }
                ],
            }
        ],
        "stages": [stage],
    }
