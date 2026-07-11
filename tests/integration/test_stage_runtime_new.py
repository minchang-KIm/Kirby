from __future__ import annotations

from pathlib import Path

from windsprig.config import GameConfig
from windsprig.content.loader import load_campaign_catalog
from windsprig.core.rng import derive_stage_seed
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.components import ControlIntent, PlayerSlot, Transform
from windsprig.gameplay.runtime import StageRuntime
from windsprig.input.commands import InputFrame, MoveCommand
from windsprig.input.roster import ActivePlayer, ActiveRoster, DeviceRef


def joined_players(count: int) -> tuple[ActivePlayer, ...]:
    roster = ActiveRoster()
    devices = (
        DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"),
        DeviceRef("keyboard", "keyboard-arrows", "Keyboard Arrows"),
    )
    for device in devices[:count]:
        roster.join(device)
    return roster.players


def test_stage_runtime_deterministic_snapshot() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]
    registry = create_default_registry(Path("windsprig/content"))
    players = joined_players(1)
    runtime_a = StageRuntime(
        config,
        stage,
        registry,
        active_players=players,
        seed=derive_stage_seed(config.replay_seed, stage.stage_id),
    )
    runtime_b = StageRuntime(
        config,
        stage,
        registry,
        active_players=players,
        seed=derive_stage_seed(config.replay_seed, stage.stage_id),
    )

    for _ in range(20):
        runtime_a.step(InputFrame.empty())
        runtime_b.step(InputFrame.empty())

    assert runtime_a.world.world_hash() == runtime_b.world.world_hash()
    assert runtime_a.world.rng.seed == 17674047013880078487


def test_runtime_spawns_one_player_without_inactive_hud_camera_lives_or_input() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]
    registry = create_default_registry(Path("windsprig/content"))
    runtime = StageRuntime(config, stage, registry, active_players=joined_players(1), seed=11)

    runtime.step(InputFrame(commands_by_slot={2: [MoveCommand(player_slot=2, axis=1)]}))

    player_rows = list(runtime.world.query(PlayerSlot, Transform, ControlIntent))
    assert len(runtime.player_entities) == 1
    assert [(slot.slot, slot.lives) for _, slot, _, _ in player_rows] == [(1, 3)]
    assert player_rows[0][3].move_axis == 0
    assert runtime.world.resources["hud"]["players"] == [
        {"slot": 1, "hp": 10, "max_hp": 10, "lives": 3, "ability": "none"}
    ]
    transform = player_rows[0][2]
    assert runtime.world.resources["camera_target"] == (transform.x, transform.y)
    assert runtime.world.resources["stage_cleared"] is False


def test_runtime_spawns_exactly_two_joined_slots() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]
    registry = create_default_registry(Path("windsprig/content"))

    runtime = StageRuntime(config, stage, registry, active_players=joined_players(2), seed=12)

    assert len(runtime.player_entities) == 2
    assert sorted(slot.slot for _, slot in runtime.world.query(PlayerSlot)) == [1, 2]
