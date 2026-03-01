from __future__ import annotations

from kirby_clone.gameplay.components import Collider, Health, StageGoal, Team, Transform
from kirby_clone.math2d import Rect


class StageGoalSystem:
    def update(self, world, dt_ms: int) -> None:
        _ = dt_ms
        if world.resources.get("stage_cleared", False):
            return
        players = [
            row
            for row in world.query(Team, Transform, Collider, Health)
            if row[1].name == "player" and not row[4].dead
        ]
        for _, goal, gtf, gcol in world.query(StageGoal, Transform, Collider):
            goal_rect = Rect(gtf.x, gtf.y, gcol.width, gcol.height)
            for _, _, ptf, pcol, _ in players:
                player_rect = Rect(ptf.x, ptf.y, pcol.width, pcol.height)
                if goal_rect.intersects(player_rect):
                    world.resources["stage_cleared"] = True
                    world.events.publish(
                        "stage_cleared",
                        {"node_id": goal.node_id, "world_id": goal.world_id, "stage_id": goal.stage_id},
                    )
                    return
