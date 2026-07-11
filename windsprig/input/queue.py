from __future__ import annotations

from windsprig.input.commands import GuardCommand, HoverCommand, InputCommand, InputFrame, MoveCommand

HELD_TYPES = (MoveCommand, HoverCommand, GuardCommand)


class InputQueue:
    """Bridge render-frame input sampling to deterministic fixed simulation steps."""

    def __init__(self) -> None:
        # Edges must outlive render frames that produce no fixed simulation step.
        self._edges: dict[int, list[InputCommand]] = {}
        self._held: dict[int, dict[type[InputCommand], InputCommand]] = {}

    def push(self, frame: InputFrame) -> None:
        """Merge a render-frame sample, using its slot keys as the active-slot snapshot."""
        active_slots = set(frame.commands_by_slot)
        omitted_slots = (set(self._held) | set(self._edges)) - active_slots
        # Slots are reusable identities; an omitted slot cannot retain its prior owner's input.
        for slot in omitted_slots:
            self.clear_slot(slot)

        for slot, commands in frame.commands_by_slot.items():
            for command in commands:
                if isinstance(command, HELD_TYPES):
                    self._held.setdefault(slot, {})[type(command)] = command
                else:
                    self._edges.setdefault(slot, []).append(command)

    def consume_step(self) -> InputFrame:
        """Return latest held values plus pending edges, draining each edge exactly once."""
        output = InputFrame.empty()
        for slot in sorted(set(self._held) | set(self._edges)):
            held_by_type = self._held.get(slot, {})
            held = [held_by_type[command_type] for command_type in HELD_TYPES if command_type in held_by_type]
            output.commands_by_slot[slot] = held + self._edges.get(slot, [])
        self._edges = {}
        return output

    def clear_slot(self, slot: int) -> None:
        """Discard all buffered input before ownership of one slot changes."""
        self._held.pop(slot, None)
        self._edges.pop(slot, None)

    def clear_held(self) -> None:
        """Discard all buffered input after a global interruption such as focus loss."""
        self._held = {}
        self._edges = {}
