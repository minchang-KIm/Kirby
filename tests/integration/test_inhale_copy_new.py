from __future__ import annotations

from pathlib import Path

from kirby_clone.content.loader import load_campaign_catalog
from kirby_clone.gameplay.abilities import create_default_registry
from kirby_clone.gameplay.components import AbilityState, PlayerSlot, Transform
from kirby_clone.gameplay.runtime import StageRuntime
from kirby_clone.input.commands import InhaleReleaseCommand, InhaleStartCommand, InputFrame
from kirby_clone.settings import GameConfig


def test_inhale_swallow_grants_copy_ability() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("kirby_clone/content"))
    stage = catalog.stages["world_1_stage_1"]
    runtime = StageRuntime(config, stage, create_default_registry(Path("kirby_clone/content")), seed=11)

    # Spawn a guaranteed copy source right in front of P1.
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

    start_frame = InputFrame(commands_by_slot={1: [InhaleStartCommand(player_slot=1)]})
    runtime.step(start_frame)
    release_frame = InputFrame(commands_by_slot={1: [InhaleReleaseCommand(player_slot=1)]})
    runtime.step(release_frame)

    ability = runtime.world.get_component(p1, AbilityState)
    assert ability.current == "fire"
