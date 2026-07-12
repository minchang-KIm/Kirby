"""Apply deterministic buffered player movement and actor gravity."""

from __future__ import annotations

from typing import cast

from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    ControlIntent,
    DefenseState,
    Health,
    MovementState,
    PlayerSlot,
    Projectile,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.state_machine import transition


class MovementSystem:
    """Own acceleration, buffered jumping, finite hover, and gravity."""

    def update(self, world: World, dt_ms: int) -> None:
        config = cast(GameConfig, world.resources["config"])
        dt_s = dt_ms / 1000.0
        gravity_scales: dict[int, float] = {}

        for entity_id, _, _, _, velocity, collider, intent, state, movement, defense, health in world.query(
            PlayerSlot,
            Team,
            Transform,
            Velocity,
            Collider,
            ControlIntent,
            ActorState,
            MovementState,
            DefenseState,
            Health,
        ):
            if collider.on_ground:
                movement.coyote_remaining_ms = config.coyote_time_ms
                movement.hover_remaining_ms = config.hover_duration_ms
                movement.hover_ready = True
            else:
                movement.coyote_remaining_ms = max(0, movement.coyote_remaining_ms - dt_ms)

            if intent.jump_pressed:
                movement.jump_buffer_remaining_ms = config.jump_buffer_ms
            else:
                movement.jump_buffer_remaining_ms = max(
                    0,
                    movement.jump_buffer_remaining_ms - dt_ms,
                )

            dodge_active = defense.dodge_remaining_ms > 0
            if not dodge_active:
                can_jump = collider.on_ground or movement.coyote_remaining_ms > 0
                jump_state = transition(state.name, "Jump")
                if not health.dead and jump_state == "Jump" and can_jump and movement.jump_buffer_remaining_ms > 0:
                    velocity.vy = -config.jump_velocity
                    collider.on_ground = False
                    movement.coyote_remaining_ms = 0
                    movement.jump_buffer_remaining_ms = 0
                    state.name = jump_state

                if not health.dead:
                    target_speed = intent.move_axis * config.move_speed
                    if defense.guarding:
                        target_speed *= config.guard_speed_multiplier
                    _accelerate_horizontal(velocity, target_speed, intent.move_axis, collider, dt_s)

            gravity_scale = 1.0
            hover_state = transition(state.name, "Hover")
            hovering = (
                not health.dead
                and not dodge_active
                and hover_state == "Hover"
                and intent.hover_held
                and not collider.on_ground
                and movement.hover_ready
                and movement.hover_remaining_ms > 0
            )
            if hovering:
                movement.hover_remaining_ms = max(0, movement.hover_remaining_ms - dt_ms)
                if movement.hover_remaining_ms == 0:
                    movement.hover_ready = False
                gravity_scale = config.hover_gravity_scale
                state.name = hover_state
            elif not health.dead and state.name == "Hover" and not collider.on_ground:
                state.name = transition(state.name, "Fall")
            gravity_scales[entity_id] = gravity_scale

        for entity_id, velocity, _collider in world.query(Velocity, Collider):
            if world.has_component(entity_id, Projectile):
                continue
            gravity_scale = gravity_scales.get(entity_id, 1.0)
            velocity.vy = min(
                velocity.vy + config.gravity * gravity_scale * dt_s,
                1600.0,
            )


def _accelerate_horizontal(
    velocity: Velocity,
    target_speed: float,
    move_axis: int,
    collider: Collider,
    dt_s: float,
) -> None:
    accel = 2400.0 if collider.on_ground else 1700.0
    if move_axis != 0:
        if velocity.vx < target_speed:
            velocity.vx = min(target_speed, velocity.vx + accel * dt_s)
        else:
            velocity.vx = max(target_speed, velocity.vx - accel * dt_s)
        return
    decel = 3000.0
    if velocity.vx > 0:
        velocity.vx = max(0.0, velocity.vx - decel * dt_s)
    else:
        velocity.vx = min(0.0, velocity.vx + decel * dt_s)
