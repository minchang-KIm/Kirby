from __future__ import annotations

import pygame

from .bindings import GAMEPAD_BINDING, KEYBOARD_BINDINGS, KeyboardProfile
from .commands import (
    AbilityUseCommand,
    DodgeCommand,
    DropAbilityCommand,
    FloatCommand,
    GuardCommand,
    InhaleReleaseCommand,
    InhaleStartCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)


class InputDeviceMux:
    """Collects keyboard(2P) + gamepad(2P) into device-agnostic commands."""

    def __init__(self) -> None:
        self._joysticks: dict[int, pygame.joystick.Joystick] = {}
        self.refresh_joysticks()

    def refresh_joysticks(self) -> None:
        pygame.joystick.init()
        self._joysticks = {}
        for index in range(min(2, pygame.joystick.get_count())):
            joy = pygame.joystick.Joystick(index)
            joy.init()
            self._joysticks[index + 3] = joy  # slot 3~4

    def collect_frame(self, events: list[pygame.event.Event], keys: pygame.key.ScancodeWrapper) -> InputFrame:
        edge_down: dict[int, set[int]] = {1: set(), 2: set()}
        edge_up: dict[int, set[int]] = {1: set(), 2: set()}
        gamepad_down: dict[int, set[int]] = {3: set(), 4: set()}
        gamepad_up: dict[int, set[int]] = {3: set(), 4: set()}

        for event in events:
            if event.type == pygame.KEYDOWN:
                for slot, profile in KEYBOARD_BINDINGS.items():
                    if event.key in _profile_keys(profile):
                        edge_down[slot].add(event.key)
            elif event.type == pygame.KEYUP:
                for slot, profile in KEYBOARD_BINDINGS.items():
                    if event.key in _profile_keys(profile):
                        edge_up[slot].add(event.key)
            elif event.type == pygame.JOYBUTTONDOWN:
                slot = event.joy + 3
                if slot in gamepad_down:
                    gamepad_down[slot].add(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                slot = event.joy + 3
                if slot in gamepad_up:
                    gamepad_up[slot].add(event.button)
            elif event.type == pygame.JOYDEVICEADDED or event.type == pygame.JOYDEVICEREMOVED:
                self.refresh_joysticks()

        frame = InputFrame.empty()

        for slot, profile in KEYBOARD_BINDINGS.items():
            for cmd in build_keyboard_commands(slot, profile, keys, edge_down[slot], edge_up[slot]):
                frame.add(cmd)

        for slot in (3, 4):
            for cmd in self._build_gamepad_commands(slot, gamepad_down[slot], gamepad_up[slot]):
                frame.add(cmd)

        return frame

    def _build_gamepad_commands(self, slot: int, edge_down: set[int], edge_up: set[int]):
        joy = self._joysticks.get(slot)
        if joy is None:
            return []

        axis = joy.get_axis(GAMEPAD_BINDING.axis_move_x)
        move_axis = 1 if axis > 0.35 else -1 if axis < -0.35 else 0

        commands = [
            MoveCommand(player_slot=slot, axis=move_axis),
            FloatCommand(player_slot=slot, held=joy.get_button(GAMEPAD_BINDING.jump_button) == 1),
            GuardCommand(player_slot=slot, held=joy.get_button(GAMEPAD_BINDING.guard_button) == 1),
        ]
        if GAMEPAD_BINDING.jump_button in edge_down:
            commands.append(JumpCommand(player_slot=slot, pressed=True))
        if GAMEPAD_BINDING.inhale_button in edge_down:
            commands.append(InhaleStartCommand(player_slot=slot))
        if GAMEPAD_BINDING.inhale_button in edge_up:
            commands.append(InhaleReleaseCommand(player_slot=slot))
        if GAMEPAD_BINDING.ability_button in edge_down:
            commands.append(AbilityUseCommand(player_slot=slot, pressed=True))
        if GAMEPAD_BINDING.dodge_button in edge_down:
            commands.append(DodgeCommand(player_slot=slot, pressed=True))
        if GAMEPAD_BINDING.drop_button in edge_down:
            commands.append(DropAbilityCommand(player_slot=slot, pressed=True))
        return commands


def build_keyboard_commands(
    slot: int,
    profile: KeyboardProfile,
    keys: pygame.key.ScancodeWrapper,
    edge_down: set[int],
    edge_up: set[int],
) -> list[object]:
    move_axis = int(bool(keys[profile.move_right])) - int(bool(keys[profile.move_left]))
    commands: list[object] = [
        MoveCommand(player_slot=slot, axis=move_axis),
        FloatCommand(player_slot=slot, held=bool(keys[profile.jump])),
        GuardCommand(player_slot=slot, held=bool(keys[profile.guard])),
    ]
    if profile.jump in edge_down:
        commands.append(JumpCommand(player_slot=slot, pressed=True))
    if profile.inhale in edge_down:
        commands.append(InhaleStartCommand(player_slot=slot))
    if profile.inhale in edge_up:
        commands.append(InhaleReleaseCommand(player_slot=slot))
    if profile.ability in edge_down:
        commands.append(AbilityUseCommand(player_slot=slot, pressed=True))
    if profile.dodge in edge_down:
        commands.append(DodgeCommand(player_slot=slot, pressed=True))
    if profile.drop_ability in edge_down:
        commands.append(DropAbilityCommand(player_slot=slot, pressed=True))
    return commands


def _profile_keys(profile: KeyboardProfile) -> set[int]:
    return {
        profile.move_left,
        profile.move_right,
        profile.jump,
        profile.inhale,
        profile.ability,
        profile.guard,
        profile.dodge,
        profile.drop_ability,
    }
