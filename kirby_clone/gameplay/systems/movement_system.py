from __future__ import annotations

from kirby_clone.gameplay.components import (
    ActorState,
    Collider,
    ControlIntent,
    PlayerSlot,
    Team,
    Transform,
    Velocity,
)
from kirby_clone.gameplay.state_machine import transition
from kirby_clone.settings import GameConfig


class MovementSystem:
    def update(self, world, dt_ms: int) -> None:
        config: GameConfig = world.resources["config"]
        dt_s = dt_ms / 1000.0

        for entity_id, _, _, _, velocity, collider, intent, state in world.query(
            PlayerSlot,
            Team,
            Transform,
            Velocity,
            Collider,
            ControlIntent,
            ActorState,
        ):
            target_speed = intent.move_axis * config.move_speed
            accel = 2400.0 if collider.on_ground else 1700.0
            if intent.guard_held:
                target_speed *= 0.4
            if intent.move_axis != 0:
                if velocity.vx < target_speed:
                    velocity.vx = min(target_speed, velocity.vx + accel * dt_s)
                else:
                    velocity.vx = max(target_speed, velocity.vx - accel * dt_s)
            else:
                decel = 3000.0
                if velocity.vx > 0:
                    velocity.vx = max(0.0, velocity.vx - decel * dt_s)
                else:
                    velocity.vx = min(0.0, velocity.vx + decel * dt_s)

            if intent.jump_pressed and collider.on_ground:
                velocity.vy = -config.jump_velocity
                collider.on_ground = False
                state.name = transition(state.name, "Jump")

            if intent.float_held and velocity.vy > -30.0:
                velocity.vy -= 540.0 * dt_s
                state.name = transition(state.name, "Float")

        for entity_id, velocity, collider in world.query(Velocity, Collider):
            _ = entity_id
            velocity.vy = min(velocity.vy + config.gravity * dt_s, 1600.0)
