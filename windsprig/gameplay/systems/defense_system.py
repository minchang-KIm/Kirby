"""Resolve deterministic guard and dodge intent before movement."""

from __future__ import annotations

from typing import cast

from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    ControlIntent,
    DefenseState,
    Facing,
    Health,
    PlayerSlot,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.state_machine import can_transition, transition


class DefenseSystem:
    """Own player guard state, dodge timers, and dodge velocity."""

    def update(self, world: World, dt_ms: int) -> None:
        config = cast(GameConfig, world.resources["config"])
        for entity_id, slot, intent, defense, facing, collider, velocity, state, health in world.query(
            PlayerSlot,
            ControlIntent,
            DefenseState,
            Facing,
            Collider,
            Velocity,
            ActorState,
            Health,
        ):
            dodge_was_active = defense.dodge_remaining_ms > 0
            # WHY: existing timers tick before an edge so 512 ms rejects and 528 ms accepts.
            defense.dodge_remaining_ms = max(0, defense.dodge_remaining_ms - dt_ms)
            defense.dodge_cooldown_ms = max(0, defense.dodge_cooldown_ms - dt_ms)

            if health.dead or state.name == "Dead":
                defense.guarding = False
                continue

            if state.name == "Hurt":
                defense.guarding = False
                state.timer_ms = max(0, state.timer_ms - dt_ms)
                if state.timer_ms > 0:
                    continue
                state.name = transition(state.name, _resting_state(collider, velocity))

            if dodge_was_active and defense.dodge_remaining_ms > 0:
                defense.guarding = False
                facing.direction = defense.dodge_direction
                velocity.vx = config.dodge_speed * defense.dodge_direction
                state.name = "Dodge"
                continue
            if dodge_was_active:
                state.name = transition(state.name, _resting_state(collider, velocity))

            if (
                intent.dodge_pressed
                and defense.dodge_cooldown_ms == 0
                and can_transition(state.name, "Dodge")
            ):
                direction = _dodge_direction(intent.move_axis, facing.direction)
                defense.guarding = False
                defense.dodge_remaining_ms = config.dodge_duration_ms
                defense.dodge_cooldown_ms = config.dodge_cooldown_ms
                defense.dodge_direction = direction
                facing.direction = direction
                velocity.vx = config.dodge_speed * direction
                state.name = transition(state.name, "Dodge")
                publish(
                    world,
                    GameplayTopic.PLAYER_DODGED,
                    entity_id=entity_id,
                    slot=slot.slot,
                    direction=direction,
                )
                continue

            can_guard = (
                intent.guard_held
                and collider.on_ground
                and state.name not in {"Hurt", "Dead"}
                and (state.name == "Guard" or can_transition(state.name, "Guard"))
            )
            if can_guard:
                defense.guarding = True
                state.name = transition(state.name, "Guard")
            else:
                was_guarding = defense.guarding or state.name == "Guard"
                defense.guarding = False
                if was_guarding:
                    state.name = transition(state.name, _resting_state(collider, velocity))


def _dodge_direction(move_axis: int, facing: int) -> int:
    if move_axis != 0:
        return 1 if move_axis > 0 else -1
    return 1 if facing >= 0 else -1


def _resting_state(collider: Collider, velocity: Velocity) -> str:
    if not collider.on_ground:
        return "Fall"
    return "Run" if abs(velocity.vx) > 40.0 else "Idle"
