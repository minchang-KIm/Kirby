"""Translate ability intent into deterministic projectile entities and events."""

from __future__ import annotations

from typing import Any, cast

from windsprig.core.ecs import World
from windsprig.gameplay.abilities import AbilityRegistry
from windsprig.gameplay.components import (
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
from windsprig.gameplay.state_machine import transition


class AbilitySystem:
    """Own legacy ability cooldowns, attacks, and projectile materialization."""

    def update(self, world: World, dt_ms: int) -> None:
        registry = cast(AbilityRegistry, world.resources["ability_registry"])
        requests = cast(
            list[dict[str, Any]],
            world.resources.setdefault("projectile_requests", []),
        )

        for entity_id, team, transform, facing, intent, ability, state in world.query(
            Team, Transform, Facing, ControlIntent, AbilityState, ActorState
        ):
            if team.name != "player":
                continue
            ability.cooldown_remaining_ms = max(0, ability.cooldown_remaining_ms - dt_ms)

            if (
                intent.ability_pressed
                and not intent.ability_consumed
                and ability.cooldown_remaining_ms <= 0
            ):
                strategy = registry.get(ability.current_id)
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
                ability.cooldown_remaining_ms = getattr(strategy, "cooldown_ms", 260)
                state.name = transition(state.name, "Attack")
                world.events.publish(
                    "ability_used",
                    {"actor": entity_id, "ability": ability.current_id},
                )

        while requests:
            req = requests.pop(0)
            projectile_id = world.create_entity()
            world.add_component(projectile_id, Transform(float(req["x"]), float(req["y"])))
            world.add_component(projectile_id, Velocity(float(req["vx"]), float(req["vy"])))
            world.add_component(
                projectile_id,
                Collider(int(req["width"]), int(req["height"]), on_ground=False, solid=False),
            )
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
