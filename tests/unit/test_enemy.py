from __future__ import annotations

from windsprig.combat import HitEvent
from windsprig.config import GameConfig
from windsprig.enemies import Enemy
from windsprig.entities import WorldState
from windsprig.math2d import Vec2
from windsprig.physics import TileCollisionWorld
from windsprig.player import Player


def _world(player: Player, enemy: Enemy) -> WorldState:
    collision = TileCollisionWorld(
        tile_size=32,
        width_tiles=30,
        height_tiles=14,
        solid_tiles={(x, 12) for x in range(30)},
    )
    return WorldState(
        collision_map=collision,
        entity_index={player.entity_id: player, enemy.entity_id: enemy},
        rng_seed=1,
        frame_index=0,
        player_id=player.entity_id,
    )


def test_enemy_switches_to_chase_when_player_near() -> None:
    player = Player(GameConfig(), spawn=(100, 200))
    enemy = Enemy(kind="grunt", spawn=(140, 200), patrol_left=0, patrol_right=400)
    world = _world(player, enemy)
    enemy.update(16, world)
    assert enemy.state == "chase"


def test_enemy_patrol_when_player_far() -> None:
    player = Player(GameConfig(), spawn=(500, 200))
    enemy = Enemy(kind="grunt", spawn=(140, 200), patrol_left=0, patrol_right=300)
    world = _world(player, enemy)
    enemy.update(16, world)
    assert enemy.state == "patrol"


def test_enemy_dies_after_enough_damage() -> None:
    enemy = Enemy(kind="grunt", spawn=(140, 200), patrol_left=0, patrol_right=300)
    hit = HitEvent(attacker_id=1, target_id=enemy.entity_id, damage=2, knockback=Vec2(0, -100), frame_index=0)
    enemy.on_hit(hit)
    assert enemy.dead is True
