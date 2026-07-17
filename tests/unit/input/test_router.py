from __future__ import annotations

import pygame

from windsprig.input.commands import (
    AbilityUseCommand,
    CancelCommand,
    ConfirmCommand,
    DodgeCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    GatherConfirmCommand,
    GuardCommand,
    HoverCommand,
    JumpCommand,
    MoveCommand,
    NavigateCommand,
    PauseCommand,
    ProbeCompleteCommand,
)
from windsprig.input.roster import ActiveRoster, DeviceRef
from windsprig.input.router import InputRouter


class FakeKeys:
    def __init__(self, pressed: set[int] | None = None) -> None:
        self.pressed = pressed or set()

    def __getitem__(self, key: int) -> int:
        return int(key in self.pressed)


def key_event(event_type: int, key: int) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key)


def joy_button_event(event_type: int, instance_id: int, button: int) -> pygame.event.Event:
    return pygame.event.Event(event_type, instance_id=instance_id, joy=0, button=button)


def test_unassigned_enter_requests_wasd_join_and_suppresses_same_frame_commands() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    events = [key_event(pygame.KEYDOWN, pygame.K_w), key_event(pygame.KEYDOWN, pygame.K_RETURN)]

    routed = router.collect(events, FakeKeys({pygame.K_w}), roster)

    assert routed.join_requests == (
        DeviceRef(kind="keyboard", uid="keyboard-wasd", label="Keyboard WASD"),
    )
    assert routed.frame.commands_by_slot == {}


def test_keypad_enter_requests_the_second_stable_keyboard_device() -> None:
    routed = InputRouter().collect(
        [key_event(pygame.KEYDOWN, pygame.K_KP_ENTER)],
        FakeKeys(),
        ActiveRoster(),
    )

    assert routed.join_requests == (
        DeviceRef(kind="keyboard", uid="keyboard-arrows", label="Keyboard Arrows"),
    )


def test_assigned_jump_emits_gameplay_and_confirm_edges_only_on_keydown() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    player = roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))

    pressed = router.collect([key_event(pygame.KEYDOWN, pygame.K_w)], FakeKeys({pygame.K_w}), roster)
    held = router.collect([], FakeKeys({pygame.K_w}), roster)

    pressed_commands = pressed.frame.commands_for(player.slot)
    held_commands = held.frame.commands_for(player.slot)
    assert sum(isinstance(command, JumpCommand) for command in pressed_commands) == 1
    assert sum(isinstance(command, ConfirmCommand) for command in pressed_commands) == 1
    assert any(command == NavigateCommand(player_slot=1, x=0, y=-1) for command in pressed_commands)
    assert not any(isinstance(command, (JumpCommand, ConfirmCommand, NavigateCommand)) for command in held_commands)
    assert any(command == HoverCommand(player_slot=1, held=True) for command in held_commands)


def test_only_joined_keyboard_profiles_contribute_continuous_commands() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    arrows = roster.join(DeviceRef("keyboard", "keyboard-arrows", "Keyboard Arrows"))

    routed = router.collect([], FakeKeys({pygame.K_a, pygame.K_RIGHT}), roster)
    commands = routed.frame.commands_for(arrows.slot)

    assert set(routed.frame.commands_by_slot) == {arrows.slot}
    assert any(command == MoveCommand(player_slot=arrows.slot, axis=1) for command in commands)
    assert not any(command == MoveCommand(player_slot=arrows.slot, axis=-1) for command in commands)
    assert [type(command) for command in commands] == [
        MoveCommand,
        HoverCommand,
        GuardCommand,
        AbilityUseCommand,
    ]


def test_keyboard_menu_edges_are_routed_in_event_order() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    events = [
        key_event(pygame.KEYDOWN, pygame.K_a),
        key_event(pygame.KEYDOWN, pygame.K_s),
        key_event(pygame.KEYDOWN, pygame.K_d),
        key_event(pygame.KEYDOWN, pygame.K_RETURN),
        key_event(pygame.KEYDOWN, pygame.K_ESCAPE),
    ]

    commands = router.collect(events, FakeKeys(), roster).frame.commands_for(1)

    assert [command for command in commands if isinstance(command, NavigateCommand)] == [
        NavigateCommand(player_slot=1, x=-1, y=0),
        NavigateCommand(player_slot=1, x=0, y=1),
        NavigateCommand(player_slot=1, x=1, y=0),
    ]
    assert sum(isinstance(command, PauseCommand) for command in commands) == 1
    assert sum(isinstance(command, CancelCommand) for command in commands) == 1


