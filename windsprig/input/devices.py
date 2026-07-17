"""Collect both legacy fixed slots into deterministic phased commands."""

from __future__ import annotations

from collections.abc import Sequence

import pygame

from .bindings import GAMEPAD_BINDING, KEYBOARD_BINDINGS, KeyboardProfile
from .commands import (
    AbilityUseCommand,
    DodgeCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    GatherConfirmCommand,
    GuardCommand,
    HoverCommand,
    InputCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)


class InputDeviceMux:
    """Collects keyboard(2P) + gamepad(2P) into device-agnostic commands."""

    def __init__(self) -> None:
        self._joysticks: dict[int, pygame.joystick.JoystickType] = {}
        self._instance_to_slot: dict[int, int] = {}
        self.refresh_joysticks()

    def refresh_joysticks(self) -> None:
        pygame.joystick.init()
        self._joysticks = {}
        self._instance_to_slot = {}
        for index in range(min(2, pygame.joystick.get_count())):
            joy = pygame.joystick.Joystick(index)
            joy.init()
            slot = index + 3
            self._joysticks[slot] = joy
            self._instance_to_slot[joy.get_instance_id()] = slot

    def collect_frame(
        self,
        events: Sequence[pygame.event.Event],
        keys: pygame.key.ScancodeWrapper,
    ) -> InputFrame:
        edge_down: dict[int, set[int]] = {1: set(), 2: set()}
        edge_up: dict[int, set[int]] = {1: set(), 2: set()}
        gamepad_down: dict[int, set[int]] = {3: set(), 4: set()}
        gamepad_up: dict[int, set[int]] = {3: set(), 4: set()}

        for event in events:
            if event.type == pygame.KEYDOWN and not _is_repeat(event):
                for slot, profile in KEYBOARD_BINDINGS.items():
                    if event.key in _profile_keys(profile):
                        edge_down[slot].add(event.key)
            elif event.type == pygame.KEYUP:
                for slot, profile in KEYBOARD_BINDINGS.items():
                    if event.key in _profile_keys(profile):
                        edge_up[slot].add(event.key)
            elif event.type == pygame.JOYBUTTONDOWN:
                gamepad_slot = self._instance_to_slot.get(event.instance_id)
                if gamepad_slot is not None:
                    gamepad_down[gamepad_slot].add(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                gamepad_slot = self._instance_to_slot.get(event.instance_id)
                if gamepad_slot is not None:
                    gamepad_up[gamepad_slot].add(event.button)
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

    def _build_gamepad_commands(
        self,
        slot: int,
        edge_down: set[int],
        edge_up: set[int],
    ) -> list[InputCommand]:
        joy = self._joysticks.get(slot)
        if joy is None:
            return []

        axis = joy.get_axis(GAMEPAD_BINDING.axis_move_x)
        move_axis = 1 if axis > 0.35 else -1 if axis < -0.35 else 0

        commands: list[InputCommand] = [
            MoveCommand(player_slot=slot, axis=move_axis),
            HoverCommand(player_slot=slot, held=joy.get_button(GAMEPAD_BINDING.jump_button) == 1),
            GuardCommand(player_slot=slot, held=joy.get_button(GAMEPAD_BINDING.guard_button) == 1),
            AbilityUseCommand(
                player_slot=slot,
                held=joy.get_button(GAMEPAD_BINDING.ability_button) == 1,
            ),
        ]
        if GAMEPAD_BINDING.jump_button in edge_down:
            commands.append(JumpCommand(player_slot=slot, pressed=True))
        if GAMEPAD_BINDING.draw_button in edge_down:
            commands.append(DrawStartCommand(player_slot=slot))
        if GAMEPAD_BINDING.draw_button in edge_up:
            commands.append(DrawReleaseCommand(player_slot=slot))
        if GAMEPAD_BINDING.ability_button in edge_down:
            commands.append(AbilityUseCommand(player_slot=slot, pressed=True))
            # The same explicit action edge lets the goal system interpret a
            # leader confirmation without teaching devices about stage state.
            commands.append(GatherConfirmCommand(player_slot=slot, pressed=True))
        if GAMEPAD_BINDING.ability_button in edge_up:
            commands.append(AbilityUseCommand(player_slot=slot, released=True))
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
) -> list[InputCommand]:
    move_axis = int(bool(keys[profile.move_right])) - int(bool(keys[profile.move_left]))
    commands: list[InputCommand] = [
        MoveCommand(player_slot=slot, axis=move_axis),
        HoverCommand(player_slot=slot, held=bool(keys[profile.jump])),
        GuardCommand(player_slot=slot, held=bool(keys[profile.guard])),
        AbilityUseCommand(player_slot=slot, held=bool(keys[profile.ability])),
    ]
    if profile.jump in edge_down:
        commands.append(JumpCommand(player_slot=slot, pressed=True))
    if profile.draw in edge_down:
        commands.append(DrawStartCommand(player_slot=slot))
    if profile.draw in edge_up:
        commands.append(DrawReleaseCommand(player_slot=slot))
    if profile.ability in edge_down:
        commands.append(AbilityUseCommand(player_slot=slot, pressed=True))
        commands.append(GatherConfirmCommand(player_slot=slot, pressed=True))
    if profile.ability in edge_up:
        commands.append(AbilityUseCommand(player_slot=slot, released=True))
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
        profile.draw,
        profile.ability,
        profile.guard,
        profile.dodge,
        profile.drop_ability,
    }


def _is_repeat(event: pygame.event.Event) -> bool:
    return bool(getattr(event, "repeat", False))
