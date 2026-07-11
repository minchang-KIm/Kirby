from __future__ import annotations

from windsprig.input.commands import GuardCommand, HoverCommand, InputCommand, InputFrame, MoveCommand

HELD_TYPES = (MoveCommand, HoverCommand, GuardCommand)


class InputQueue:
    def __init__(self) -> None:
        self._edges: dict[int, list[InputCommand]] = {}
        self._held: dict[int, dict[type[InputCommand], InputCommand]] = {}

    def push(self, frame: InputFrame) -> None:
        for slot, commands in frame.commands_by_slot.items():
            for command in commands:
                if isinstance(command, HELD_TYPES):
                    self._held.setdefault(slot, {})[type(command)] = command
                else:
                    self._edges.setdefault(slot, []).append(command)

    def consume_step(self) -> InputFrame:
        output = InputFrame.empty()
        for slot in sorted(set(self._held) | set(self._edges)):
            held_by_type = self._held.get(slot, {})
            held = [held_by_type[command_type] for command_type in HELD_TYPES if command_type in held_by_type]
            output.commands_by_slot[slot] = held + self._edges.get(slot, [])
        self._edges = {}
        return output

    def clear_held(self) -> None:
        self._held = {}
        self._edges = {}
