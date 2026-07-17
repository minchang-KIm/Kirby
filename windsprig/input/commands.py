"""Immutable device-agnostic input values crossing the fixed-step boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CancelOrigin = Literal["cancel", "ability_button"]


@dataclass(frozen=True, slots=True)
class InputCommand:
    player_slot: int


@dataclass(frozen=True, slots=True)
class MoveCommand(InputCommand):
    axis: int


@dataclass(frozen=True, slots=True)
class JumpCommand(InputCommand):
    pressed: bool


@dataclass(frozen=True, slots=True)
class HoverCommand(InputCommand):
    held: bool


@dataclass(frozen=True, slots=True)
class DrawStartCommand(InputCommand):
    pass


@dataclass(frozen=True, slots=True)
class DrawReleaseCommand(InputCommand):
    pass


@dataclass(frozen=True, slots=True)
class AbilityUseCommand(InputCommand):
    pressed: bool = False
    held: bool = False
    released: bool = False


@dataclass(frozen=True, slots=True)
class GuardCommand(InputCommand):
    held: bool


@dataclass(frozen=True, slots=True)
class DodgeCommand(InputCommand):
    pressed: bool


@dataclass(frozen=True, slots=True)
class DropAbilityCommand(InputCommand):
    pressed: bool


@dataclass(frozen=True, slots=True)
class GatherConfirmCommand(InputCommand):
    """Request a leader-owned team gather on one gameplay action edge."""

    pressed: bool


@dataclass(frozen=True, slots=True)
class NavigateCommand(InputCommand):
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ConfirmCommand(InputCommand):
    pass


@dataclass(frozen=True, slots=True)
class CancelCommand(InputCommand):
    origin: CancelOrigin = "cancel"


@dataclass(frozen=True, slots=True)
class PauseCommand(InputCommand):
    pass


@dataclass(frozen=True, slots=True)
class ProbeCompleteCommand(InputCommand):
    """Request the opt-in browser probe's goal-position diagnostic."""

    pass


@dataclass(slots=True)
class InputFrame:
    commands_by_slot: dict[int, list[InputCommand]] = field(default_factory=dict)

    def add(self, command: InputCommand) -> None:
        self.commands_by_slot.setdefault(command.player_slot, []).append(command)

    def commands_for(self, player_slot: int) -> list[InputCommand]:
        return self.commands_by_slot.get(player_slot, [])

    def continuous_only(self) -> InputFrame:
        filtered: dict[int, list[InputCommand]] = {}
        for slot, commands in self.commands_by_slot.items():
            continuous: list[InputCommand] = [
                command for command in commands if isinstance(command, (MoveCommand, HoverCommand, GuardCommand))
            ]
            ability_commands = [command for command in commands if isinstance(command, AbilityUseCommand)]
            if ability_commands:
                pure_samples = [
                    command
                    for command in ability_commands
                    if not command.pressed and not command.released
                ]
                sample = pure_samples[-1] if pure_samples else ability_commands[-1]
                continuous.append(AbilityUseCommand(player_slot=slot, held=sample.held))
            filtered[slot] = continuous
        return InputFrame(commands_by_slot=filtered)

    @staticmethod
    def empty() -> InputFrame:
        return InputFrame()
