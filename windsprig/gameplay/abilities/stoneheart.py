"""Stoneheart's airborne-only armored ground slam."""

from __future__ import annotations

from windsprig.gameplay.components import AttackRequest

from .base import AbilityContext, AbilityExecution


class StoneheartStrategy:
    """Refuse grounded use and emit one guarded landing attack while airborne."""

    __slots__ = ()
    name = "stoneheart"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        if context.on_ground:
            return AbilityExecution((), cooldown_ms=0, next_combo_step=0)
        attack = AttackRequest(
            owner_entity_id=context.actor_id,
            team="player",
            ability_id=self.name,
            attack_kind="ground_slam",
            visual_id="stoneheart_ground_slam",
            x=context.x - 4.0,
            y=context.y + 20.0,
            width=36,
            height=44,
            vx=0.0,
            vy=520.0,
            damage=6,
            knockback_x=0.0,
            knockback_y=-180.0,
            ttl_ms=480,
            guard_break=True,
            interaction_kind="breakable_floor",
        )
        return AbilityExecution(
            (attack,),
            cooldown_ms=420,
            next_combo_step=0,
            armor_ms=420,
        )
