from __future__ import annotations

from hypothesis import given, strategies as st

from kirby_clone.math2d import Rect, Vec2
from kirby_clone.physics import PhysicsBody, TileCollisionWorld, move_body


def test_horizontal_collision_stops_at_wall() -> None:
    world = TileCollisionWorld(
        tile_size=32,
        width_tiles=10,
        height_tiles=8,
        solid_tiles={(2, 2)},
    )
    body = PhysicsBody(rect=Rect(40, 64, 20, 20), velocity=Vec2(200, 0))
    result = move_body(body, world, dt_s=0.2)
    assert result.hit_right is True
    assert body.rect.right <= 64
    assert body.velocity.x == 0


def test_one_way_platform_lands_from_above() -> None:
    world = TileCollisionWorld(
        tile_size=32,
        width_tiles=10,
        height_tiles=8,
        solid_tiles=set(),
        one_way_tiles={(2, 3)},
    )
    body = PhysicsBody(rect=Rect(64, 70, 20, 20), velocity=Vec2(0, 80))
    result = move_body(body, world, dt_s=0.5)
    assert result.hit_ground is True
    assert body.rect.bottom == 96


def test_one_way_platform_allows_pass_from_below() -> None:
    world = TileCollisionWorld(
        tile_size=32,
        width_tiles=10,
        height_tiles=8,
        solid_tiles=set(),
        one_way_tiles={(2, 3)},
    )
    body = PhysicsBody(rect=Rect(64, 110, 20, 20), velocity=Vec2(0, -90))
    result = move_body(body, world, dt_s=0.5)
    assert result.hit_ceiling is False
    assert body.rect.y < 110


def test_hazard_collision_is_reported() -> None:
    world = TileCollisionWorld(
        tile_size=32,
        width_tiles=10,
        height_tiles=8,
        solid_tiles=set(),
        hazard_tiles={(1, 1)},
    )
    body = PhysicsBody(rect=Rect(40, 40, 20, 20), velocity=Vec2(0, 0))
    result = move_body(body, world, dt_s=0.016)
    assert result.hit_hazard is True


@given(
    start_x=st.floats(min_value=0, max_value=120, allow_nan=False, allow_infinity=False),
    vx=st.floats(min_value=-320, max_value=320, allow_nan=False, allow_infinity=False),
    vy=st.floats(min_value=-320, max_value=320, allow_nan=False, allow_infinity=False),
)
def test_body_does_not_end_inside_solid(start_x: float, vx: float, vy: float) -> None:
    world = TileCollisionWorld(
        tile_size=32,
        width_tiles=12,
        height_tiles=10,
        solid_tiles={(4, 4), (4, 5), (5, 5)},
    )
    body = PhysicsBody(rect=Rect(start_x, 60, 20, 20), velocity=Vec2(vx, vy))
    if world.touches_solid(body.rect):
        return
    move_body(body, world, dt_s=0.016)
    assert not world.touches_solid(body.rect)
