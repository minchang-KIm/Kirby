from __future__ import annotations

import pytest

from windsprig.input.roster import ActiveRoster, DeviceRef


def keyboard(uid: str, label: str | None = None) -> DeviceRef:
    return DeviceRef(kind="keyboard", uid=uid, label=label or uid)


def gamepad(uid: str) -> DeviceRef:
    return DeviceRef(kind="gamepad", uid=uid, label=uid)


def test_join_uses_lowest_slot_and_first_player_is_leader() -> None:
    roster = ActiveRoster(max_players=4)

    first = roster.join(keyboard("keyboard-wasd"))
    second = roster.join(keyboard("keyboard-arrows"))

    assert (first.slot, first.is_leader) == (1, True)
    assert (second.slot, second.is_leader) == (2, False)
    assert roster.players == (first, second)
    assert roster.leader_slot == 1


def test_duplicate_join_uses_device_identity_and_is_idempotent_when_full() -> None:
    roster = ActiveRoster(max_players=1)
    first = roster.join(keyboard("keyboard-wasd", "Original label"))

    duplicate = roster.join(keyboard("keyboard-wasd", "Updated label"))

    assert duplicate == first
    assert roster.players == (first,)
    with pytest.raises(ValueError, match="active roster is full"):
        roster.join(gamepad("gamepad-7"))


def test_leaving_leader_promotes_lowest_remaining_slot() -> None:
    roster = ActiveRoster(max_players=4)
    roster.join(keyboard("keyboard-wasd"))
    second = roster.join(keyboard("keyboard-arrows"))
    third = roster.join(gamepad("gamepad-7"))

    removed = roster.leave(1)

    assert removed is not None and removed.slot == 1
    assert roster.leader_slot == second.slot
    assert [(player.slot, player.is_leader) for player in roster.players] == [
        (second.slot, True),
        (third.slot, False),
    ]


def test_leaving_nonleader_keeps_leader_and_reuses_lowest_slot_visuals() -> None:
    roster = ActiveRoster(max_players=4)
    leader = roster.join(keyboard("keyboard-wasd"))
    roster.join(keyboard("keyboard-arrows"))

    removed = roster.leave(2)
    replacement = roster.join(gamepad("gamepad-8"))

    assert removed is not None and removed.slot == 2
    assert roster.leader_slot == leader.slot
    assert (replacement.slot, replacement.color_token, replacement.icon_token) == (2, "gold", "sun")
    assert roster.leave(4) is None


def test_reassign_keeps_slot_visual_and_leader_identity() -> None:
    roster = ActiveRoster(max_players=4)
    player = roster.join(keyboard("keyboard-wasd"))
    pad = DeviceRef(kind="gamepad", uid="gamepad-7", label="Standard Gamepad")

    reassigned = roster.reassign(player.slot, pad)

    assert reassigned.slot == 1
    assert reassigned.color_token == "mint"
    assert reassigned.icon_token == "leaf"
    assert reassigned.is_leader is True
    assert roster.player_for_device(pad) == reassigned
    assert roster.player_for_device(keyboard("keyboard-wasd")) is None


def test_reassign_rejects_an_assigned_device_without_mutating_roster() -> None:
    roster = ActiveRoster(max_players=4)
    first = roster.join(keyboard("keyboard-wasd"))
    second = roster.join(keyboard("keyboard-arrows"))

    with pytest.raises(ValueError, match="device is already assigned"):
        roster.reassign(second.slot, keyboard("keyboard-wasd", "Same identity"))

    assert roster.players == (first, second)
    with pytest.raises(KeyError):
        roster.reassign(4, gamepad("gamepad-9"))


@pytest.mark.parametrize("max_players", [0, 5])
def test_roster_rejects_player_limits_outside_local_range(max_players: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 4"):
        ActiveRoster(max_players=max_players)


def test_device_lookup_distinguishes_kind_and_uid_but_not_label() -> None:
    roster = ActiveRoster()
    player = roster.join(keyboard("shared-id", "Keyboard label"))

    assert roster.player_for_device(keyboard("shared-id", "New label")) == player
    assert roster.player_for_device(gamepad("shared-id")) is None
    assert roster.is_active(player.slot) is True
    assert roster.is_active(4) is False
