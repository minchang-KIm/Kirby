from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import pygame
import pytest

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.input.commands import InputFrame, JumpCommand, MoveCommand
from windsprig.input.queue import InputQueue
from windsprig.input.roster import ActiveRoster, DeviceRef
from windsprig.input.router import RoutedInput
from windsprig.platform.services import (
    AudioStatus,
    DisplayCapabilities,
    LifecycleEvent,
    PlatformCapabilities,
    PlatformServices,
    StorageCapabilities,
)


class FakeStorage:
    capabilities = StorageCapabilities(persistent=False, atomic_write=False, backup=False)

    def read_text(self, _key: str) -> str | None:
        return None

    def write_text(self, _key: str, _value: str) -> None:
        return None

    def delete(self, _key: str) -> None:
        return None

    def keys(self, _prefix: str) -> tuple[str, ...]:
        return ()


class FakeAudio:
    def __init__(self) -> None:
        self._status = AudioStatus(ready=False, muted=True)
        self.initialize_count = 0
        self.pause_count = 0
        self.resume_count = 0
        self.fail_initialize = False

    @property
    def status(self) -> AudioStatus:
        return self._status

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        assert after_user_gesture is True
        self.initialize_count += 1
        if self.fail_initialize:
            raise RuntimeError("audio unavailable")
        self._status = AudioStatus(ready=True, muted=False)
        return self._status

    def play_cue(self, _cue_id: str, bus: str = "sfx") -> bool:
        _ = bus
        return False

    def pause(self) -> None:
        self.pause_count += 1

    def resume(self) -> None:
        self.resume_count += 1

    def set_bus_volume(self, _bus: str, _value: float) -> None:
        return None


class FakeDisplay:
    capabilities = DisplayCapabilities(fullscreen=False)

    def __init__(self) -> None:
        self.presented: list[pygame.Surface] = []

    def create_window(self, logical_size: tuple[int, int], fullscreen: bool) -> pygame.Surface:
        _ = fullscreen
        return pygame.Surface(logical_size)

    def present(self, canvas: pygame.Surface) -> None:
        self.presented.append(canvas)

    def set_fullscreen(self, _enabled: bool) -> bool:
        return False


class FakeTime:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.tick_targets: list[int] = []
        self.yield_count = 0

    def tick(self, target_fps: int) -> float:
        self.tick_targets.append(target_fps)
        return self.elapsed

    def monotonic_ms(self) -> float:
        return 0.0

    async def yield_frame(self) -> None:
        self.yield_count += 1


class FakeLifecycle:
    def __init__(self) -> None:
        self.next_events: tuple[LifecycleEvent, ...] = ()

    def consume(self, _events: Sequence[pygame.event.Event]) -> tuple[LifecycleEvent, ...]:
        return self.next_events


class FakeKeys:
    def __getitem__(self, _key: int) -> int:
        return 0


class FakeRouter:
    def __init__(self) -> None:
        self.next_routed = RoutedInput(InputFrame.empty())

    def collect(
        self,
        _events: Sequence[pygame.event.Event],
        _keys: FakeKeys,
        _roster: ActiveRoster,
    ) -> RoutedInput:
        return self.next_routed


@dataclass(slots=True)
class FakeTransition:
    target: str
    payload: Mapping[str, object] = field(default_factory=dict)


class RecordingScreen:
    def __init__(self) -> None:
        self.frames: list[InputFrame] = []
        self.enters: list[Mapping[str, object]] = []
        self.exit_count = 0
        self.rendered_alphas: list[float] = []
        self.next_transition: FakeTransition | None = None

    def on_enter(self, payload: Mapping[str, object]) -> None:
        self.enters.append(payload)

    def on_exit(self) -> None:
        self.exit_count += 1

    def fixed_update(self, dt_ms: int, input_frame: InputFrame) -> FakeTransition | None:
        assert dt_ms == 16
        self.frames.append(input_frame)
        transition = self.next_transition
        self.next_transition = None
        return transition

    def render(self, canvas: pygame.Surface, alpha: float) -> None:
        assert canvas.get_size() == (1280, 720)
        self.rendered_alphas.append(alpha)


class RecordingFactory:
    def __init__(self, screens: Mapping[str, RecordingScreen]) -> None:
        self.screens = dict(screens)
        self.created: list[str] = []

    def create(self, screen_id: str) -> RecordingScreen:
        self.created.append(screen_id)
        return self.screens[screen_id]


