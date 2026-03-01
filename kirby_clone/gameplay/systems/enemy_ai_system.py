from __future__ import annotations

from kirby_clone.gameplay.components import EnemyAI, Health, PlayerSlot, Transform, Velocity


class EnemyAISystem:
    def update(self, world, dt_ms: int) -> None:
        _ = dt_ms
        players: list[tuple[int, Transform]] = []
        for player_id, _, transform, health in world.query(PlayerSlot, Transform, Health):
            if not health.dead:
                players.append((player_id, transform))

        for entity_id, ai, transform, velocity, health in world.query(EnemyAI, Transform, Velocity, Health):
            if health.dead:
                velocity.vx = 0.0
                continue

            target_dx = None
            if players:
                nearest = min(players, key=lambda item: abs(item[1].x - transform.x))
                dx = nearest[1].x - transform.x
                if abs(dx) <= ai.aggro_range:
                    target_dx = dx

            if target_dx is not None:
                ai.facing = 1 if target_dx >= 0 else -1
                speed = 140.0 if ai.kind == "grunt" else 90.0
                if ai.kind == "boss":
                    speed = 120.0
                velocity.vx = speed * ai.facing
            else:
                if transform.x <= ai.patrol_left:
                    ai.facing = 1
                elif transform.x >= ai.patrol_right:
                    ai.facing = -1
                patrol_speed = 88.0 if ai.kind != "boss" else 70.0
                velocity.vx = patrol_speed * ai.facing
