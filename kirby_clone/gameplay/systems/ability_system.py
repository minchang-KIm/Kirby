from __future__ import annotations

from kirby_clone.gameplay.components import (
    AbilityState,
    ActorState,
    Collider,
    ControlIntent,
    Facing,
    Projectile,
    Team,
    Transform,
    Velocity,
)
from kirby_clone.gameplay.state_machine import transition


class AbilitySystem:
    def update(self, world, dt_ms: int) -> None:
        registry = world.resources["ability_registry"]
        requests = world.resources.setdefault("projectile_requests", [])

        for entity_id, team, transform, facing, intent, ability, state in world.query(
            Team, Transform, Facing, ControlIntent, AbilityState, ActorState
        ):
            if team.name != "player":
                continue
            ability.cooldown_ms = max(0, ability.cooldown_ms - dt_ms)

            if intent.drop_pressed and ability.current != "none":
                ability.previous = ability.current
                ability.current = "none"
                ability.is_super = False
                world.events.publish("ability_dropped", {"actor": entity_id})

            if intent.ability_pressed and ability.cooldown_ms <= 0:
                strategy = registry.get(ability.current)
                for shape in strategy.get_attack_shapes(entity_id, world.frame_index):
                    requests.append(
                        {
                            "owner": entity_id,
                            "team": "player",
                            "tag": shape.tag,
                            "x": transform.x + (shape.dx if facing.direction > 0 else -shape.dx),
                            "y": transform.y + shape.dy,
                            "vx": shape.knockback_x if facing.direction > 0 else -shape.knockback_x,
                            "vy": shape.knockback_y,
                            "damage": shape.damage,
                            "ttl_ms": shape.ttl_ms,
                            "width": shape.width,
                            "height": shape.height,
                        }
                    )
                ability.cooldown_ms = getattr(strategy, "cooldown_ms", 260)
                ability.is_super = bool(getattr(strategy, "is_super", False))
                state.name = transition(state.name, "Attack")
                world.events.publish("ability_used", {"actor": entity_id, "ability": ability.current})

        while requests:
            req = requests.pop(0)
            projectile_id = world.create_entity()
            world.add_component(projectile_id, Transform(float(req["x"]), float(req["y"])))
            world.add_component(projectile_id, Velocity(float(req["vx"]), float(req["vy"])))
            world.add_component(projectile_id, Collider(int(req["width"]), int(req["height"]), on_ground=False, solid=False))
            world.add_component(
                projectile_id,
                Projectile(
                    owner=int(req["owner"]),
                    tag=str(req["tag"]),
                    damage=int(req["damage"]),
                    ttl_ms=int(req["ttl_ms"]),
                ),
            )
            world.add_component(projectile_id, Team(str(req["team"])))