@dataclass(slots=True)
class AppHarness:
    app: GameApp
    audio: FakeAudio
    display: FakeDisplay
    time: FakeTime
    lifecycle: FakeLifecycle
    router: FakeRouter
    queue: InputQueue
    roster: ActiveRoster
    screen: RecordingScreen
    events: list[pygame.event.Event]


def make_harness(
    *,
    roster: ActiveRoster | None = None,
    queue: InputQueue | None = None,
    screens: Mapping[str, RecordingScreen] | None = None,
    audio_requires_gesture: bool = False,
) -> AppHarness:
    audio = FakeAudio()
    display = FakeDisplay()
    time = FakeTime()
    lifecycle = FakeLifecycle()
    services = PlatformServices(
        storage=FakeStorage(),
        audio=audio,
        display=display,
        time=time,
        lifecycle=lifecycle,
        browser=None,
        capabilities=PlatformCapabilities(
            is_web=False,
            persistent_storage=False,
            fullscreen=False,
            gamepads=True,
            audio_requires_gesture=audio_requires_gesture,
        ),
    )
    router = FakeRouter()
    input_queue = queue or InputQueue()
    active_roster = roster or ActiveRoster()
    world_map = RecordingScreen()
    screen_map = dict(screens or {"world_map": world_map})
    world_map = screen_map["world_map"]
    events: list[pygame.event.Event] = []
    app = GameApp(
        GameConfig(),
        services,
        RecordingFactory(screen_map),
        input_router=router,
        input_queue=input_queue,
        roster=active_roster,
        event_source=lambda: tuple(events),
        key_source=FakeKeys,
    )
    return AppHarness(
        app=app,
        audio=audio,
        display=display,
        time=time,
        lifecycle=lifecycle,
        router=router,
        queue=input_queue,
        roster=active_roster,
        screen=world_map,
        events=events,
    )


def test_game_app_exposes_native_async_run_contracts() -> None:
    assert inspect.iscoroutinefunction(GameApp.run)
    assert inspect.iscoroutinefunction(GameApp.run_frame)


async def test_async_app_keeps_edge_until_first_fixed_step_then_consumes_it_once() -> None:
    harness = make_harness()
    player = harness.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    harness.time.elapsed = 1
    harness.router.next_routed = RoutedInput(
        InputFrame(
            commands_by_slot={
                player.slot: [MoveCommand(player.slot, 1), JumpCommand(player.slot, True)]
            }
        )
    )

    await harness.app.run_frame()

    assert harness.screen.frames == []
    harness.time.elapsed = 15
    harness.router.next_routed = RoutedInput(
        InputFrame(commands_by_slot={player.slot: [MoveCommand(player.slot, 1)]})
    )
    await harness.app.run_frame()
    harness.time.elapsed = 16
    await harness.app.run_frame()

    first_commands = harness.screen.frames[0].commands_for(player.slot)
    second_commands = harness.screen.frames[1].commands_for(player.slot)
    assert sum(isinstance(command, JumpCommand) for command in first_commands) == 1
    assert not any(isinstance(command, JumpCommand) for command in second_commands)
    assert MoveCommand(player.slot, 1) in first_commands
    assert MoveCommand(player.slot, 1) in second_commands
    assert len(harness.display.presented) == 3
    assert harness.time.yield_count == 3
    assert len({id(canvas) for canvas in harness.display.presented}) == 1


async def test_async_app_clamps_elapsed_before_bounded_catch_up_and_records_drop() -> None:
    harness = make_harness()
    harness.time.elapsed = 1_000

    await harness.app.run_frame()

    assert len(harness.screen.frames) == 5
    assert harness.app.performance_diagnostics == ["fixed_step_drop:160"]
    assert harness.screen.rendered_alphas == [pytest.approx(0.625)]


async def test_focus_loss_clears_old_and_same_frame_input_then_audio_resumes_on_gain() -> None:
    harness = make_harness()
    player = harness.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    harness.queue.push(
        InputFrame(commands_by_slot={player.slot: [JumpCommand(player.slot, True)]})
    )
    harness.router.next_routed = RoutedInput(
        InputFrame(
            commands_by_slot={
                player.slot: [MoveCommand(player.slot, 1), JumpCommand(player.slot, True)]
            }
        )
    )
    harness.lifecycle.next_events = (LifecycleEvent("focus_lost"),)
    harness.time.elapsed = 16

    await harness.app.run_frame()

    assert harness.screen.frames[0].commands_for(player.slot) == []
    assert harness.audio.pause_count == 1
    harness.lifecycle.next_events = (LifecycleEvent("focus_gained"),)
    harness.time.elapsed = 0
    await harness.app.run_frame()
    assert harness.audio.resume_count == 1


