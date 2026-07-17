"""Tempest's full-meter one-shot screen attack."""

from __future__ import annotations

from windsprig.gameplay.components import AttackRequest

from .base import AbilityContext, AbilityExecution


class TempestStrategy:
    """Spend a full meter and request one screen volume before restoring the prior ability."""

    __slots__ = ()
    name = "tempest"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        if context.meter < 100:
            return AbilityExecution((), cooldown_ms=0, next_combo_step=0)
        attack = AttackRequest(
            owner_entity_id=context.actor_id,
            team="player",
            ability_id=self.name,
            attack_kind="screen_tempest",
            visual_id="tempest_screen",
            x=0.0,
            y=0.0,
            width=0,
            height=0,
            vx=0.0,
            vy=0.0,
            damage=5,
            knockback_x=0.0,
            knockback_y=-120.0,
            ttl_ms=32,
            pierce=10_000,
        )
        return AbilityExecution(
            (attack,),
            cooldown_ms=600,
            next_combo_step=0,
            meter_cost=100,
            restore_previous=True,
        )
