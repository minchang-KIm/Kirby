"""Advance canonical attacks exactly once per fixed step."""

from __future__ import annotations

import math

from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.components import Attack, Collider, Transform, Velocity

GALEHOOK_RETURN_FRAME_OFFSET = 23


class AttackMotionSystem:
    """Own all canonical attack movement, return motion, bounds, and TTL."""

    def update(self, world: World, dt_ms: int) -> None:
        stage = world.resources.get("stage_spec")
        if not isinstance(stage, StageSpec):
            raise TypeError("stage_spec must be a StageSpec for attack motion")
        dt_seconds = dt_ms / 1000.0
        expired: list[int] = []
        for entity_id, attack, transform, velocity, collider in world.query(
            Attack,
            Transform,
            Velocity,
            Collider,
        ):
            if attack.last_advanced_frame == world.frame_index:
                raise AssertionError(f"attack {entity_id} advanced twice in frame {world.frame_index}")
            if attack.last_advanced_frame > world.frame_index:
                raise AssertionError(f"attack {entity_id} advanced beyond frame {world.frame_index}")
            _update_galehook_return(world, attack, transform, velocity)
            transform.x += velocity.vx * dt_seconds
            transform.y += velocity.vy * dt_seconds
            attack.ttl_ms = max(0, attack.ttl_ms - dt_ms)
            attack.last_advanced_frame = world.frame_index
            if attack.ttl_ms == 0 or _outside_stage(stage, transform, collider):
                expired.append(entity_id)
        for entity_id in expired:
            world.destroy_entity(entity_id)


def _update_galehook_return(
    world: World,
    attack: Attack,
    transform: Transform,
    velocity: Velocity,
) -> None:
    if attack.attack_kind != "boomerang":
        return
    return_frame = attack.born_frame + GALEHOOK_RETURN_FRAME_OFFSET
    if world.frame_index < return_frame:
        return
    speed = math.hypot(velocity.vx, velocity.vy)
    owner = world.try_component(attack.owner_entity_id, Transform)
    if owner is not None and speed > 0.0:
        dx = owner.x - transform.x
        dy = owner.y - transform.y
        distance = math.hypot(dx, dy)
        if distance > 0.0:
            velocity.vx = dx / distance * speed
            velocity.vy = dy / distance * speed
        else:
            velocity.vx = 0.0
            velocity.vy = 0.0
    elif attack.last_advanced_frame < return_frame:
        velocity.vx = -velocity.vx
        velocity.vy = -velocity.vy


def _outside_stage(stage: StageSpec, transform: Transform, collider: Collider) -> bool:
    return (
        transform.x + collider.width <= 0.0
        or transform.x >= stage.pixel_width
        or transform.y + collider.height <= 0.0
        or transform.y >= stage.pixel_height
    )


__all__ = ["AttackMotionSystem"]
