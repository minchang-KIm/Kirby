"""Device-mux behavior across both keyboard profiles and both gamepad slots."""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame
import pytest

from windsprig.input.bindings import GAMEPAD_BINDING, KEYBOARD_BINDINGS
from windsprig.input.commands import (
    AbilityUseCommand,
    DodgeCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    GatherConfirmCommand,
    GuardCommand,
    HoverCommand,
    JumpCommand,
    MoveCommand,
)
from windsprig.input.devices import InputDeviceMux, _profile_keys, build_keyboard_commands


class FakeKeys:
    def __init__(self, pressed: set[int]) -> None:
        self.pressed = pressed

    def __getitem__(self, key: int) -> int:
        return int(key in self.pressed)


@dataclass
class FakeJoystick:
    instance_id: int
    axis: float
    held_buttons: set[int] = field(default_factory=set)
    initialized: int = 0

    def init(self) -> None:
        self.initialized += 1

    def get_instance_id(self) -> int:
        return self.instance_id

    def get_axis(self, _axis: int) -> float:
        return self.axis

    def get_button(self, button: int) -> int:
        return int(button in self.held_buttons)


def install_fake_joysticks(
    monkeypatch: pytest.MonkeyPatch,
    joysticks: list[FakeJoystick],
) -> list[bool]:
    initialized: list[bool] = []
    monkeypatch.setattr(pygame.joystick, "init", lambda: initialized.append(True))
    monkeypatch.setattr(pygame.joystick, "get_count", lambda: len(joysticks))
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda index: joysticks[index])
    return initialized


def test_keyboard_builder_emits_every_edge_and_continuous_command() -> None:
    profile = KEYBOARD_BINDINGS[1]
    commands = build_keyboard_commands(
        slot=1,
        profile=profile,
        keys=FakeKeys({profile.move_left, profile.jump, profile.guard}),
        edge_down={
            profile.jump,
            profile.draw,
            profile.ability,
            profile.dodge,
            profile.drop_ability,
        },
        edge_up={profile.draw},
    )

    assert MoveCommand(player_slot=1, axis=-1) in commands
    assert HoverCommand(player_slot=1, held=True) in commands
    assert GuardCommand(player_slot=1, held=True) in commands
    assert JumpCommand(player_slot=1, pressed=True) in commands
    assert DrawStartCommand(player_slot=1) in commands
    assert DrawReleaseCommand(player_slot=1) in commands
    assert AbilityUseCommand(player_slot=1, pressed=True) in commands
    assert GatherConfirmCommand(player_slot=1, pressed=True) in commands
    assert AbilityUseCommand(player_slot=1, held=False) in commands
    assert DodgeCommand(player_slot=1, pressed=True) in commands
    assert DropAbilityCommand(player_slot=1, pressed=True) in commands
    assert _profile_keys(profile) == {
        profile.move_left,
        profile.move_right,
        profile.jump,
        profile.draw,
        profile.ability,
        profile.guard,
        profile.dodge,
        profile.drop_ability,
    }


@pytest.mark.parametrize(("axis", "expected"), [(0.8, 1), (-0.8, -1), (0.2, 0)])
def test_gamepad_axis_uses_a_dead_zone(
    monkeypatch: pytest.MonkeyPatch,
    axis: float,
    expected: int,
) -> None:
    joystick = FakeJoystick(instance_id=70, axis=axis)
    install_fake_joysticks(monkeypatch, [joystick])
    mux = InputDeviceMux()

    commands = mux._build_gamepad_commands(3, set(), set())

    assert MoveCommand(player_slot=3, axis=expected) in commands
    assert mux._build_gamepad_commands(4, set(), set()) == []


def test_gamepad_builder_emits_held_state_and_every_supported_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    joystick = FakeJoystick(
        instance_id=70,
        axis=0.0,
        held_buttons={
            GAMEPAD_BINDING.jump_button,
            GAMEPAD_BINDING.guard_button,
            GAMEPAD_BINDING.ability_button,
        },
    )
    install_fake_joysticks(monkeypatch, [joystick])
    mux = InputDeviceMux()
    edge_down = {
        GAMEPAD_BINDING.jump_button,
        GAMEPAD_BINDING.draw_button,
        GAMEPAD_BINDING.ability_button,
        GAMEPAD_BINDING.dodge_button,
        GAMEPAD_BINDING.drop_button,
    }

    commands = mux._build_gamepad_commands(
        3,
        edge_down,
        {GAMEPAD_BINDING.draw_button, GAMEPAD_BINDING.ability_button},
    )

    assert HoverCommand(player_slot=3, held=True) in commands
    assert GuardCommand(player_slot=3, held=True) in commands
    assert JumpCommand(player_slot=3, pressed=True) in commands
    assert DrawStartCommand(player_slot=3) in commands
    assert DrawReleaseCommand(player_slot=3) in commands
    assert AbilityUseCommand(player_slot=3, pressed=True) in commands
    assert GatherConfirmCommand(player_slot=3, pressed=True) in commands
    assert AbilityUseCommand(player_slot=3, held=True) in commands
    assert AbilityUseCommand(player_slot=3, released=True) in commands
    assert DodgeCommand(player_slot=3, pressed=True) in commands
    assert DropAbilityCommand(player_slot=3, pressed=True) in commands


