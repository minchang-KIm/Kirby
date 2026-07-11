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


def test_edge_survives_zero_step_frames_and_is_consumed_once() -> None:
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
