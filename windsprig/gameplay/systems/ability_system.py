"""Translate phased ability intent into deterministic typed attack requests."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.abilities import AbilityContext, AbilityExecution, AbilityRegistry
from windsprig.gameplay.abilities.cinder import MAX_CHARGE_MS
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    AttackRequest,
    Collider,
    ControlIntent,
    Facing,
    Health,
    Team,
    Transform,
)
from windsprig.gameplay.state_machine import can_transition, transition


class AbilitySystem:
    """Own ability timers and append accepted executions to the shared FIFO queue."""

    def update(self, world: World, dt_ms: int) -> None:
        registry = cast(AbilityRegistry, world.resources["ability_registry"])
        requests = cast(
            list[AttackRequest],
            world.resources.setdefault("attack_requests", []),
        )

        for entity_id, team, transform, facing, collider, health, intent, ability, state in world.query(
            Team,
            Transform,
            Facing,
            Collider,
            Health,
            ControlIntent,
            AbilityState,
            ActorState,
        ):
            if team.name != "player":
                continue
            cooldown_was_active = ability.cooldown_remaining_ms > 0
            # Timers tick before an edge, making the first fixed step at zero immediately eligible.
            ability.cooldown_remaining_ms = max(0, ability.cooldown_remaining_ms - dt_ms)
            ability.combo_window_remaining_ms = max(0, ability.combo_window_remaining_ms - dt_ms)
            ability.armor_remaining_ms = max(0, ability.armor_remaining_ms - dt_ms)
            if ability.combo_window_remaining_ms == 0:
                ability.combo_step = 0
            if cooldown_was_active and ability.cooldown_remaining_ms == 0 and state.name == "Attack":
                state.name = transition(state.name, _resting_state(collider, intent))

            if ability.current_id != "cinder":
                ability.charge_ms = 0
            if intent.ability_consumed:
                if ability.current_id == "cinder" and intent.ability_released:
                    ability.charge_ms = 0
                intent.ability_pressed = False
                intent.ability_released = False
                continue

            charge_ms = ability.charge_ms
            if ability.current_id == "cinder":
                if not health.dead and state.name != "Dead" and intent.ability_held:
                    ability.charge_ms = min(MAX_CHARGE_MS, ability.charge_ms + dt_ms)
                charge_ms = ability.charge_ms
                should_activate = intent.ability_released
                intent.ability_pressed = False
                intent.ability_released = False
                if should_activate:
                    ability.charge_ms = 0
            else:
                should_activate = intent.ability_pressed
                intent.ability_pressed = False
                intent.ability_released = False

            if not should_activate or not _can_activate(health, state, ability):
                continue
            execution = registry.get(ability.current_id).activate(
                AbilityContext(
                    actor_id=entity_id,
                    frame_index=world.frame_index,
                    x=transform.x,
                    y=transform.y,
                    facing=facing.direction,
                    on_ground=collider.on_ground,
                    charge_ms=charge_ms,
                    combo_step=ability.combo_step,
                    meter=ability.meter,
                )
            )
            if not _has_effect(execution):
                continue

            requests.extend(_fit_stage_bound_attacks(world, execution.attacks))
            ability.cooldown_remaining_ms = max(0, execution.cooldown_ms)
            ability.combo_step = execution.next_combo_step
            ability.combo_window_remaining_ms = max(0, execution.combo_window_ms)
            ability.armor_remaining_ms = max(ability.armor_remaining_ms, execution.armor_ms)
            ability.meter = max(0, ability.meter - execution.meter_cost)
            if execution.restore_previous:
                restored_id = ability.previous_id
                ability.current_id = "none" if restored_id == "tempest" else restored_id
                ability.previous_id = "none"
            state.name = transition(state.name, "Attack")


def _can_activate(health: Health, state: ActorState, ability: AbilityState) -> bool:
    if health.dead or state.name == "Dead" or ability.cooldown_remaining_ms > 0:
        return False
    return state.name == "Attack" or can_transition(state.name, "Attack")


def _has_effect(execution: AbilityExecution) -> bool:
    return bool(execution.attacks or execution.armor_ms or execution.meter_cost or execution.restore_previous)


def _fit_stage_bound_attacks(
    world: World,
    attacks: tuple[AttackRequest, ...],
) -> tuple[AttackRequest, ...]:
    if not any(attack.attack_kind == "screen_tempest" for attack in attacks):
        return attacks
    stage = world.resources.get("stage_spec")
    if not isinstance(stage, StageSpec):
        raise TypeError("stage_spec must be a StageSpec for screen_tempest")
    return tuple(
        replace(
            attack,
            x=0.0,
            y=0.0,
            width=stage.pixel_width,
            height=stage.pixel_height,
        )
        if attack.attack_kind == "screen_tempest"
        else attack
        for attack in attacks
    )


def _resting_state(collider: Collider, intent: ControlIntent) -> str:
    if not collider.on_ground:
        return "Fall"
    return "Run" if intent.move_axis else "Idle"
