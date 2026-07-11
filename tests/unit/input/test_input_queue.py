from __future__ import annotations

from windsprig.input.commands import (
    DodgeCommand,
    GuardCommand,
    HoverCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)
from windsprig.input.queue import InputQueue
from windsprig.input.roster import ActiveRoster, DeviceRef


def test_edge_survives_later_held_only_frame_for_same_active_slot_and_is_consumed_once() -> None:
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                1: [MoveCommand(player_slot=1, axis=1), JumpCommand(player_slot=1, pressed=True)]
            }
        )
    )
    queue.push(InputFrame(commands_by_slot={1: [MoveCommand(player_slot=1, axis=1)]}))

    first_step = queue.consume_step().commands_for(1)
    second_step = queue.consume_step().commands_for(1)

    assert sum(isinstance(command, JumpCommand) for command in first_step) == 1
    assert not any(isinstance(command, JumpCommand) for command in second_step)
    assert any(isinstance(command, MoveCommand) and command.axis == 1 for command in first_step)
    assert any(isinstance(command, MoveCommand) and command.axis == 1 for command in second_step)


def test_omitted_slot_clears_old_owner_held_and_pending_edges_before_reuse() -> None:
    roster = ActiveRoster()
    old_owner = roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                old_owner.slot: [
                    MoveCommand(player_slot=old_owner.slot, axis=1),
                    JumpCommand(player_slot=old_owner.slot, pressed=True),
                ]
            }
        )
    )

    roster.leave(old_owner.slot)
    queue.push(InputFrame.empty())  # The join-suppressed render frame omits the vacated slot.
    new_owner = roster.join(DeviceRef("gamepad", "gamepad-7", "New Controller"))

    assert new_owner.slot == old_owner.slot
    assert queue.consume_step().commands_for(new_owner.slot) == []


def test_omitted_slot_cleanup_preserves_state_for_present_empty_slot() -> None:
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                1: [
                    MoveCommand(player_slot=1, axis=1),
                    JumpCommand(player_slot=1, pressed=True),
                ],
                2: [
                    MoveCommand(player_slot=2, axis=-1),
                    DodgeCommand(player_slot=2, pressed=True),
                ],
            }
        )
    )

    queue.push(InputFrame(commands_by_slot={2: []}))
    first_step = queue.consume_step()
    second_step = queue.consume_step()

    assert first_step.commands_for(1) == []
    assert second_step.commands_for(1) == []
    assert first_step.commands_for(2) == [
        MoveCommand(player_slot=2, axis=-1),
        DodgeCommand(player_slot=2, pressed=True),
    ]
    assert second_step.commands_for(2) == [MoveCommand(player_slot=2, axis=-1)]


def test_clear_slot_drops_reassigned_owner_state_without_disturbing_other_slots() -> None:
    roster = ActiveRoster()
    reassigned_player = roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    other_player = roster.join(DeviceRef("keyboard", "keyboard-arrows", "Keyboard Arrows"))
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                reassigned_player.slot: [
                    MoveCommand(player_slot=reassigned_player.slot, axis=1),
                    JumpCommand(player_slot=reassigned_player.slot, pressed=True),
                ],
                other_player.slot: [
                    MoveCommand(player_slot=other_player.slot, axis=-1),
                    DodgeCommand(player_slot=other_player.slot, pressed=True),
                ],
            }
        )
    )

    roster.reassign(
        reassigned_player.slot,
        DeviceRef("gamepad", "gamepad-8", "Replacement Controller"),
    )
    queue.clear_slot(reassigned_player.slot)
    frame = queue.consume_step()

    assert frame.commands_for(reassigned_player.slot) == []
    assert frame.commands_for(other_player.slot) == [
        MoveCommand(player_slot=other_player.slot, axis=-1),
        DodgeCommand(player_slot=other_player.slot, pressed=True),
    ]


def test_latest_released_held_values_replace_pressed_values_and_persist() -> None:
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                1: [
                    MoveCommand(player_slot=1, axis=1),
                    HoverCommand(player_slot=1, held=True),
                    GuardCommand(player_slot=1, held=True),
                ]
            }
        )
    )
    queue.push(
        InputFrame(
            commands_by_slot={
                1: [
                    GuardCommand(player_slot=1, held=False),
                    MoveCommand(player_slot=1, axis=0),
                    HoverCommand(player_slot=1, held=False),
                ]
            }
        )
    )

    expected = [
        MoveCommand(player_slot=1, axis=0),
        HoverCommand(player_slot=1, held=False),
        GuardCommand(player_slot=1, held=False),
    ]
    assert queue.consume_step().commands_for(1) == expected
    assert queue.consume_step().commands_for(1) == expected


def test_consume_orders_slots_held_types_and_edges_deterministically() -> None:
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                2: [JumpCommand(player_slot=2, pressed=True)],
                1: [
                    GuardCommand(player_slot=1, held=True),
                    DodgeCommand(player_slot=1, pressed=True),
                    MoveCommand(player_slot=1, axis=-1),
                    HoverCommand(player_slot=1, held=True),
                    JumpCommand(player_slot=1, pressed=True),
                ],
            }
        )
    )

    frame = queue.consume_step()

    assert list(frame.commands_by_slot) == [1, 2]
    assert [type(command) for command in frame.commands_for(1)] == [
        MoveCommand,
        HoverCommand,
        GuardCommand,
        DodgeCommand,
        JumpCommand,
    ]
    assert frame.commands_for(2) == [JumpCommand(player_slot=2, pressed=True)]


def test_focus_loss_clears_held_state_and_pending_edges() -> None:
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                1: [
                    GuardCommand(player_slot=1, held=True),
                    JumpCommand(player_slot=1, pressed=True),
                ]
            }
        )
    )

    queue.clear_held()

    assert queue.consume_step().commands_for(1) == []