def test_escape_cancels_for_the_arrows_keyboard_when_it_is_the_only_keyboard() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    player = roster.join(DeviceRef("keyboard", "keyboard-arrows", "Keyboard Arrows"))

    commands = router.collect(
        [key_event(pygame.KEYDOWN, pygame.K_ESCAPE)],
        FakeKeys(),
        roster,
    ).frame.commands_for(player.slot)

    assert commands[-1] == CancelCommand(player_slot=player.slot)
    assert getattr(commands[-1], "origin", None) == "cancel"


def test_keyboard_routes_every_gameplay_edge_and_released_held_value() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    events = [
        key_event(pygame.KEYDOWN, pygame.K_s),
        key_event(pygame.KEYUP, pygame.K_s),
        key_event(pygame.KEYDOWN, pygame.K_f),
        key_event(pygame.KEYUP, pygame.K_f),
        key_event(pygame.KEYDOWN, pygame.K_h),
        key_event(pygame.KEYDOWN, pygame.K_t),
    ]

    pressed = router.collect(events, FakeKeys({pygame.K_g}), roster).frame.commands_for(1)
    released = router.collect([], FakeKeys(), roster).frame.commands_for(1)

    assert any(isinstance(command, DrawStartCommand) for command in pressed)
    assert any(isinstance(command, DrawReleaseCommand) for command in pressed)
    assert AbilityUseCommand(1, held=False) in pressed
    assert AbilityUseCommand(1, pressed=True) in pressed
    assert GatherConfirmCommand(1, pressed=True) in pressed
    assert AbilityUseCommand(1, released=True) in pressed
    assert any(isinstance(command, DodgeCommand) for command in pressed)
    assert any(isinstance(command, DropAbilityCommand) for command in pressed)
    assert GuardCommand(player_slot=1, held=True) in pressed
    assert GuardCommand(player_slot=1, held=False) in released


def test_f9_routes_only_as_the_probe_completion_command_for_an_active_keyboard() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))

    commands = router.collect(
        [key_event(pygame.KEYDOWN, pygame.K_F9)],
        FakeKeys(),
        roster,
    ).frame.commands_for(1)

    assert commands == [
        MoveCommand(player_slot=1, axis=0),
        HoverCommand(player_slot=1, held=False),
        GuardCommand(player_slot=1, held=False),
        AbilityUseCommand(player_slot=1, held=False),
        ProbeCompleteCommand(player_slot=1),
    ]


def test_gamepad_start_uses_instance_identity_and_deduplicates_join_request() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    events = [
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=0),
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=7),
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=7),
    ]

    routed = router.collect(events, FakeKeys(), roster)

    assert routed.join_requests == (
        DeviceRef(kind="gamepad", uid="gamepad-42", label="Gamepad 42"),
    )
    assert routed.frame.commands_by_slot == {}


def test_same_frame_gamepad_start_and_removal_reports_disconnect_without_ghost_join() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    events = [
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=7),
        pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=42, joy=0),
    ]

    routed = router.collect(events, FakeKeys(), roster)

    assert routed.disconnected_devices == (
        DeviceRef(kind="gamepad", uid="gamepad-42", label="Gamepad 42"),
    )
    assert routed.join_requests == ()
    assert roster.players == ()


def test_assigned_gamepad_routes_primary_cancel_pause_and_hat_edges() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    player = roster.join(DeviceRef("gamepad", "gamepad-42", "My Controller"))
    events = [
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=0),
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=1),
        joy_button_event(pygame.JOYBUTTONUP, instance_id=42, button=1),
        joy_button_event(pygame.JOYBUTTONDOWN, instance_id=42, button=7),
        pygame.event.Event(pygame.JOYHATMOTION, instance_id=42, joy=0, hat=0, value=(1, -1)),
    ]

    commands = router.collect(events, FakeKeys(), roster).frame.commands_for(player.slot)

    assert any(isinstance(command, JumpCommand) for command in commands)
    assert any(isinstance(command, ConfirmCommand) for command in commands)
    assert AbilityUseCommand(player.slot, held=False) in commands
    assert AbilityUseCommand(player.slot, pressed=True) in commands
    assert GatherConfirmCommand(player.slot, pressed=True) in commands
    assert AbilityUseCommand(player.slot, released=True) in commands
    gamepad_cancel = next(command for command in commands if isinstance(command, CancelCommand))
    assert getattr(gamepad_cancel, "origin", None) == "ability_button"
    assert any(isinstance(command, PauseCommand) for command in commands)
    assert [command for command in commands if isinstance(command, NavigateCommand)] == [
        NavigateCommand(player_slot=player.slot, x=1, y=0),
        NavigateCommand(player_slot=player.slot, x=0, y=1),
    ]


