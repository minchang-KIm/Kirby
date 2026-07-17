"""The sole async frame coordinator for native and browser Windsprig runtimes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol

import pygame

from windsprig.config import GameConfig
from windsprig.content import CampaignCatalog
from windsprig.core.time import FixedStepClock
from windsprig.feasibility import FoundationProbe
from windsprig.gameplay.runtime import StageRuntime
from windsprig.input.commands import ConfirmCommand, InputFrame
from windsprig.input.queue import InputQueue
from windsprig.input.roster import ActiveRoster, DeviceRef
from windsprig.input.router import InputRouter, KeyState, RoutedInput
from windsprig.meta import (
    CompletionTracker,
    SaveData,
    SaveLoadResult,
    SaveMigrationCatalog,
    SaveNotice,
    SaveService,
    SaveWriteResult,
)
from windsprig.platform.native import create_native_services
from windsprig.platform.services import PlatformServices, WebTestStatus, publish_test_status
from windsprig.screens.base import Screen, ScreenFactory, ScreenId
from windsprig.screens.foundation import (
    FoundationScreen,
    FoundationScreenFactory,
    create_foundation_screen_factory,
)

_POINTER_DOWN_TYPES = frozenset((pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN))


class InputCollector(Protocol):
    """Collect one roster-aware render-frame input snapshot."""

    def collect(
        self,
        events: Sequence[pygame.event.Event],
        keys: KeyState,
        roster: ActiveRoster,
    ) -> RoutedInput:
        """Translate platform input without mutating roster ownership."""
        raise NotImplementedError


class GameApp:
    """Coordinate lifecycle, input, fixed updates, rendering, and cooperative yield."""

    def __init__(
        self,
        config: GameConfig | None = None,
        services: PlatformServices | None = None,
        screen_factory: ScreenFactory | None = None,
        *,
        input_router: InputCollector | None = None,
        input_queue: InputQueue | None = None,
        roster: ActiveRoster | None = None,
        fixed_clock: FixedStepClock | None = None,
        event_source: Callable[[], Sequence[pygame.event.Event]] | None = None,
        key_source: Callable[[], KeyState] | None = None,
        initial_screen_id: ScreenId | None = None,
        probe: FoundationProbe | None = None,
    ) -> None:
        self.config = config or GameConfig()
        self.services = services or create_native_services(self.config)
        if screen_factory is None:
            active_roster = roster or ActiveRoster(self.config.max_local_players)
            foundation_factory = create_foundation_screen_factory(
                self.config,
                self.services,
                lambda: datetime.now(UTC),
                roster=active_roster,
                probe=probe,
            )
            self.screen_factory: ScreenFactory = foundation_factory
            self.roster = active_roster
        else:
            self.screen_factory = screen_factory
            if roster is not None:
                self.roster = roster
            elif isinstance(screen_factory, FoundationScreenFactory):
                self.roster = screen_factory.roster
            else:
                self.roster = ActiveRoster(self.config.max_local_players)
        self.active_roster = self.roster
        self.input_router = input_router or InputRouter()
        self.input_queue = input_queue or InputQueue()
        self.fixed_clock = fixed_clock or FixedStepClock(self.config.fixed_dt_ms)
        self.event_source = event_source or _pygame_events
        self.key_source = key_source or _pygame_keys
        if probe is not None:
            self.probe = probe
        elif isinstance(self.screen_factory, FoundationScreenFactory):
            self.probe = self.screen_factory.probe
        else:
            self.probe = FoundationProbe(self.services.storage, enabled=False)
        self.canvas = pygame.Surface(self.config.resolution)
        self.performance_diagnostics: list[str] = []
        self.disconnected_devices: tuple[DeviceRef, ...] = ()
        self.running = False
        self._audio_initialization_attempted = False
        self._last_web_test_status: WebTestStatus | None = None
        selected_initial_id = initial_screen_id or self._factory_initial_screen_id()
        self._active_screen_id = selected_initial_id
        self.screen: Screen = self.screen_factory.create(selected_initial_id)
        self.screen.on_enter(MappingProxyType({}))

    async def run(self) -> int:
        """Run frames cooperatively until lifecycle input requests shutdown."""
        self.running = True
        while self.running:
            await self.run_frame()
        return 0

    async def run_frame(self) -> None:
        """Coordinate exactly one rendered frame without quitting pygame or the process."""
        raw_elapsed_ms = self.services.time.tick(self.config.target_fps)
        elapsed_ms = min(max(0.0, raw_elapsed_ms), float(self.config.max_frame_elapsed_ms))
        events = tuple(self.event_source())
        lifecycle_events = self.services.lifecycle.consume(events)

        if (
            not self._audio_initialization_attempted
            and self.services.capabilities.audio_requires_gesture
            and not self.services.audio.status.ready
            and any(event.type in _POINTER_DOWN_TYPES for event in events)
        ):
            self._audio_initialization_attempted = True
            try:
                audio_status = await self.services.audio.initialize(after_user_gesture=True)
            except Exception:
                # Audio is an explicitly nonfatal platform capability.
                audio_status = self.services.audio.status
            if audio_status.ready:
                # The unlocking pointer is itself a confirm action. Starting a
                # committed cue here proves browser decoding/channel ownership
                # without feeding any additional input into the simulation.
                try:
                    self.services.audio.play_cue("sfx.ui.confirm", "sfx")
                except Exception:
                    pass
                self.probe.mark("audio", "ready")
            elif audio_status.muted:
                self.probe.mark("audio", "muted")

        routed = self.input_router.collect(events, self.key_source(), self.roster)
        # Queue against the old ownership snapshot, then explicitly invalidate reused slots.
        self.input_queue.push(routed.frame)
        self._remove_disconnected_players(routed.disconnected_devices)
        disconnected_identities = {(device.kind, device.uid) for device in routed.disconnected_devices}
        non_disconnected_joins = tuple(
            device for device in routed.join_requests if (device.kind, device.uid) not in disconnected_identities
        )
        self._join_requested_players(non_disconnected_joins)
        self.disconnected_devices = routed.disconnected_devices

        for event in lifecycle_events:
            if event.kind == "quit":
                self.running = False
            elif event.kind == "focus_lost":
                # Clearing after routing also drops edges sampled in the focus-loss frame.
                self.input_queue.clear_held()
                self.services.audio.pause()
            elif event.kind == "focus_gained":
                self.services.audio.resume()

        batch = self.fixed_clock.push(elapsed_ms, self.config.max_catch_up_steps)
        if batch.dropped_ms:
            self.performance_diagnostics.append(f"fixed_step_drop:{int(batch.dropped_ms)}")
        for _ in range(batch.steps):
            # Input is consumed before transition so a later catch-up step targets the new screen.
            input_frame = self.input_queue.consume_step()
            self._observe_probe_input(input_frame)
            transition = self.screen.fixed_update(
                self.config.fixed_dt_ms,
                input_frame,
            )
            if transition is None:
                continue
            payload = MappingProxyType(dict(transition.payload))
            self.screen.on_exit()
            self.screen = self.screen_factory.create(transition.target)
            self._active_screen_id = transition.target
            self.screen.on_enter(payload)

        self.screen.render(self.canvas, batch.alpha)
        self.services.display.present(self.canvas)
        self._publish_web_test_status()
        gameplay_active = (
            isinstance(self.screen, FoundationScreen)
            and self._active_screen_id == "playing"
            and isinstance(self.screen.runtime, StageRuntime)
        )
        self.probe.presented_frame(raw_elapsed_ms, gameplay_active=gameplay_active)
        await self.services.time.yield_frame()

    def _publish_web_test_status(self) -> None:
        """Publish changed post-render product state without feeding simulation input."""
        status = self.screen_factory.web_test_status(
            self._active_screen_id,
            len(self.roster.players),
        )
        if status == self._last_web_test_status:
            return
        publish_test_status(self.services.browser, status)
        self._last_web_test_status = status

    def _observe_probe_input(self, input_frame: InputFrame) -> None:
        for commands in input_frame.commands_by_slot.values():
            for command in commands:
                if isinstance(command, ConfirmCommand):
                    self.probe.consumed_input_edge()

    def confirm_save_reset(self) -> SaveWriteResult:
        """Expose the foundation screen's narrow verified reset action."""
        return self.foundation_screen.confirm_save_reset()

    def reload_save(self) -> SaveLoadResult:
        """Expose authoritative save reload without replacing the active service."""
        return self.foundation_screen.reload_save()

    @property
    def foundation_screen(self) -> FoundationScreen:
        """Return the shared production screen that owns campaign and recovery state."""
        if isinstance(self.screen_factory, FoundationScreenFactory):
            return self.screen_factory.foundation_screen
        if isinstance(self.screen, FoundationScreen):
            return self.screen
        raise RuntimeError("the configured screen factory has no foundation state")

    @property
    def catalog(self) -> CampaignCatalog:
        """Expose the foundation catalog for compatibility and diagnostics."""
        return self.foundation_screen.catalog

    @property
    def migration_catalog(self) -> SaveMigrationCatalog:
        """Expose stable migration IDs owned by the foundation screen."""
        return self.foundation_screen.migration_catalog

    @property
    def tracker(self) -> CompletionTracker:
        """Expose current in-memory completion state."""
        return self.foundation_screen.tracker

    @property
    def runtime(self) -> StageRuntime | None:
        """Expose the current deterministic stage runtime, if any."""
        return self.foundation_screen.runtime

    @runtime.setter
    def runtime(self, runtime: StageRuntime | None) -> None:
        self.foundation_screen.runtime = runtime

    @property
    def save_service(self) -> SaveService:
        """Expose the one active save transaction service."""
        return self.foundation_screen.save_service

    @property
    def save_data(self) -> SaveData:
        """Expose immutable in-memory save data."""
        return self.foundation_screen.save_data

    @property
    def save_notice(self) -> SaveNotice | None:
        """Expose the current recovery notice for status presentation."""
        return self.foundation_screen.save_notice

    @property
    def save_write_result(self) -> SaveWriteResult | None:
        """Expose the latest explicit persistence result."""
        return self.foundation_screen.save_write_result

    @property
    def save_status(self) -> str:
        """Expose the current user-facing persistence status."""
        return self.foundation_screen.save_status

    def _factory_initial_screen_id(self) -> ScreenId:
        if isinstance(self.screen_factory, FoundationScreenFactory):
            return self.screen_factory.initial_screen_id
        return "world_map"

    def _remove_disconnected_players(self, devices: Sequence[DeviceRef]) -> None:
        for device in devices:
            player = self.roster.player_for_device(device)
            if player is None:
                continue
            # Slots are reusable; no old held value or edge may reach a replacement owner.
            self.input_queue.clear_slot(player.slot)
            self.roster.leave(player.slot)

    def _join_requested_players(self, devices: Sequence[DeviceRef]) -> None:
        for device in devices:
            if self.roster.player_for_device(device) is not None:
                continue
            if len(self.roster.players) >= self.config.max_local_players:
                break
            self.roster.join(device)

    def _on_stage_progress(self) -> None:
        self.foundation_screen._on_stage_progress()

    def _flush_save(self) -> None:
        self.foundation_screen._flush_save()


def _pygame_events() -> Sequence[pygame.event.Event]:
    return pygame.event.get()


def _pygame_keys() -> KeyState:
    return pygame.key.get_pressed()
