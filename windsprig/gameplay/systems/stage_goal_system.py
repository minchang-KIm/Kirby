from __future__ import annotations

from windsprig.core.ecs import World
from windsprig.gameplay.components import Collider, Health, StageGoal, Team, Transform
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.math2d import Rect

# Temporary compatibility topic until Task 9 publishes the final typed outcome events.
PROVISIONAL_STAGE_CLEARED_TOPIC = "stage_cleared"


class StageGoalSystem:
    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        outcome = world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        if outcome is not StageOutcome.RUNNING:
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
                    world.resources["stage_outcome"] = StageOutcome.COMPLETED
                    world.events.publish(
                        PROVISIONAL_STAGE_CLEARED_TOPIC,
                        {"node_id": goal.node_id, "world_id": goal.world_id, "stage_id": goal.stage_id},
                    )
                    return
