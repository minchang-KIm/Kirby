"""Complete stages through all-player readiness or a leader-owned gather."""

from __future__ import annotations

from typing import Literal, cast

from windsprig.config import GameConfig
from windsprig.content.models import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.bosses import BossState
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    ControlIntent,
    GatherState,
    Health,
    PlayerSlot,
    Respawn,
    StageGoal,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.validation import build_stage_result, validate_gather_state
from windsprig.input.roster import ActivePlayer
from windsprig.math2d import Rect

type GoalPlayerRow = tuple[int, PlayerSlot, Transform, Collider, Health, ControlIntent]
type GatherCancelReason = Literal["leader_left_goal", "leader_defeated", "roster_changed"]

GATHER_FORMATION_SPACING_PX = 6.0


def goal_participation(
    world: World,
    active_slots: tuple[int, ...],
    goal_transform: Transform,
    goal_collider: Collider,
) -> tuple[dict[int, GoalPlayerRow], tuple[int, ...], tuple[int, ...]]:
    """Return canonical active rows, required slots, and living goal overlaps."""

    if active_slots != tuple(sorted(set(active_slots))):
        raise ValueError("goal active slots must be unique canonical order")
    goal_rect = Rect(goal_transform.x, goal_transform.y, goal_collider.width, goal_collider.height)
    by_slot: dict[int, GoalPlayerRow] = {}
    for row in cast(list[GoalPlayerRow], world.query(PlayerSlot, Transform, Collider, Health, ControlIntent)):
        slot = row[1].slot
        if slot not in active_slots:
            continue
        if slot in by_slot:
            raise ValueError("goal participant slots must be unique")
        by_slot[slot] = row
    if tuple(sorted(by_slot)) != active_slots:
        raise ValueError("goal participants must exactly match active player slots")

    required_slots = tuple(
        slot
        for slot in active_slots
        if not (by_slot[slot][4].dead and by_slot[slot][1].lives == 0)
    )
    at_goal_slots = tuple(
        slot
        for slot in required_slots
        if not by_slot[slot][4].dead
        and goal_rect.intersects(
            Rect(
                by_slot[slot][2].x,
                by_slot[slot][2].y,
                by_slot[slot][3].width,
                by_slot[slot][3].height,
            )
        )
    )
    return by_slot, required_slots, at_goal_slots


