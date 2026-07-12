"""Complete a catalog stage only when every required living player is ready."""

from __future__ import annotations

from typing import cast

from windsprig.content.models import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.bosses import BossState
from windsprig.gameplay.components import Collider, Health, PlayerSlot, StageGoal, Transform
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.validation import build_stage_result
from windsprig.input.roster import ActivePlayer
from windsprig.math2d import Rect


class StageGoalSystem:
    """Own the one-shot goal gate and its immutable raw completion facts."""

    def update(self, world: World, dt_ms: int) -> None:
        outcome = world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        if outcome is not StageOutcome.RUNNING:
            return
        stage = world.resources.get("stage_spec")
        if not isinstance(stage, StageSpec):
            raise TypeError("stage_spec must be a StageSpec")
        if not self._boss_gate_is_open(world, stage):
            return

        raw_players = world.resources.get("active_players")
        if type(raw_players) is not tuple or any(type(player) is not ActivePlayer for player in raw_players):
            raise TypeError("active_players must be a tuple of ActivePlayer values")
        active_slots = tuple(player.slot for player in cast(tuple[ActivePlayer, ...], raw_players))
        if not active_slots:
            return
        rows = world.query(PlayerSlot, Transform, Collider, Health)
        by_slot: dict[int, tuple[Transform, Collider, Health]] = {}
        for _, slot, transform, collider, health in rows:
            if slot.slot in active_slots:
                by_slot.setdefault(slot.slot, (transform, collider, health))
        if tuple(sorted(by_slot)) != active_slots:
            raise ValueError("goal participants must exactly match active player slots")

        goals = world.query(StageGoal, Transform, Collider)
        if len(goals) != 1:
            raise RuntimeError("stages must retain exactly one goal entity")
        _, goal, goal_transform, goal_collider = goals[0]
        if (goal.stage_id, goal.world_id, goal.node_id) != (
            stage.stage_id,
            stage.world_id,
            stage.node_id,
        ):
            raise ValueError("goal identity must match the active stage")
        goal_rect = Rect(
            goal_transform.x,
            goal_transform.y,
            goal_collider.width,
            goal_collider.height,
        )
        for slot in active_slots:
            transform, collider, health = by_slot[slot]
            if health.dead or not goal_rect.intersects(Rect(transform.x, transform.y, collider.width, collider.height)):
                return

        result = build_stage_result(
            world,
            stage,
            (world.frame_index + 1) * dt_ms,
        )
        world.resources["stage_result"] = result
        world.resources["stage_outcome"] = StageOutcome.COMPLETED
        publish(
            world,
            GameplayTopic.STAGE_COMPLETED,
            stage_id=result.stage_id,
            node_id=result.node_id,
            clear_time_ms=result.clear_time_ms,
            collected_mote_ids=result.collected_mote_ids,
        )

    @staticmethod
    def _boss_gate_is_open(world: World, stage: StageSpec) -> bool:
        boss_rows = world.query(BossState)
        if stage.boss_id is None:
            if boss_rows:
                raise RuntimeError("non-boss stages must not contain boss entities")
            return True
        if len(boss_rows) != 1:
            raise RuntimeError("boss stages must retain exactly one boss entity")
        boss_id, state = cast(tuple[int, BossState], boss_rows[0])
        health = world.try_component(boss_id, Health)
        if health is None:
            raise RuntimeError("boss entities must retain terminal health state")
        if state.boss_id != stage.boss_id:
            raise ValueError("boss entity identity must match the stage catalog")
        if state.defeated and (not health.dead or health.current != 0):
            raise ValueError("boss defeat state must match terminal boss health")
        return state.defeated


__all__ = ["StageGoalSystem"]
