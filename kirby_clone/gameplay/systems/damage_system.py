from __future__ import annotations

from kirby_clone.gameplay.components import ActorState, Health, PlayerSlot, Respawn, Velocity
from kirby_clone.gameplay.state_machine import transition
from kirby_clone.settings import GameConfig


class DamageSystem:
    def update(self, world, dt_ms: int) -> None:
        config: GameConfig = world.resources["config"]
        for _, health in world.query(Health):
            health.invulnerable_ms = max(0, health.invulnerable_ms - dt_ms)

        queue: list[dict[str, object]] = world.resources.setdefault("damage_queue", [])
        while queue:
            item = queue.pop(0)
            target_id = int(item["target"])
            health = world.try_component(target_id, Health)
            if health is None or health.dead:
                continue
            if health.invulnerable_ms > 0:
                continue

            amount = int(item["amount"])
            health.current -= amount
            health.invulnerable_ms = config.invulnerable_ms
            velocity = world.try_component(target_id, Velocity)
            if velocity is not None:
                velocity.vx += float(item.get("knockback_x", 0.0))
                velocity.vy = min(velocity.vy + float(item.get("knockback_y", -80.0)), -80.0)

            if health.current <= 0:
                health.current = 0
                health.dead = True
                state = world.try_component(target_id, ActorState)
                if state is not None:
                    state.name = transition(state.name, "Dead")
                if world.has_component(target_id, PlayerSlot):
                    respawn = world.try_component(target_id, Respawn)
                    if respawn is not None:
                        respawn.timer_ms = 1800
                world.events.publish("actor_dead", {"entity_id": target_id})
            else:
                state = world.try_component(target_id, ActorState)
                if state is not None:
                    state.name = transition(state.name, "Hurt")
