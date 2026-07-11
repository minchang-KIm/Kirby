from __future__ import annotations

from pathlib import Path

from windsprig.config import GameConfig
from windsprig.content.loader import load_campaign_catalog
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.components import AbilityState, PlayerSlot, Transform
from windsprig.gameplay.runtime import StageRuntime
from windsprig.input.commands import DrawReleaseCommand, DrawStartCommand, InputFrame
from windsprig.input.roster import ActiveRoster, DeviceRef


def test_draw_harmonize_grants_echo_ability() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    runtime = StageRuntime(
        config,
        stage,
        create_default_registry(Path("windsprig/content")),
        active_players=roster.players,
        seed=11,
    )

    # Spawn a guaranteed echo source right in front of P1.
    p1 = next(entity_id for entity_id, slot in runtime.world.query(PlayerSlot) if slot.slot == 1)
    p1_tf = runtime.world.get_component(p1, Transform)
    runtime.factory.spawn_enemy(
        x=p1_tf.x + 16,
        y=p1_tf.y,
        kind="grunt",
        ability="fire",
        patrol_left=p1_tf.x - 40,
        patrol_right=p1_tf.x + 40,
    )

    start_frame = InputFrame(commands_by_slot={1: [DrawStartCommand(player_slot=1)]})
    runtime.step(start_frame)
    release_frame = InputFrame(commands_by_slot={1: [DrawReleaseCommand(player_slot=1)]})
    runtime.step(release_frame)

    ability = runtime.world.get_component(p1, AbilityState)
    assert ability.current == "fire"
