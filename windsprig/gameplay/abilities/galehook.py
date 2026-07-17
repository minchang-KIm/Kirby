"""Galehook's deterministic outbound boomerang request."""

from __future__ import annotations

from windsprig.gameplay.components import AttackRequest

from .base import AbilityContext, AbilityExecution

OUTBOUND_MS = 360
TOTAL_TTL_MS = 800


class GalehookStrategy:
    """Emit one boomerang whose return motion is owned by the attack pipeline."""

    __slots__ = ()
    name = "galehook"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        facing = 1 if context.facing >= 0 else -1
        attack = AttackRequest(
            owner_entity_id=context.actor_id,
            team="player",
            ability_id=self.name,
            attack_kind="boomerang",
            visual_id="galehook_boomerang",
            x=context.x + 20.0 * facing,
            y=context.y + 6.0,
            width=24,
            height=18,
            vx=440.0 * facing,
            vy=0.0,
            damage=2,
            knockback_x=140.0 * facing,
            knockback_y=-60.0,
            ttl_ms=TOTAL_TTL_MS,
            pierce=2,
            pull_strength=260.0,
            interaction_kind="switch",
        )
        return AbilityExecution((attack,), cooldown_ms=360, next_combo_step=0)
