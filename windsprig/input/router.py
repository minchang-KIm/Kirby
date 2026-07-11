from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import pygame

from windsprig.input.bindings import GAMEPAD_BINDING, KEYBOARD_BINDINGS, KeyboardProfile
from windsprig.input.commands import (
    AbilityUseCommand,
    CancelCommand,
    ConfirmCommand,
    DodgeCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    GuardCommand,
    HoverCommand,
    InputCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
    NavigateCommand,
    PauseCommand,
)
from windsprig.input.roster import ActivePlayer, ActiveRoster, DeviceRef

KEYBOARD_WASD_DEVICE = DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD")
KEYBOARD_ARROWS_DEVICE = DeviceRef("keyboard", "keyboard-arrows", "Keyboard Arrows")


class KeyState(Protocol):
    """Minimal keyboard-state contract required for held sampling."""

    def __getitem__(self, key: int) -> int | bool: ...


class JoystickState(Protocol):
    """Joystick operations used by routing and hotplug identity management."""

    def get_axis(self, axis: int) -> float: ...

    def get_button(self, button: int) -> int | bool: ...

    def get_init(self) -> bool: ...

    def get_instance_id(self) -> int: ...

    def get_name(self) -> str: ...

    def init(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _KeyboardRoute:
    device: DeviceRef
    profile: KeyboardProfile
    join_key: int
    cancel_key: int


KEYBOARD_ROUTES = (
    _KeyboardRoute(
        device=KEYBOARD_WASD_DEVICE,
        profile=KEYBOARD_BINDINGS[1],
        join_key=pygame.K_RETURN,
        cancel_key=pygame.K_ESCAPE,
    ),
    _KeyboardRoute(
        device=KEYBOARD_ARROWS_DEVICE,
        profile=KEYBOARD_BINDINGS[2],
        join_key=pygame.K_KP_ENTER,
        cancel_key=pygame.K_ESCAPE,
    ),
)


@dataclass(frozen=True, slots=True)
class RoutedInput:
    """One render frame of commands plus roster and disconnection requests."""

    frame: InputFrame
    join_requests: tuple[DeviceRef, ...] = ()
    disconnected_devices: tuple[DeviceRef, ...] = ()


class InputRouter:
    """Translate pygame input into roster-scoped gameplay and menu commands."""

    def __init__(self) -> None:
        self._joysticks: dict[int, JoystickState] = {}
        self._axis_menu_state: dict[tuple[int, int], int] = {}
        self._hat_menu_state: dict[tuple[int, int], tuple[int, int]] = {}
        self.refresh_joysticks()

    def refresh_joysticks(self) -> None:
        """Rebuild connected gamepad state keyed by stable pygame instance ID."""
        try:
            pygame.joystick.init()
            connected: dict[int, JoystickState] = {}
            for device_index in range(pygame.joystick.get_count()):
                joystick = pygame.joystick.Joystick(device_index)
                if not joystick.get_init():
                    joystick.init()
                connected[joystick.get_instance_id()] = joystick
            self._joysticks = connected
        except pygame.error:
            self._joysticks = {}

    def collect(
        self,
        events: Sequence[pygame.event.Event],
        keys: KeyState,
        roster: ActiveRoster,
    ) -> RoutedInput:
        """Collect one render frame without mutating the active roster."""
        event_list = tuple(events)
        self._register_added_gamepads(event_list)

        join_requests = self._join_requests(event_list, roster)
        # Remove first so a disconnected device's last held sample cannot enter the queue.
        disconnected = self._removed_gamepads(event_list, roster)
        disconnected_identities = {(device.kind, device.uid) for device in disconnected}
        join_requests = [
            device
            for device in join_requests
            if (device.kind, device.uid) not in disconnected_identities
        ]
        # Joining input is roster intent, not a gameplay/menu action in the same frame.
        suppressed = {(device.kind, device.uid) for device in join_requests}
        frame = InputFrame.empty()

        for player in roster.players:
            if (player.device.kind, player.device.uid) in suppressed:
                continue
            if player.device.kind == "keyboard":
                route = _keyboard_route(player.device.uid)
                if route is None:
                    continue
                for command in _keyboard_held_commands(player.slot, route.profile, keys):
                    frame.add(command)
                for event in event_list:
                    for command in _keyboard_event_commands(player.slot, route, event):
                        frame.add(command)
            else:
                for command in self._gamepad_held_commands(player):
                    frame.add(command)
                for event in event_list:
                    for command in self._gamepad_event_commands(player, event):
                        frame.add(command)

        return RoutedInput(
            frame=frame,
            join_requests=tuple(join_requests),
            disconnected_devices=tuple(disconnected),
        )

    def _register_added_gamepads(self, events: Sequence[pygame.event.Event]) -> None:
        for event in events:
            if event.type != pygame.JOYDEVICEADDED:
                continue
            device_index = getattr(event, "device_index", None)
            if not isinstance(device_index, int):
                continue
            try:
                joystick = pygame.joystick.Joystick(device_index)
                if not joystick.get_init():
                    joystick.init()
                self._joysticks[joystick.get_instance_id()] = joystick
            except pygame.error:
                continue

    def _join_requests(
        self,
        events: Sequence[pygame.event.Event],
        roster: ActiveRoster,
    ) -> list[DeviceRef]:
        requests: list[DeviceRef] = []
        for event in events:
            if event.type == pygame.KEYDOWN and not _is_repeat(event):
                route = next((route for route in KEYBOARD_ROUTES if event.key == route.join_key), None)
                if route is not None and roster.player_for_device(route.device) is None:
                    _append_unique_device(requests, route.device)
            elif event.type == pygame.JOYBUTTONDOWN and event.button == GAMEPAD_BINDING.start_button:
                instance_id = _event_instance_id(event)
                if instance_id is None:
                    continue
                device = self._gamepad_device(instance_id)
                if roster.player_for_device(device) is None:
                    _append_unique_device(requests, device)
        return requests

    def _gamepad_held_commands(self, player: ActivePlayer) -> list[InputCommand]:
        instance_id = _instance_id_from_uid(player.device.uid)
        joystick = self._joysticks.get(instance_id) if instance_id is not None else None
        if joystick is None:
            axis = 0
            hover = False
            guard = False
        else:
            try:
                axis_value = joystick.get_axis(GAMEPAD_BINDING.axis_move_x)
                axis = 1 if axis_value > 0.35 else -1 if axis_value < -0.35 else 0
                hover = bool(joystick.get_button(GAMEPAD_BINDING.jump_button))
                guard = bool(joystick.get_button(GAMEPAD_BINDING.guard_button))
            except pygame.error:
                axis = 0
                hover = False
                guard = False
        return [
            MoveCommand(player_slot=player.slot, axis=axis),
            HoverCommand(player_slot=player.slot, held=hover),
            GuardCommand(player_slot=player.slot, held=guard),
        ]

    def _gamepad_event_commands(
        self,
        player: ActivePlayer,
        event: pygame.event.Event,
    ) -> list[InputCommand]:
        instance_id = _event_instance_id(event)
        if instance_id is None or player.device.uid != f"gamepad-{instance_id}":
            return []

        slot = player.slot
        if event.type == pygame.JOYBUTTONDOWN:
            if event.button == GAMEPAD_BINDING.jump_button:
                return [JumpCommand(slot, True), ConfirmCommand(slot)]
            if event.button == GAMEPAD_BINDING.draw_button:
                return [DrawStartCommand(slot)]
            if event.button == GAMEPAD_BINDING.ability_button:
                return [AbilityUseCommand(slot, True), CancelCommand(slot)]
            if event.button == GAMEPAD_BINDING.dodge_button:
                return [DodgeCommand(slot, True)]
            if event.button == GAMEPAD_BINDING.drop_button:
                return [DropAbilityCommand(slot, True)]
            if event.button == GAMEPAD_BINDING.start_button:
                return [PauseCommand(slot)]
        elif event.type == pygame.JOYBUTTONUP and event.button == GAMEPAD_BINDING.draw_button:
            return [DrawReleaseCommand(slot)]
        elif event.type == pygame.JOYHATMOTION:
            hat_x, hat_y = (int(value) for value in event.value)
            state_key = (instance_id, int(event.hat))
            previous_x, previous_y = self._hat_menu_state.get(state_key, (0, 0))
            self._hat_menu_state[state_key] = (hat_x, hat_y)
            commands: list[InputCommand] = []
            if hat_x and hat_x != previous_x:
                commands.append(NavigateCommand(slot, x=hat_x, y=0))
            if hat_y and hat_y != previous_y:
                commands.append(NavigateCommand(slot, x=0, y=-hat_y))
            return commands
        elif event.type == pygame.JOYAXISMOTION and event.axis in (0, 1):
            direction = 1 if event.value > 0.5 else -1 if event.value < -0.5 else 0
            state_key = (instance_id, int(event.axis))
            previous = self._axis_menu_state.get(state_key, 0)
            self._axis_menu_state[state_key] = direction
            if direction == 0 or direction == previous:
                return []
            if event.axis == 0:
                return [NavigateCommand(slot, x=direction, y=0)]
            return [NavigateCommand(slot, x=0, y=direction)]
        return []

    def _removed_gamepads(
        self,
        events: Sequence[pygame.event.Event],
        roster: ActiveRoster,
    ) -> list[DeviceRef]:
        disconnected: list[DeviceRef] = []
        for event in events:
            if event.type != pygame.JOYDEVICEREMOVED:
                continue
            instance_id = _event_instance_id(event)
            if instance_id is None:
                continue
            candidate = self._gamepad_device(instance_id)
            player = roster.player_for_device(candidate)
            _append_unique_device(disconnected, player.device if player is not None else candidate)
            self._joysticks.pop(instance_id, None)
            self._axis_menu_state = {
                key: value for key, value in self._axis_menu_state.items() if key[0] != instance_id
            }
            self._hat_menu_state = {
                key: value for key, value in self._hat_menu_state.items() if key[0] != instance_id
            }
        return disconnected

    def _gamepad_device(self, instance_id: int) -> DeviceRef:
        joystick = self._joysticks.get(instance_id)
        try:
            label = joystick.get_name() if joystick is not None else ""
        except pygame.error:
            label = ""
        return DeviceRef(
            kind="gamepad",
            uid=f"gamepad-{instance_id}",
            label=label or f"Gamepad {instance_id}",
        )


def _keyboard_route(uid: str) -> _KeyboardRoute | None:
    return next((route for route in KEYBOARD_ROUTES if route.device.uid == uid), None)


def _keyboard_held_commands(slot: int, profile: KeyboardProfile, keys: KeyState) -> list[InputCommand]:
    move_axis = int(bool(keys[profile.move_right])) - int(bool(keys[profile.move_left]))
    return [
        MoveCommand(player_slot=slot, axis=move_axis),
        HoverCommand(player_slot=slot, held=bool(keys[profile.jump])),
        GuardCommand(player_slot=slot, held=bool(keys[profile.guard])),
    ]


def _keyboard_event_commands(
    slot: int,
    route: _KeyboardRoute,
    event: pygame.event.Event,
) -> list[InputCommand]:
    profile = route.profile
    if event.type == pygame.KEYUP:
        return [DrawReleaseCommand(slot)] if event.key == profile.draw else []
    if event.type != pygame.KEYDOWN or _is_repeat(event):
        return []

    key = event.key
    commands: list[InputCommand] = []
    if key == profile.jump:
        commands.extend((JumpCommand(slot, True), ConfirmCommand(slot)))
    elif key == profile.draw:
        commands.append(DrawStartCommand(slot))
    elif key == profile.ability:
        commands.append(AbilityUseCommand(slot, True))
    elif key == profile.dodge:
        commands.append(DodgeCommand(slot, True))
    elif key == profile.drop_ability:
        commands.append(DropAbilityCommand(slot, True))

    directions = {
        profile.move_left: (-1, 0),
        profile.move_right: (1, 0),
        profile.jump: (0, -1),
        profile.draw: (0, 1),
    }
    if key in directions:
        x, y = directions[key]
        commands.append(NavigateCommand(slot, x=x, y=y))
    if key == route.cancel_key:
        commands.append(CancelCommand(slot))
    if key == route.join_key:
        commands.append(PauseCommand(slot))
    return commands


def _append_unique_device(devices: list[DeviceRef], candidate: DeviceRef) -> None:
    identity = (candidate.kind, candidate.uid)
    if all((device.kind, device.uid) != identity for device in devices):
        devices.append(candidate)


def _event_instance_id(event: pygame.event.Event) -> int | None:
    instance_id = getattr(event, "instance_id", None)
    return instance_id if isinstance(instance_id, int) else None


def _instance_id_from_uid(uid: str) -> int | None:
    prefix = "gamepad-"
    if not uid.startswith(prefix):
        return None
    try:
        return int(uid[len(prefix) :])
    except ValueError:
        return None


def _is_repeat(event: pygame.event.Event) -> bool:
    return bool(getattr(event, "repeat", False))
