from __future__ import annotations

import windsprig.input as input_api
from windsprig.input.bindings import KEYBOARD_BINDINGS
from windsprig.input.commands import (
    AbilityUseCommand,
    DrawStartCommand,
    GatherConfirmCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)
from windsprig.input.devices import build_keyboard_commands


class FakeKeys:
    def __init__(self, pressed: set[int]) -> None:
        self.pressed = pressed

    def __getitem__(self, key: int) -> int:
        return 1 if key in self.pressed else 0


def test_gather_confirmation_is_available_from_the_public_input_api() -> None:
    assert input_api.GatherConfirmCommand is GatherConfirmCommand


def test_keyboard_command_mapping() -> None:
    profile = KEYBOARD_BINDINGS[1]
    keys = FakeKeys({profile.move_right, profile.jump})
    commands = build_keyboard_commands(
        slot=1,
        profile=profile,
        keys=keys,
        edge_down={profile.jump, profile.draw, profile.ability},
        edge_up=set(),
    )
    assert any(isinstance(cmd, MoveCommand) and cmd.axis == 1 for cmd in commands)
    assert any(isinstance(cmd, JumpCommand) for cmd in commands)
    assert any(isinstance(cmd, DrawStartCommand) for cmd in commands)
    assert any(isinstance(cmd, AbilityUseCommand) for cmd in commands)


def test_ability_command_defaults_and_positional_press_compatibility() -> None:
    assert AbilityUseCommand(1) == AbilityUseCommand(1, pressed=False, held=False, released=False)
    assert AbilityUseCommand(1, True) == AbilityUseCommand(1, pressed=True, held=False, released=False)


def test_continuous_only_keeps_held_ability_without_replaying_edges() -> None:
    profile = KEYBOARD_BINDINGS[1]
    keys = FakeKeys({profile.move_left, profile.guard})
    commands = build_keyboard_commands(
        slot=1,
        profile=profile,
        keys=keys,
        edge_down={profile.jump, profile.ability},
        edge_up=set(),
    )
    frame = InputFrame(commands_by_slot={1: commands})
    filtered = frame.continuous_only()
    kept = filtered.commands_for(1)
    assert any(isinstance(cmd, MoveCommand) for cmd in kept)
    ability = next(cmd for cmd in kept if isinstance(cmd, AbilityUseCommand))
    assert ability == AbilityUseCommand(player_slot=1, held=False)
    assert all(
        cmd.__class__.__name__ in {"MoveCommand", "HoverCommand", "GuardCommand", "AbilityUseCommand"}
        for cmd in kept
    )

    combined = InputFrame(
        commands_by_slot={1: [AbilityUseCommand(1, pressed=True, held=True, released=True)]}
    ).continuous_only()
    assert combined.commands_for(1) == [AbilityUseCommand(1, held=True)]