async def test_pointer_gesture_attempts_audio_initialization_once_and_failure_is_nonfatal() -> None:
    harness = make_harness(audio_requires_gesture=True)
    harness.audio.fail_initialize = True
    harness.events.extend(
        (
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1),
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1),
        )
    )

    await harness.app.run_frame()
    await harness.app.run_frame()

    assert harness.audio.initialize_count == 1
    assert len(harness.display.presented) == 2
    assert harness.time.yield_count == 2


async def test_native_pointer_does_not_repeat_non_gesture_audio_initialization() -> None:
    harness = make_harness(audio_requires_gesture=False)
    harness.events.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))

    await harness.app.run_frame()
    await harness.app.run_frame()

    assert harness.audio.initialize_count == 0


async def test_disconnect_clears_slot_before_reuse_and_joined_owner_gets_no_stale_input() -> None:
    roster = ActiveRoster()
    old_device = DeviceRef("gamepad", "gamepad-7", "Old Controller")
    old_player = roster.join(old_device)
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                old_player.slot: [MoveCommand(old_player.slot, 1), JumpCommand(old_player.slot, True)]
            }
        )
    )
    harness = make_harness(roster=roster, queue=queue)
    new_device = DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD")
    harness.router.next_routed = RoutedInput(
        frame=InputFrame(commands_by_slot={old_player.slot: [MoveCommand(old_player.slot, 0)]}),
        join_requests=(new_device,),
        disconnected_devices=(old_device,),
    )
    harness.time.elapsed = 16

    await harness.app.run_frame()

    new_player = harness.roster.player_for_device(new_device)
    assert new_player is not None and new_player.slot == old_player.slot
    assert harness.roster.player_for_device(old_device) is None
    assert harness.screen.frames[0].commands_for(new_player.slot) == []


async def test_same_frame_disconnect_overrides_matching_join_and_clears_old_owner() -> None:
    roster = ActiveRoster()
    device = DeviceRef("gamepad", "gamepad-7", "Old Controller")
    old_player = roster.join(device)
    queue = InputQueue()
    queue.push(
        InputFrame(
            commands_by_slot={
                old_player.slot: [MoveCommand(old_player.slot, 1), JumpCommand(old_player.slot, True)]
            }
        )
    )
    harness = make_harness(roster=roster, queue=queue)
    harness.router.next_routed = RoutedInput(
        frame=InputFrame(commands_by_slot={old_player.slot: [MoveCommand(old_player.slot, 0)]}),
        join_requests=(device,),
        disconnected_devices=(device,),
    )
    harness.time.elapsed = 16

    await harness.app.run_frame()

    assert harness.roster.players == ()
    assert harness.screen.frames[0].commands_for(old_player.slot) == []


async def test_transition_exits_and_enters_once_and_passes_an_immutable_payload_snapshot() -> None:
    world_map = RecordingScreen()
    playing = RecordingScreen()
    payload: dict[str, object] = {"stage_id": "world_1_stage_1"}
    world_map.next_transition = FakeTransition("playing", payload)
    harness = make_harness(screens={"world_map": world_map, "playing": playing})
    harness.time.elapsed = 16

    await harness.app.run_frame()
    payload["stage_id"] = "changed"

    assert world_map.exit_count == 1
    assert len(world_map.enters) == 1
    assert len(playing.enters) == 1
    assert playing.enters[0]["stage_id"] == "world_1_stage_1"
    with pytest.raises(TypeError):
        playing.enters[0]["stage_id"] = "mutated"  # type: ignore[index]
    assert world_map.rendered_alphas == []
    assert len(playing.rendered_alphas) == 1


async def test_quit_stops_the_loop_but_still_presents_and_yields_the_frame() -> None:
    harness = make_harness()
    harness.app.running = True
    harness.lifecycle.next_events = (LifecycleEvent("quit"),)

    await harness.app.run_frame()

    assert harness.app.running is False
    assert len(harness.display.presented) == 1
    assert harness.time.yield_count == 1
