"""Map one fixed-step command frame onto mutable player intent components."""

from __future__ import annotations

from windsprig.core.ecs import World
from windsprig.gameplay.components import ControlIntent, Facing, PlayerSlot
from windsprig.input.commands import (
    AbilityUseCommand,
    DodgeCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    GatherConfirmCommand,
    GuardCommand,
    HoverCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)


class InputCommandSystem:
    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        input_frame = world.frame_input
        for _, _, intent in world.query(PlayerSlot, ControlIntent):
            intent.jump_pressed = False
            intent.draw_started = False
            intent.draw_released = False
            intent.ability_pressed = False
            intent.ability_released = False
            intent.ability_consumed = False
            intent.dodge_pressed = False
            intent.drop_pressed = False
            intent.gather_confirmed = False
        if not isinstance(input_frame, InputFrame):
            return

        for _, _, intent in world.query(PlayerSlot, ControlIntent):
            intent.move_axis = 0
            intent.hover_held = False
            intent.guard_held = False
            intent.ability_held = False

        for entity_id, slot, intent in world.query(PlayerSlot, ControlIntent):
            for command in input_frame.commands_for(slot.slot):
                if isinstance(command, MoveCommand):
                    intent.move_axis = command.axis
                    facing = world.try_component(entity_id, Facing)
                    if facing is not None and command.axis != 0:
                        facing.direction = 1 if command.axis > 0 else -1
                elif isinstance(command, JumpCommand):
                    intent.jump_pressed = command.pressed
                elif isinstance(command, HoverCommand):
                    intent.hover_held = command.held
                elif isinstance(command, DrawStartCommand):
                    intent.draw_started = True
                elif isinstance(command, DrawReleaseCommand):
                    intent.draw_released = True
                elif isinstance(command, AbilityUseCommand):
                    intent.ability_pressed = intent.ability_pressed or command.pressed
                    intent.ability_released = intent.ability_released or command.released
                    if not command.pressed and not command.released:
                        intent.ability_held = command.held
                    elif command.held:
                        intent.ability_held = True
                elif isinstance(command, GuardCommand):
                    intent.guard_held = command.held
                elif isinstance(command, DodgeCommand):
                    intent.dodge_pressed = command.pressed
                elif isinstance(command, DropAbilityCommand):
                    intent.drop_pressed = command.pressed
                elif isinstance(command, GatherConfirmCommand):
                    intent.gather_confirmed = intent.gather_confirmed or command.pressed
