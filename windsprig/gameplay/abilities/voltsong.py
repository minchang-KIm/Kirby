"""Voltsong's deterministic conductor pulse and chain selection."""

from __future__ import annotations

from collections.abc import Sequence

from windsprig.gameplay.components import AttackRequest

from .base import AbilityContext, AbilityExecution

CHAIN_RADIUS_PX = 132.0
CHAIN_TARGET_LIMIT = 3


def select_chain_targets(
    origin: tuple[float, float],
    candidates: Sequence[tuple[int, float, float]],
    radius_px: float = CHAIN_RADIUS_PX,
    limit: int = CHAIN_TARGET_LIMIT,
) -> tuple[int, ...]:
    """Return in-range IDs ordered by squared distance and then stable entity ID."""
    if radius_px < 0.0 or limit <= 0:
        return ()
    origin_x, origin_y = origin
    radius_squared = radius_px * radius_px
    eligible = (
        (
            (candidate_x - origin_x) ** 2 + (candidate_y - origin_y) ** 2,
            entity_id,
        )
        for entity_id, candidate_x, candidate_y in candidates
    )
    ordered = sorted(
        (distance_squared, entity_id)
        for distance_squared, entity_id in eligible
        if distance_squared <= radius_squared
    )
    return tuple(entity_id for _, entity_id in ordered[:limit])


class VoltsongStrategy:
    """Emit one short-lived pulse that can chain and energize conductors."""

    __slots__ = ()
    name = "voltsong"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        attack = AttackRequest(
            owner_entity_id=context.actor_id,
            team="player",
            ability_id=self.name,
            attack_kind="chain_pulse",
            visual_id="voltsong_chain_pulse",
            x=context.x - CHAIN_RADIUS_PX,
            y=context.y - CHAIN_RADIUS_PX,
            width=int(CHAIN_RADIUS_PX * 2),
            height=int(CHAIN_RADIUS_PX * 2),
            vx=0.0,
            vy=0.0,
            damage=2,
            knockback_x=80.0 * (1 if context.facing >= 0 else -1),
            knockback_y=-40.0,
            ttl_ms=96,
            pierce=2,
            interaction_kind="conductor",
        )
        return AbilityExecution((attack,), cooldown_ms=280, next_combo_step=0)
