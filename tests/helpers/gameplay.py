"""Deterministic builders for production gameplay tests."""

from __future__ import annotations

from windsprig.content.loader import CheckpointSpec, EnemySpawn, MoteSpec, StageSpec
from windsprig.input.roster import ActivePlayer, DeviceRef


def make_active_player(slot: int, leader: bool = False) -> ActivePlayer:
    """Build a stable keyboard-backed player identity for ``slot``."""
    return ActivePlayer(
        slot=slot,
        device=DeviceRef(
            kind="keyboard",
            uid=f"test-kb-{slot}",
            label=f"Test Keyboard {slot}",
        ),
        color_token=f"player-{slot}",
        icon_token=f"sprig-{slot}",
        is_leader=leader,
    )


def make_stage(
    *,
    player_spawns: tuple[tuple[float, float], ...] = ((64.0, 160.0),),
    enemy_spawns: tuple[EnemySpawn, ...] = (),
    motes: tuple[MoteSpec, ...] = (),
    checkpoints: tuple[CheckpointSpec, ...] = (),
) -> StageSpec:
    """Build a compact flat stage without coupling tests to campaign content."""
    return StageSpec(
        stage_id="test_stage",
        world_id="test_world",
        node_id="test_node",
        width_tiles=20,
        height_tiles=10,
        tile_size=32,
        ground_y_tile=8,
        player_spawns=player_spawns,
        enemy_spawns=enemy_spawns,
        motes=motes,
        checkpoints=checkpoints,
        interactions=(),
        goal_tile=(18, 7),
        hazards=(),
        one_way_tiles=(),
        solids=tuple((tile_x, 8) for tile_x in range(20)),
    )
