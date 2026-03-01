from __future__ import annotations

from kirby_clone.gameplay.components import (
    AbilityState,
    ActorState,
    Collider,
    ControlIntent,
    EnemyDropAbility,
    Facing,
    Health,
    InhaleState,
    Team,
    Transform,
)
from kirby_clone.gameplay.state_machine import transition


class InhaleSystem:
    def update(self, world, dt_ms: int) -> None:
        enemy_rows = list(world.query(Team, Transform, Collider, Health, EnemyDropAbility))
        for player_id, team, transform, collider, intent, inhale, ability, state, facing in world.query(
            Team,
            Transform,
            Collider,
            ControlIntent,
            InhaleState,
            AbilityState,
            ActorState,
            Facing,
        ):
            if team.name != "player":
                continue
            if intent.inhale_pressed:
                inhale.active = True
                inhale.active_ms = 0
                inhale.captured_entity = None
                state.name = transition(state.name, "Inhale")

            if inhale.active:
                inhale.active_ms += dt_ms
                self._try_capture_enemy(player_id, transform, collider, inhale, facing.direction, enemy_rows)

            if intent.inhale_released and inhale.active:
                self._on_inhale_release(world, player_id, transform, ability, inhale, facing.direction, state)

    def _try_capture_enemy(
        self,
        player_id: int,
        player_transform: Transform,
        player_collider: Collider,
        inhale: InhaleState,
        facing: int,
        enemy_rows: list[tuple[int, Team, Transform, Collider, Health, EnemyDropAbility]],
    ) -> None:
        if inhale.captured_entity is not None:
            return
        inhale_range = 78.0 + min(80.0, inhale.active_ms * 0.2)
        for enemy_id, team, enemy_transform, _, enemy_health, _ in enemy_rows:
            if team.name != "enemy" or enemy_health.dead:
                continue
            dx = enemy_transform.x - player_transform.x
            dy = abs(enemy_transform.y - player_transform.y)
            if dy > player_collider.height + 10:
                continue
            if facing > 0 and not (0 <= dx <= inhale_range):
                continue
            if facing < 0 and not (-inhale_range <= dx <= 0):
                continue
            inhale.captured_entity = enemy_id
            # Pull captured enemy close to the mouth.
            enemy_transform.x = player_transform.x + (player_collider.width - 6) * facing
            enemy_transform.y = player_transform.y
            return

    def _on_inhale_release(
        self,
        world,
        player_id: int,
        player_transform: Transform,
        ability: AbilityState,
        inhale: InhaleState,
        facing: int,
        state: ActorState,
    ) -> None:
        if inhale.captured_entity is not None and inhale.captured_entity in world.alive_entities:
            captured = inhale.captured_entity
            drop = world.try_component(captured, EnemyDropAbility)
            if drop is not None:
                ability.previous = ability.current
                ability.current = drop.ability
                world.events.publish(
                    "ability_copied",
                    {"actor": player_id, "ability": ability.current},
                )
            world.destroy_entity(captured)
            state.name = transition(state.name, "Swallow")
        else:
            world.resources.setdefault("projectile_requests", []).append(
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

        inhale.active = False
        inhale.active_ms = 0
        inhale.captured_entity = None
