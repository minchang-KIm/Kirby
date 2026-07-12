"""Activate catalog checkpoints for the living active team exactly once."""

from __future__ import annotations

from typing import cast

from windsprig.content.models import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    Collider,
    Health,
    PlayerSlot,
    Respawn,
    Transform,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.validation import validate_checkpoint_state
from windsprig.input.roster import ActivePlayer
from windsprig.math2d import Rect


class CheckpointSystem:
    """Advance the single team checkpoint in stable entity order."""

    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        outcome = world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        stage = world.resources.get("stage_spec")
        if not isinstance(stage, StageSpec):
            raise TypeError("stage_spec must be a StageSpec")
        checkpoint_rows = validate_checkpoint_state(world, stage)
        if outcome is not StageOutcome.RUNNING:
            return

        raw_players = world.resources.get("active_players")
        if type(raw_players) is not tuple or any(type(player) is not ActivePlayer for player in raw_players):
            raise TypeError("active_players must be a tuple of ActivePlayer values")
        active_slots = {player.slot for player in cast(tuple[ActivePlayer, ...], raw_players)}
        players = [
            row
            for row in world.query(PlayerSlot, Transform, Collider, Health, Respawn)
            if row[1].slot in active_slots and not row[4].dead
        ]

        for _, checkpoint, checkpoint_transform, checkpoint_collider in checkpoint_rows:
            if checkpoint.active:
                continue
            checkpoint_rect = Rect(
                checkpoint_transform.x,
                checkpoint_transform.y,
                checkpoint_collider.width,
                checkpoint_collider.height,
            )
            overlapping = next(
                (
                    row
                    for row in players
                    if checkpoint_rect.intersects(Rect(row[2].x, row[2].y, row[3].width, row[3].height))
                ),
                None,
            )
            if overlapping is None:
                continue

            respawn_targets = tuple(
                (
                    respawn,
                    checkpoint.x,
                    checkpoint.y - index * player_collider.height,
                )
                for index, (_, _, _, player_collider, _, respawn) in enumerate(players)
            )
            if any(y < 0.0 for _, _, y in respawn_targets):
                raise ValueError("checkpoint player offsets must stay inside the stage")
            for _, candidate, _, _ in checkpoint_rows:
                candidate.active = candidate is checkpoint
            world.resources["active_checkpoint_id"] = checkpoint.checkpoint_id
            for respawn, x, y in respawn_targets:
                respawn.x = x
                # Vertical offsets remain supported by the one authored safe tile.
                respawn.y = y
            player_id, slot, _, _, _, _ = overlapping
            publish(
                world,
                GameplayTopic.CHECKPOINT_REACHED,
                checkpoint_id=checkpoint.checkpoint_id,
                player_id=player_id,
                slot=slot.slot,
            )
            return


__all__ = ["CheckpointSystem"]
