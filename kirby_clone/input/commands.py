from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InputCommand:
    player_slot: int


@dataclass(frozen=True)
class MoveCommand(InputCommand):
    axis: int


@dataclass(frozen=True)
class JumpCommand(InputCommand):
    pressed: bool


@dataclass(frozen=True)
class FloatCommand(InputCommand):
    held: bool


@dataclass(frozen=True)
class InhaleStartCommand(InputCommand):
    pass


@dataclass(frozen=True)
class InhaleReleaseCommand(InputCommand):
    pass


@dataclass(frozen=True)
class AbilityUseCommand(InputCommand):
    pressed: bool


@dataclass(frozen=True)
class GuardCommand(InputCommand):
    held: bool


@dataclass(frozen=True)
class DodgeCommand(InputCommand):
    pressed: bool


@dataclass(frozen=True)
class DropAbilityCommand(InputCommand):
    pressed: bool


@dataclass
class InputFrame:
    commands_by_slot: dict[int, list[InputCommand]] = field(default_factory=dict)

    def add(self, command: InputCommand) -> None:
        self.commands_by_slot.setdefault(command.player_slot, []).append(command)

    def commands_for(self, player_slot: int) -> list[InputCommand]:
        return self.commands_by_slot.get(player_slot, [])

    def continuous_only(self) -> "InputFrame":
        kept_types = {"MoveCommand", "FloatCommand", "GuardCommand"}
        filtered: dict[int, list[InputCommand]] = {}
        for slot, commands in self.commands_by_slot.items():
            filtered[slot] = [cmd for cmd in commands if cmd.__class__.__name__ in kept_types]
        return InputFrame(commands_by_slot=filtered)

    @staticmethod
    def empty() -> "InputFrame":
        return InputFrame()