class StageGoalSystem:
    """Own the one-shot goal gate and deterministic team-gather lifecycle."""

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

        active_players = self._active_players(world)
        active_slots = tuple(player.slot for player in active_players)
        if not active_slots:
            return
        goal, gather, goal_transform, goal_collider = self._goal_row(world, stage)
        _ = goal
        validate_gather_state(gather)
        by_slot, required_slots, at_goal_slots = goal_participation(
            world,
            active_slots,
            goal_transform,
            goal_collider,
        )
        gather.at_goal_slots = at_goal_slots

        if gather.countdown_remaining_ms > 0:
            leader_slot = gather.leader_slot
            if leader_slot not in by_slot or not by_slot[leader_slot][1].is_leader:
                self._cancel(world, gather, "roster_changed")
                return
            # PlayerSlot is hashed ECS authority; ActivePlayer only carries
            # routing metadata and may legitimately differ between sync points.
            leader_health = by_slot[leader_slot][4]
            if leader_health.dead:
                self._cancel(world, gather, "leader_defeated")
                return
            if leader_slot not in at_goal_slots:
                self._cancel(world, gather, "leader_left_goal")
                return
            if required_slots and at_goal_slots == required_slots:
                # Arrival resolves an already-started gather through its normal
                # event/state lifecycle even when no teleport remains necessary.
                self._complete_gather(
                    world,
                    stage,
                    dt_ms,
                    gather,
                    goal_transform,
                    by_slot,
                    required_slots,
                    at_goal_slots,
                )
                return
            gather.countdown_remaining_ms = max(0, gather.countdown_remaining_ms - dt_ms)
            if gather.countdown_remaining_ms == 0:
                self._complete_gather(
                    world,
                    stage,
                    dt_ms,
                    gather,
                    goal_transform,
                    by_slot,
                    required_slots,
                    at_goal_slots,
                )
            return

        if required_slots and at_goal_slots == required_slots:
            self._complete_stage(world, stage, dt_ms)
            return

        leader_slot = next((slot for slot in active_slots if by_slot[slot][1].is_leader), None)
        if leader_slot is None or leader_slot not in at_goal_slots:
            return
        if not by_slot[leader_slot][5].gather_confirmed:
            return
        gather.leader_slot = leader_slot
        gather.leader_confirmed = True
        config = world.resources.get("config")
        if not isinstance(config, GameConfig):
            raise TypeError("config must be a GameConfig")
        gather.countdown_remaining_ms = config.gather_countdown_ms
        publish(
            world,
            GameplayTopic.GATHER_STARTED,
            leader_slot=leader_slot,
            countdown_ms=gather.countdown_remaining_ms,
            waiting_slots=tuple(slot for slot in required_slots if slot not in at_goal_slots),
        )

    @staticmethod
    def _active_players(world: World) -> tuple[ActivePlayer, ...]:
        raw_players = world.resources.get("active_players")
        if type(raw_players) is not tuple or any(type(player) is not ActivePlayer for player in raw_players):
            raise TypeError("active_players must be a tuple of ActivePlayer values")
        players = cast(tuple[ActivePlayer, ...], raw_players)
        slots = tuple(player.slot for player in players)
        if slots != tuple(sorted(set(slots))):
            raise ValueError("active player slots must be unique canonical order")
        return players

    @staticmethod
    def _goal_row(
        world: World,
        stage: StageSpec,
    ) -> tuple[StageGoal, GatherState, Transform, Collider]:
        goals = world.query(StageGoal, GatherState, Transform, Collider)
        if len(goals) != 1:
            raise RuntimeError("stages must retain exactly one goal and gather state")
        _, goal, gather, transform, collider = cast(
            tuple[int, StageGoal, GatherState, Transform, Collider],
            goals[0],
        )
        if (goal.stage_id, goal.world_id, goal.node_id) != (
            stage.stage_id,
            stage.world_id,
            stage.node_id,
        ):
            raise ValueError("goal identity must match the active stage")
        return goal, gather, transform, collider

    @staticmethod
    def _cancel(world: World, gather: GatherState, reason: GatherCancelReason) -> None:
        leader_slot = gather.cancel()
        if leader_slot is None:
            raise ValueError("only an active leader gather can be cancelled")
        publish(
            world,
            GameplayTopic.GATHER_CANCELLED,
            leader_slot=leader_slot,
            reason=reason,
        )

    @staticmethod
    def _complete_gather(
        world: World,
        stage: StageSpec,
        dt_ms: int,
        gather: GatherState,
        goal_transform: Transform,
        by_slot: dict[int, GoalPlayerRow],
        required_slots: tuple[int, ...],
        at_goal_slots: tuple[int, ...],
    ) -> None:
        if gather.leader_slot is None or not gather.leader_confirmed:
            raise ValueError("gather completion requires its confirmed leader")
        config = world.resources.get("config")
        if not isinstance(config, GameConfig):
            raise TypeError("config must be a GameConfig")
        checkpoint_id = world.resources.get("active_checkpoint_id")
        if type(checkpoint_id) is not str or not checkpoint_id:
            raise TypeError("active_checkpoint_id must be a non-empty checkpoint ID")
        waiting_slots = tuple(slot for slot in required_slots if slot not in at_goal_slots)
        for slot_number in waiting_slots:
            entity_id, slot, transform, collider, health, _ = by_slot[slot_number]
            # Compact one-based offsets keep all four player origins inside the
            # narrow goal while preserving a stable, slot-visible spread.
            transform.x = goal_transform.x + GATHER_FORMATION_SPACING_PX * (slot_number - 1)
            transform.y = goal_transform.y
            velocity = world.get_component(entity_id, Velocity)
            velocity.vx = velocity.vy = 0.0
            collider.on_ground = False
            if not health.dead:
                continue
            if slot.lives <= 0:
                raise ValueError("dead gathered players must have a life to spend")
            slot.lives -= 1
            health.current = max(1, health.maximum // 2)
            health.dead = False
            health.invulnerable_ms = config.respawn_invulnerable_ms
            actor = world.get_component(entity_id, ActorState)
            actor.name = "Idle"
            actor.timer_ms = 0
            respawn = world.get_component(entity_id, Respawn)
            respawn.timer_ms = 0
            respawn.started_frame = -1
            publish(
                world,
                GameplayTopic.PLAYER_RESPAWNED,
                entity_id=entity_id,
                slot=slot_number,
                checkpoint_id=checkpoint_id,
                cost=1,
            )
        leader_slot = gather.leader_slot
        gather.cancel()
        gather.at_goal_slots = required_slots
        publish(
            world,
            GameplayTopic.GATHER_COMPLETED,
            leader_slot=leader_slot,
            gathered_slots=waiting_slots,
        )
        StageGoalSystem._complete_stage(world, stage, dt_ms)

    @staticmethod
    def _complete_stage(world: World, stage: StageSpec, dt_ms: int) -> None:
        result = build_stage_result(world, stage, (world.frame_index + 1) * dt_ms)
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


__all__ = ["StageGoalSystem", "goal_participation"]
