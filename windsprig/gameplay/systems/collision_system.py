from __future__ import annotations

from typing import cast

from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    NON_ENTITY_DAMAGE_SOURCE_ID,
    ActorState,
    CapturedBy,
    Collider,
    DamageRecord,
    Projectile,
    Transform,
    Velocity,
)
from windsprig.math2d import Rect, Vec2
from windsprig.physics import PhysicsBody, TileCollisionWorld, move_body


class CollisionSystem:
    def update(self, world: World, dt_ms: int) -> None:
        collision_world = cast(TileCollisionWorld, world.resources["collision_world"])
        dt_s = dt_ms / 1000.0
        for entity_id, transform, velocity, collider in world.query(Transform, Velocity, Collider):
            # WHY: Combat owns legacy projectile motion until Task 8 introduces AttackMotionSystem.
            if world.has_component(entity_id, Projectile):
                continue
            if world.has_component(entity_id, CapturedBy):
                velocity.vx = 0.0
                velocity.vy = 0.0
                continue
            body = PhysicsBody(
                rect=Rect(transform.x, transform.y, collider.width, collider.height),
                velocity=Vec2(velocity.vx, velocity.vy),
                on_ground=collider.on_ground,
            )
            result = move_body(body, collision_world, dt_s)
            transform.x = body.rect.x
            transform.y = body.rect.y
            velocity.vx = body.velocity.x
            velocity.vy = body.velocity.y
            collider.on_ground = result.hit_ground

            state = world.try_component(entity_id, ActorState)
            if state is not None and collider.on_ground and state.name in {"Fall", "Jump", "Hover"}:
                state.name = "Run" if abs(velocity.vx) > 40 else "Idle"

            if result.hit_hazard:
                cast(
                    list[DamageRecord],
                    world.resources.setdefault("damage_queue", []),
                ).append(
                    DamageRecord(
                        source_id=NON_ENTITY_DAMAGE_SOURCE_ID,
                        target_id=entity_id,
                        amount=1,
                        knockback_x=0.0,
                        knockback_y=-200.0,
                        guard_break=True,
                    )
                )
