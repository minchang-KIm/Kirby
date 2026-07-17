from __future__ import annotations

from pathlib import Path

import pytest

from windsprig.config import GameConfig
from windsprig.content.loader import load_campaign_catalog
from windsprig.core.events import GameEvent
from windsprig.core.rng import derive_stage_seed
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.components import ControlIntent, PlayerSlot, Transform
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.session import GameSession, SessionAction
from windsprig.gameplay.snapshot import StageOutcome
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

    frame = runtime.step(InputFrame(commands_by_slot={2: [MoveCommand(player_slot=2, axis=1)]}))

    player_rows = list(runtime.world.query(PlayerSlot, Transform, ControlIntent))
    assert runtime.player_entities == {1: 1}
    assert [(slot.slot, slot.lives) for _, slot, _, _ in player_rows] == [(1, 3)]
    assert player_rows[0][3].move_axis == 0
    assert [(player.slot, player.hp, player.maximum_hp) for player in frame.view.players] == [
        (1, 10, 10)
    ]
    assert "hud" not in runtime.world.resources
    transform = player_rows[0][2]
    assert [(target.x, target.y) for target in frame.view.camera_targets] == [
        (transform.x, transform.y)
    ]
    assert runtime.world.resources["stage_outcome"] is StageOutcome.RUNNING
    assert "stage_cleared" not in runtime.world.resources


def test_runtime_spawns_exactly_two_joined_slots() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]
    registry = create_default_registry(Path("windsprig/content"))

    runtime = StageRuntime(config, stage, registry, active_players=joined_players(2), seed=12)

    assert tuple(runtime.player_entities) == (1, 2)
    assert sorted(slot.slot for _, slot in runtime.world.query(PlayerSlot)) == [1, 2]


def test_playing_roster_changes_wait_for_the_pause_lobby() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(config.content_dir)
    stage = catalog.stages["world_1_stage_1"]
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    session = GameSession.create(
        config,
        stage,
        create_default_registry(config.content_dir),
        roster.players,
        seed=12,
    )
    session.dispatch(SessionAction.START)
    recorded_events: list[GameEvent] = []
    session.runtime.world.events.subscribe("*", recorded_events.append)
    roster.join(DeviceRef("keyboard", "keyboard-arrows", "Keyboard Arrows"))
    before_hash = session.runtime.world.world_hash()

    with pytest.raises(ValueError, match="roster"):
        session.sync_active_players(roster.players)

    assert session.runtime.player_entities == {1: 1}
    assert session.runtime.world.world_hash() == before_hash
    assert recorded_events == []

    session.dispatch(SessionAction.PAUSE)
    joined = session.sync_active_players(roster.players)
    assert [event.topic for event in joined] == ["PlayerJoined"]
    joined_entity = session.runtime.player_entities[2]
    session.dispatch(SessionAction.RESUME)
    roster.leave(1)
    before_disconnect = session.runtime.world.world_hash()
    recorded_events.clear()

    with pytest.raises(ValueError, match="roster"):
        session.sync_active_players(roster.players)

    assert session.runtime.player_entities == {1: 1, 2: joined_entity}
    assert session.runtime.world.world_hash() == before_disconnect
    assert recorded_events == []

    session.dispatch(SessionAction.PAUSE)
    left = session.sync_active_players(roster.players)
    assert [event.topic for event in left] == ["PlayerLeft"]
    assert session.runtime.player_entities == {2: joined_entity}
    assert session.runtime.world.get_component(joined_entity, PlayerSlot).is_leader is True
