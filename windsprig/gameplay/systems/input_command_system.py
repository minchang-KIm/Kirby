from __future__ import annotations

from windsprig.gameplay.components import ControlIntent, Facing, PlayerSlot
from windsprig.input.commands import (
    AbilityUseCommand,
    DodgeCommand,
    DropAbilityCommand,
    HoverCommand,
    GuardCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)


class InputCommandSystem:
    def update(self, world, dt_ms: int) -> None:
        _ = dt_ms
        input_frame = world.frame_input
        if not isinstance(input_frame, InputFrame):
            return

        for _, _, intent in world.query(PlayerSlot, ControlIntent):
            intent.move_axis = 0
            intent.jump_pressed = False
            intent.float_held = False
            intent.draw_pressed = False
            intent.draw_released = False
            intent.ability_pressed = False
            intent.guard_held = False
            intent.dodge_pressed = False
            intent.drop_pressed = False

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
                    intent.float_held = command.held
                elif isinstance(command, DrawStartCommand):
                    intent.draw_pressed = True
                elif isinstance(command, DrawReleaseCommand):
                    intent.draw_released = True
                elif isinstance(command, AbilityUseCommand):
                    intent.ability_pressed = command.pressed
                elif isinstance(command, GuardCommand):
                    intent.guard_held = command.held
                elif isinstance(command, DodgeCommand):
                    intent.dodge_pressed = command.pressed
                elif isinstance(command, DropAbilityCommand):
                    intent.drop_pressed = command.pressed
