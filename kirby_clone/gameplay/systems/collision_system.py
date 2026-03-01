from __future__ import annotations

from kirby_clone.gameplay.components import ActorState, Collider, Transform, Velocity
from kirby_clone.math2d import Rect, Vec2
from kirby_clone.physics import PhysicsBody, move_body


class CollisionSystem:
    def update(self, world, dt_ms: int) -> None:
        collision_world = world.resources["collision_world"]
        dt_s = dt_ms / 1000.0
        for entity_id, transform, velocity, collider in world.query(Transform, Velocity, Collider):
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
            if state is not None and collider.on_ground and state.name in {"Fall", "Jump", "Float"}:
                state.name = "Run" if abs(velocity.vx) > 40 else "Idle"

            if result.hit_hazard:
                world.resources.setdefault("damage_queue", []).append(
                    {"target": entity_id, "amount": 1, "knockback_x": 0.0, "knockback_y": -200.0}
                )
