from __future__ import annotations

from typing import cast

from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    Collider,
    ControlIntent,
    DrawState,
    EnemyDropAbility,
    Facing,
    Health,
    Team,
    Transform,
)
from windsprig.gameplay.state_machine import transition


class DrawSystem:
    def update(self, world: World, dt_ms: int) -> None:
        enemy_rows = list(world.query(Team, Transform, Collider, Health, EnemyDropAbility))
        for player_id, team, transform, collider, intent, draw_state, ability, state, facing in world.query(
            Team,
            Transform,
            Collider,
            ControlIntent,
            DrawState,
            AbilityState,
            ActorState,
            Facing,
        ):
            if team.name != "player":
                continue
            if intent.draw_pressed:
                draw_state.active = True
                draw_state.active_ms = 0
                draw_state.captured_entity = None
                state.name = transition(state.name, "Draw")

            if draw_state.active:
                draw_state.active_ms += dt_ms
                self._try_capture_enemy(player_id, transform, collider, draw_state, facing.direction, enemy_rows)

            if intent.draw_released and draw_state.active:
                self._on_draw_release(world, player_id, transform, ability, draw_state, facing.direction, state)

    def _try_capture_enemy(
        self,
        player_id: int,
        player_transform: Transform,
        player_collider: Collider,
        draw_state: DrawState,
        facing: int,
        enemy_rows: list[tuple[int, Team, Transform, Collider, Health, EnemyDropAbility]],
    ) -> None:
        if draw_state.captured_entity is not None:
            return
        draw_range = 78.0 + min(80.0, draw_state.active_ms * 0.2)
        for enemy_id, team, enemy_transform, _, enemy_health, _ in enemy_rows:
            if team.name != "enemy" or enemy_health.dead:
                continue
            dx = enemy_transform.x - player_transform.x
            dy = abs(enemy_transform.y - player_transform.y)
            if dy > player_collider.height + 10:
                continue
            if facing > 0 and not (0 <= dx <= draw_range):
                continue
            if facing < 0 and not (-draw_range <= dx <= 0):
                continue
            draw_state.captured_entity = enemy_id
            # Pull the captured echo close to the player.
            enemy_transform.x = player_transform.x + (player_collider.width - 6) * facing
            enemy_transform.y = player_transform.y
            return

    def _on_draw_release(
        self,
        world: World,
        player_id: int,
        player_transform: Transform,
        ability: AbilityState,
        draw_state: DrawState,
        facing: int,
        state: ActorState,
    ) -> None:
        if draw_state.captured_entity is not None and draw_state.captured_entity in world.alive_entities:
            captured = draw_state.captured_entity
            drop = world.try_component(captured, EnemyDropAbility)
            if drop is not None:
                ability.previous = ability.current
                ability.current = drop.ability
                world.events.publish(
                    "ability_copied",
                    {"actor": player_id, "ability": ability.current},
                )
            world.destroy_entity(captured)
            state.name = transition(state.name, "Harmonize")
        else:
            projectile_requests = cast(
                list[dict[str, object]],
                world.resources.setdefault("projectile_requests", []),
            )
            projectile_requests.append(
                {
                    "owner": player_id,
                    "team": "player",
                    "tag": "spit_star",
                    "x": player_transform.x + 10,
                    "y": player_transform.y + 8,
                    "vx": 360.0 * facing,
                    "vy": -20.0,
                    "damage": 2,
                    "ttl_ms": 300,
                    "width": 20,
                    "height": 16,
                }
            )
            state.name = transition(state.name, "Attack")

        draw_state.active = False
        draw_state.active_ms = 0
        draw_state.captured_entity = None