def test_gamepad_hat_navigation_requires_neutral_before_repeating_direction() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    player = roster.join(DeviceRef("gamepad", "gamepad-42", "My Controller"))

    def hat(value: tuple[int, int]) -> pygame.event.Event:
        return pygame.event.Event(pygame.JOYHATMOTION, instance_id=42, joy=0, hat=0, value=value)

    first = router.collect([hat((1, 0))], FakeKeys(), roster).frame.commands_for(player.slot)
    repeated = router.collect([hat((1, 0))], FakeKeys(), roster).frame.commands_for(player.slot)
    neutral = router.collect([hat((0, 0))], FakeKeys(), roster).frame.commands_for(player.slot)
    rearmed = router.collect([hat((1, 0))], FakeKeys(), roster).frame.commands_for(player.slot)

    assert [command for command in first if isinstance(command, NavigateCommand)] == [
        NavigateCommand(player_slot=player.slot, x=1, y=0)
    ]
    assert not any(isinstance(command, NavigateCommand) for command in repeated)
    assert not any(isinstance(command, NavigateCommand) for command in neutral)
    assert [command for command in rearmed if isinstance(command, NavigateCommand)] == [
        NavigateCommand(player_slot=player.slot, x=1, y=0)
    ]


def test_removed_gamepad_reports_the_roster_device_without_mutating_roster() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    player = roster.join(DeviceRef("gamepad", "gamepad-73", "Named Controller"))
    removed = pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=73, joy=0)

    routed = router.collect([removed], FakeKeys(), roster)

    assert routed.disconnected_devices == (player.device,)
    assert roster.players == (player,)


def test_removed_gamepad_uses_stable_identity_when_joystick_metadata_is_unavailable() -> None:
    class RemovedJoystick:
        def get_axis(self, _axis: int) -> float:
            raise pygame.error("device removed")

        def get_name(self) -> str:
            raise pygame.error("device removed")

    router = InputRouter()
    router._joysticks[73] = RemovedJoystick()  # type: ignore[assignment]
    roster = ActiveRoster()
    player = roster.join(DeviceRef("gamepad", "gamepad-73", "Named Controller"))
    removed = pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=73, joy=0)

    routed = router.collect([removed], FakeKeys(), roster)

    assert routed.disconnected_devices == (player.device,)


def test_removed_gamepad_publishes_neutral_held_values_in_the_removal_frame() -> None:
    class HeldJoystick:
        def get_axis(self, _axis: int) -> float:
            return 1.0

        def get_button(self, _button: int) -> int:
            return 1

        def get_name(self) -> str:
            return "Held Controller"

    router = InputRouter()
    router._joysticks[91] = HeldJoystick()  # type: ignore[assignment]
    roster = ActiveRoster()
    player = roster.join(DeviceRef("gamepad", "gamepad-91", "Held Controller"))
    removed = pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=91, joy=0)

    routed = router.collect([removed], FakeKeys(), roster)

    assert routed.frame.commands_for(player.slot) == [
        MoveCommand(player_slot=player.slot, axis=0),
        HoverCommand(player_slot=player.slot, held=False),
        GuardCommand(player_slot=player.slot, held=False),
        AbilityUseCommand(player_slot=player.slot, held=False),
    ]


def test_repeat_keyboard_ability_keydown_does_not_duplicate_the_press_edge() -> None:
    router = InputRouter()
    roster = ActiveRoster()
    roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    events = [
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, repeat=False),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, repeat=True),
    ]

    commands = router.collect(events, FakeKeys({pygame.K_f}), roster).frame.commands_for(1)

    assert [command for command in commands if isinstance(command, AbilityUseCommand)] == [
        AbilityUseCommand(1, held=True),
        AbilityUseCommand(1, pressed=True),
    ]
