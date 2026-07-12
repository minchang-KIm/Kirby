from __future__ import annotations

from typing import cast

from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    NON_ENTITY_DAMAGE_SOURCE_ID,
    ActorState,
    Collider,
    DamageRecord,
    Health,
    PlayerSlot,
    Respawn,
    Transform,
    Velocity,
)


class CoopRespawnSystem:
    def update(self, world: World, dt_ms: int) -> None:
        stage = cast(StageSpec, world.resources["stage_spec"])
        stage_height = stage.pixel_height
        alive_positions: list[tuple[float, float]] = []

        for entity_id, _, transform, health in world.query(PlayerSlot, Transform, Health):
            if not health.dead:
                alive_positions.append((transform.x, transform.y))
            elif transform.y > stage_height + 120:
                cast(
                    list[DamageRecord],
                    world.resources.setdefault("damage_queue", []),
                ).append(
                    DamageRecord(
                        source_id=NON_ENTITY_DAMAGE_SOURCE_ID,
                        target_id=entity_id,
                        amount=health.maximum,
                        knockback_x=0.0,
                        knockback_y=-220.0,
                        guard_break=True,
                    )
                )

        anchor = alive_positions[0] if alive_positions else None

        for entity_id, slot, respawn, transform, velocity, collider, health, state in world.query(
            PlayerSlot, Respawn, Transform, Velocity, Collider, Health, ActorState
        ):
            if not health.dead:
                continue
            respawn.timer_ms = max(0, respawn.timer_ms - dt_ms)
            if respawn.timer_ms > 0:
                continue
            if slot.lives <= 0:
                continue
            slot.lives -= 1
            health.dead = False
            health.current = max(1, health.maximum // 2)
            health.invulnerable_ms = 1200
            if anchor is None:
                transform.x = respawn.x
                transform.y = respawn.y
            else:
                transform.x = anchor[0] + 18 * (slot.slot - 1)
                transform.y = anchor[1] - 28
            velocity.vx = 0.0
            velocity.vy = -100.0
            collider.on_ground = False
            state.name = "Idle"
            world.events.publish("player_respawned", {"slot": slot.slot, "entity_id": entity_id})
