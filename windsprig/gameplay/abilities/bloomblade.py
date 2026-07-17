"""Bloomblade's deterministic three-step melee combo."""

from __future__ import annotations

from windsprig.gameplay.components import AttackRequest

from .base import AbilityContext, AbilityExecution

_DAMAGES = (2, 2, 4)
_COOLDOWNS_MS = (120, 120, 260)


class BloombladeStrategy:
    """Create one projectile-cutting melee arc for each accepted press."""

    __slots__ = ()
    name = "bloomblade"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        combo_step = context.combo_step if context.combo_step in range(3) else 0
        facing = 1 if context.facing >= 0 else -1
        attack = AttackRequest(
            owner_entity_id=context.actor_id,
            team="player",
            ability_id=self.name,
            attack_kind="melee_arc",
            visual_id=f"bloomblade_arc_{combo_step + 1}",
            x=context.x + 28 * facing,
            y=context.y + 2,
            width=38,
            height=30,
            vx=0.0,
            vy=0.0,
            damage=_DAMAGES[combo_step],
            knockback_x=180.0 * facing,
            knockback_y=-80.0,
            ttl_ms=80,
            cuts_projectiles=True,
        )
        return AbilityExecution(
            attacks=(attack,),
            cooldown_ms=_COOLDOWNS_MS[combo_step],
            next_combo_step=(combo_step + 1) % 3,
            combo_window_ms=260,
        )