def test_mux_refreshes_two_gamepads_and_routes_keyboard_and_gamepad_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    joysticks = [
        FakeJoystick(instance_id=70, axis=0.8),
        FakeJoystick(instance_id=71, axis=-0.8),
        FakeJoystick(instance_id=72, axis=0.0),
    ]
    initialized = install_fake_joysticks(monkeypatch, joysticks)
    mux = InputDeviceMux()
    first = KEYBOARD_BINDINGS[1]
    second = KEYBOARD_BINDINGS[2]
    events = [
        pygame.event.Event(pygame.KEYDOWN, key=first.jump),
        pygame.event.Event(pygame.KEYDOWN, key=first.draw),
        pygame.event.Event(pygame.KEYUP, key=first.draw),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UNKNOWN),
        pygame.event.Event(
            pygame.JOYBUTTONDOWN,
            instance_id=70,
            button=GAMEPAD_BINDING.ability_button,
        ),
        pygame.event.Event(
            pygame.JOYBUTTONUP,
            instance_id=70,
            button=GAMEPAD_BINDING.draw_button,
        ),
        pygame.event.Event(pygame.JOYBUTTONDOWN, instance_id=999, button=0),
        pygame.event.Event(pygame.JOYBUTTONUP, instance_id=999, button=0),
        pygame.event.Event(pygame.JOYDEVICEADDED),
        pygame.event.Event(pygame.JOYDEVICEREMOVED),
    ]

    frame = mux.collect_frame(
        events,
        FakeKeys({first.move_right, second.move_left}),
    )

    assert len(mux._joysticks) == 2
    assert mux._instance_to_slot == {70: 3, 71: 4}
    assert all(joystick.initialized == 3 for joystick in joysticks[:2])
    assert joysticks[2].initialized == 0
    assert initialized == [True, True, True]
    assert MoveCommand(player_slot=1, axis=1) in frame.commands_for(1)
    assert JumpCommand(player_slot=1, pressed=True) in frame.commands_for(1)
    assert DrawStartCommand(player_slot=1) in frame.commands_for(1)
    assert DrawReleaseCommand(player_slot=1) in frame.commands_for(1)
    assert MoveCommand(player_slot=2, axis=-1) in frame.commands_for(2)
    assert AbilityUseCommand(player_slot=3, pressed=True) in frame.commands_for(3)
    assert DrawReleaseCommand(player_slot=3) in frame.commands_for(3)
    assert MoveCommand(player_slot=4, axis=-1) in frame.commands_for(4)


def test_keyboard_repeat_does_not_create_a_second_ability_press(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_joysticks(monkeypatch, [])
    mux = InputDeviceMux()
    profile = KEYBOARD_BINDINGS[1]
    pressed = mux.collect_frame(
        [pygame.event.Event(pygame.KEYDOWN, key=profile.ability, repeat=False)],
        FakeKeys({profile.ability}),
    )
    repeated = mux.collect_frame(
        [pygame.event.Event(pygame.KEYDOWN, key=profile.ability, repeat=True)],
        FakeKeys({profile.ability}),
    )
    released = mux.collect_frame(
        [pygame.event.Event(pygame.KEYUP, key=profile.ability)],
        FakeKeys(set()),
    )

    assert [
        command for command in pressed.commands_for(1) if isinstance(command, AbilityUseCommand)
    ] == [
        AbilityUseCommand(1, held=True),
        AbilityUseCommand(1, pressed=True),
    ]
    assert [
        command for command in repeated.commands_for(1) if isinstance(command, AbilityUseCommand)
    ] == [AbilityUseCommand(1, held=True)]
    assert [
        command for command in released.commands_for(1) if isinstance(command, AbilityUseCommand)
    ] == [
        AbilityUseCommand(1, held=False),
        AbilityUseCommand(1, released=True),
    ]
