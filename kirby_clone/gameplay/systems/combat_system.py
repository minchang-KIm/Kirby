from __future__ import annotations

from kirby_clone.gameplay.components import Collider, EnemyAI, Health, Projectile, Team, Transform, Velocity
from kirby_clone.math2d import Rect


class CombatSystem:
    def update(self, world, dt_ms: int) -> None:
        dt_s = dt_ms / 1000.0
        damage_queue: list[dict[str, object]] = world.resources.setdefault("damage_queue", [])
        to_destroy: set[int] = set()

        targets = list(world.query(Team, Transform, Collider, Health))

        for projectile_id, projectile, team, transform, collider, velocity in world.query(
            Projectile, Team, Transform, Collider, Velocity
        ):
            transform.x += velocity.vx * dt_s
            transform.y += velocity.vy * dt_s
            projectile.ttl_ms -= dt_ms
            if projectile.ttl_ms <= 0:
                to_destroy.add(projectile_id)
                continue

            projectile_rect = Rect(transform.x, transform.y, collider.width, collider.height)
            for target_id, target_team, target_tf, target_col, target_hp in targets:
                if target_id == projectile.owner or target_hp.dead:
                    continue
                if target_team.name == team.name:
                    continue
                target_rect = Rect(target_tf.x, target_tf.y, target_col.width, target_col.height)
                if not projectile_rect.intersects(target_rect):
                    continue
                damage_queue.append(
                    {
                        "target": target_id,
                        "amount": projectile.damage,
                        "knockback_x": velocity.vx * 0.5,
                        "knockback_y": min(-120.0, velocity.vy * 0.5),
                    }
                )
                to_destroy.add(projectile_id)
                break

        # Enemy body contact damage.
        players = [row for row in targets if row[1].name == "player"]
        enemies = [
            row + (world.try_component(row[0], EnemyAI),)
            for row in targets
            if row[1].name == "enemy" and row[3].solid
        ]
        for player_id, _, ptf, pcol, php in players:
            if php.dead:
                continue
            prect = Rect(ptf.x, ptf.y, pcol.width, pcol.height)
            for enemy_id, _, etf, ecol, ehp, ai in enemies:
                if ehp.dead or ai is None:
                    continue
                erect = Rect(etf.x, etf.y, ecol.width, ecol.height)
                if prect.intersects(erect):
                    damage_queue.append(
                        {
                            "target": player_id,
                            "amount": 2 if ai.kind == "boss" else 1,
                            "knockback_x": 180.0 if etf.x <= ptf.x else -180.0,
                            "knockback_y": -120.0,
                        }
                    )

        for entity_id in to_destroy:
            world.destroy_entity(entity_id)
