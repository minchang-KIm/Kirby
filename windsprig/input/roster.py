from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

DeviceKind = Literal["keyboard", "gamepad"]
SLOT_VISUALS: dict[int, tuple[str, str]] = {
    1: ("mint", "leaf"),
    2: ("gold", "sun"),
    3: ("violet", "moon"),
    4: ("cyan", "gale"),
}


@dataclass(frozen=True, slots=True)
class DeviceRef:
    kind: DeviceKind
    uid: str
    label: str


@dataclass(frozen=True, slots=True)
class ActivePlayer:
    slot: int
    device: DeviceRef
    color_token: str
    icon_token: str
    is_leader: bool


class ActiveRoster:
    def __init__(self, max_players: int = 4) -> None:
        if not 1 <= max_players <= 4:
            raise ValueError("max_players must be between 1 and 4")
        self.max_players = max_players
        self._players: dict[int, ActivePlayer] = {}

    @property
    def players(self) -> tuple[ActivePlayer, ...]:
        return tuple(self._players[slot] for slot in sorted(self._players))

    @property
    def leader_slot(self) -> int | None:
        return next((player.slot for player in self.players if player.is_leader), None)

    def join(self, device: DeviceRef) -> ActivePlayer:
        current = self.player_for_device(device)
        if current is not None:
            return current
        free_slot = next(
            (slot for slot in range(1, self.max_players + 1) if slot not in self._players),
            None,
        )
        if free_slot is None:
            raise ValueError("active roster is full")
        color_token, icon_token = SLOT_VISUALS[free_slot]
        player = ActivePlayer(
            slot=free_slot,
            device=device,
            color_token=color_token,
            icon_token=icon_token,
            is_leader=not self._players,
        )
        self._players[free_slot] = player
        return player

    def leave(self, slot: int) -> ActivePlayer | None:
        removed = self._players.pop(slot, None)
        if removed is not None and removed.is_leader and self._players:
            promoted_slot = min(self._players)
            self._players[promoted_slot] = replace(self._players[promoted_slot], is_leader=True)
        return removed

    def reassign(self, slot: int, device: DeviceRef) -> ActivePlayer:
        if self.player_for_device(device) is not None:
            raise ValueError("device is already assigned")
        player = self._players[slot]
        reassigned = replace(player, device=device)
        self._players[slot] = reassigned
        return reassigned

    def player_for_device(self, device: DeviceRef) -> ActivePlayer | None:
        return next(
            (
                player
                for player in self.players
                if player.device.kind == device.kind and player.device.uid == device.uid
            ),
            None,
        )

    def is_active(self, slot: int) -> bool:
        return slot in self._players
