from __future__ import annotations

from kirby_clone.entities import WorldState
from kirby_clone.input import InputState
from kirby_clone.math2d import Vec2
from kirby_clone.physics import TileCollisionWorld
from kirby_clone.player import Player
from kirby_clone.settings import GameConfig


def _world() -> WorldState:
    collision = TileCollisionWorld(
        tile_size=32,
        width_tiles=20,
        height_tiles=12,
        solid_tiles={(x, 10) for x in range(20)},
    )
    return WorldState(collision_map=collision, entity_index={}, rng_seed=1337, frame_index=0, player_id=1)


def test_jump_buffer_triggers_jump_when_grounded() -> None:
    config = GameConfig()
    player = Player(config=config, spawn=(40, 200))
    world = _world()
    world.entity_index[player.entity_id] = player

    player.body.on_ground = True
    player._jump_buffer_ms = config.jump_buffer_ms  # test-only reach into timer state
    player.set_input(InputState(jump_held=True))
    player.update(config.fixed_dt_ms, world)

    assert player.body.velocity.y < 0
    assert player.state in {"jump", "fall"}


def test_coyote_time_allows_late_jump() -> None:
    config = GameConfig()
    player = Player(config=config, spawn=(40, 200))
    world = _world()
    world.entity_index[player.entity_id] = player

    player.body.on_ground = False
    player._coyote_ms = 80  # test-only reach into timer state
    player._jump_buffer_ms = 80
    player.set_input(InputState(jump_held=True))
    player.update(config.fixed_dt_ms, world)
    assert player.body.velocity.y < -100


def test_on_hit_applies_invulnerability() -> None:
    config = GameConfig()
    player = Player(config=config, spawn=(40, 200))
    player.on_hit(type("Hit", (), {"damage": 1, "knockback": Vec2(100, -100)})())  # lightweight stub
    hp_after_first = player.hp
    player.on_hit(type("Hit", (), {"damage": 1, "knockback": Vec2(100, -100)})())
    assert player.hp == hp_after_first
