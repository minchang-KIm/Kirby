from __future__ import annotations

from kirby_clone.input.bindings import KEYBOARD_BINDINGS
from kirby_clone.input.commands import (
    AbilityUseCommand,
    InhaleStartCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)
from kirby_clone.input.devices import build_keyboard_commands


class FakeKeys:
    def __init__(self, pressed: set[int]) -> None:
        self.pressed = pressed

    def __getitem__(self, key: int) -> int:
        return 1 if key in self.pressed else 0


def test_keyboard_command_mapping() -> None:
    profile = KEYBOARD_BINDINGS[1]
    keys = FakeKeys({profile.move_right, profile.jump})
    commands = build_keyboard_commands(
        slot=1,
        profile=profile,
        keys=keys,
        edge_down={profile.jump, profile.inhale, profile.ability},
        edge_up=set(),
    )
    assert any(isinstance(cmd, MoveCommand) and cmd.axis == 1 for cmd in commands)
    assert any(isinstance(cmd, JumpCommand) for cmd in commands)
    assert any(isinstance(cmd, InhaleStartCommand) for cmd in commands)
    assert any(isinstance(cmd, AbilityUseCommand) for cmd in commands)


def test_continuous_only_keeps_axis_like_commands() -> None:
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
    assert all(cmd.__class__.__name__ in {"MoveCommand", "FloatCommand", "GuardCommand"} for cmd in kept)
