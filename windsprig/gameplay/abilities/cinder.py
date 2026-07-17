"""Cinder's deterministic hold-to-charge ember."""

from __future__ import annotations

from windsprig.gameplay.components import AttackRequest

from .base import AbilityContext, AbilityExecution

MAX_CHARGE_MS = 640


class CinderStrategy:
    """Scale one charged ember from a clamped fixed-step hold duration."""

    __slots__ = ()
    name = "cinder"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        charge_ms = max(0, min(MAX_CHARGE_MS, context.charge_ms))
        charge_ratio = min(1.0, charge_ms / 640.0)
        facing = 1 if context.facing >= 0 else -1
        attack = AttackRequest(
            owner_entity_id=context.actor_id,
            team="player",
            ability_id=self.name,
            attack_kind="charged_ember",
            visual_id="cinder_ember_charged" if charge_ratio == 1.0 else "cinder_ember",
            x=context.x + 20 * facing,
            y=context.y + 8,
            width=18 + int(14 * charge_ratio),
            height=14 + int(10 * charge_ratio),
            vx=(360.0 + 160.0 * charge_ratio) * facing,
            vy=-20.0,
            damage=2 + int(3 * charge_ratio),
            knockback_x=220.0 * facing,
            knockback_y=-100.0,
            ttl_ms=900,
            pierce=0,
            interaction_kind="spawn_burn_zone",
        )
        return AbilityExecution((attack,), cooldown_ms=320, next_combo_step=0)
