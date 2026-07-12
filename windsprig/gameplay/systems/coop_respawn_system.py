"""Own stage-boundary defeat and the pre-Task-10 teammate recovery seam."""

from __future__ import annotations

from typing import cast

from windsprig.config import GameConfig
from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    NON_ENTITY_DAMAGE_SOURCE_ID,
    ActorState,
    Collider,
    DamageRecord,
    Health,
    PlayerSlot,
    Respawn,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.validation import validate_damage_queue
from windsprig.input.roster import ActivePlayer

type PlayerRespawnRow = tuple[
    int,
    PlayerSlot,
    Respawn,
    Transform,
    Velocity,
    Collider,
    Health,
    ActorState,
]
type PlayerBoundaryRow = tuple[int, PlayerSlot, Transform, Health]


class CoopRespawnSystem:
    """Fail an all-dead active team before any teammate recovery can run."""

    def update(self, world: World, dt_ms: int) -> None:
        stage = world.resources.get("stage_spec")
        if not isinstance(stage, StageSpec):
            raise TypeError("stage_spec must be a StageSpec")
        outcome = world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        if outcome is not StageOutcome.RUNNING:
            return

        boundary_rows = cast(
            list[PlayerBoundaryRow],
            world.query(PlayerSlot, Transform, Health),
        )
        rows = cast(
            list[PlayerRespawnRow],
            world.query(
                PlayerSlot,
                Respawn,
                Transform,
                Velocity,
                Collider,
                Health,
                ActorState,
            ),
        )
        active_slots = self._active_slots(world, boundary_rows)
        active_boundary_rows = sorted(
            (row for row in boundary_rows if row[1].slot in active_slots),
            key=lambda row: (row[1].slot, row[0]),
        )
        active_rows = sorted(
            (row for row in rows if row[1].slot in active_slots),
            key=lambda row: (row[1].slot, row[0]),
        )
        if tuple(row[1].slot for row in active_rows) != active_slots:
            raise ValueError("respawn participants must exactly match active player slots")
        if tuple(row[1].slot for row in active_boundary_rows) != active_slots:
            raise ValueError("stage-boundary participants must exactly match active player slots")
        if not active_boundary_rows:
            return

        raw_queue = world.resources.get("damage_queue")
        validate_damage_queue(raw_queue)
        damage_queue = cast(list[DamageRecord], raw_queue)
        queued_targets = {record.target_id for record in damage_queue}
        for entity_id, _, transform, health in active_boundary_rows:
            collider = world.try_component(entity_id, Collider)
            # Physics clamps at the authored bottom; compare collider bottom so the
            # clamped player still enters the normal typed damage/death path.
            if (
                not health.dead
                and collider is not None
                and transform.y + collider.height >= stage.pixel_height
                and entity_id not in queued_targets
            ):
                damage_queue.append(
                    DamageRecord(
                        source_id=NON_ENTITY_DAMAGE_SOURCE_ID,
                        target_id=entity_id,
                        amount=health.maximum,
                        knockback_x=0.0,
                        knockback_y=-220.0,
                        guard_break=True,
                    )
                )

        living = [row for row in active_boundary_rows if not row[3].dead]
        if not living:
            world.resources["stage_result"] = None
            world.resources["stage_outcome"] = StageOutcome.FAILED
            publish(
                world,
                GameplayTopic.STAGE_FAILED,
                stage_id=stage.stage_id,
                node_id=stage.node_id,
                active_slots=active_slots,
            )
            return

        # Task 10 replaces this existing prototype recovery with the final gather
        # and living-anchor contract; Task 9 only prevents it from defeating all-dead.
        anchor = (living[0][2].x, living[0][2].y)
        checkpoint_id = world.resources.get("active_checkpoint_id")
        if type(checkpoint_id) is not str or not checkpoint_id:
            raise TypeError("active_checkpoint_id must be a non-empty checkpoint ID")
        config = world.resources.get("config")
        if not isinstance(config, GameConfig):
            raise TypeError("config must be a GameConfig")
        invulnerable_ms = config.respawn_invulnerable_ms
        for entity_id, slot, respawn, transform, velocity, collider, health, state in active_rows:
            if not health.dead:
                continue
            respawn.timer_ms = max(0, respawn.timer_ms - dt_ms)
            if respawn.timer_ms > 0 or slot.lives <= 0:
                continue
            slot.lives -= 1
            health.dead = False
            health.current = max(1, health.maximum // 2)
            health.invulnerable_ms = invulnerable_ms
            transform.x = anchor[0] + 18 * (slot.slot - 1)
            transform.y = anchor[1] - 28
            velocity.vx = 0.0
            velocity.vy = -100.0
            collider.on_ground = False
            state.name = "Idle"
            publish(
                world,
                GameplayTopic.PLAYER_RESPAWNED,
                entity_id=entity_id,
                slot=slot.slot,
                checkpoint_id=checkpoint_id,
                cost=1,
            )

    @staticmethod
    def _active_slots(
        world: World,
        rows: list[PlayerBoundaryRow],
    ) -> tuple[int, ...]:
        raw_players = world.resources.get("active_players")
        if type(raw_players) is not tuple or any(type(player) is not ActivePlayer for player in raw_players):
            raise TypeError("active_players must be a tuple of ActivePlayer values")
        players = cast(tuple[ActivePlayer, ...], raw_players)
        slots = tuple(player.slot for player in players)
        if slots != tuple(sorted(slots)) or len(slots) != len(set(slots)):
            raise ValueError("active player slots must be unique and sorted")
        return slots


__all__ = ["CoopRespawnSystem"]
