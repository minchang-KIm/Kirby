from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import pygame

AudioBus = Literal["music", "sfx"]
LifecycleKind = Literal["quit", "focus_lost", "focus_gained"]
type DiagnosticPrimitive = str | int | bool
WEB_TEST_DIAGNOSTIC_NAME = "__WINSPRIG_TEST__"


@dataclass(frozen=True, slots=True)
class StorageCapabilities:
    persistent: bool
    atomic_write: bool
    backup: bool


@dataclass(frozen=True, slots=True)
class AudioStatus:
    ready: bool
    muted: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DisplayCapabilities:
    fullscreen: bool


@dataclass(frozen=True, slots=True)
class PlatformCapabilities:
    is_web: bool
    persistent_storage: bool
    fullscreen: bool
    gamepads: bool
    audio_requires_gesture: bool


@dataclass(frozen=True, slots=True)
class WebTestStatus:
    """Expose a primitive read-only product summary without gameplay authority."""

    state: str
    save_version: int
    save_status: str
    cleared_stages: int
    active_players: int


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    kind: LifecycleKind


class StorageService(Protocol):
    @property
    def capabilities(self) -> StorageCapabilities:
        raise NotImplementedError

    def read_text(self, key: str) -> str | None:
        raise NotImplementedError

    def write_text(self, key: str, value: str) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def keys(self, prefix: str) -> tuple[str, ...]:
        raise NotImplementedError


class AudioService(Protocol):
    @property
    def status(self) -> AudioStatus:
        raise NotImplementedError

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        raise NotImplementedError

    def play_cue(self, cue_id: str, bus: AudioBus = "sfx") -> bool:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def resume(self) -> None:
        raise NotImplementedError

    def set_bus_volume(self, bus: AudioBus, value: float) -> None:
        raise NotImplementedError


class DisplayService(Protocol):
    @property
    def capabilities(self) -> DisplayCapabilities:
        raise NotImplementedError

    def create_window(self, logical_size: tuple[int, int], fullscreen: bool) -> pygame.Surface:
        raise NotImplementedError

    def present(self, canvas: pygame.Surface) -> None:
        raise NotImplementedError

    def set_fullscreen(self, enabled: bool) -> bool:
        raise NotImplementedError


class TimeService(Protocol):
    def tick(self, target_fps: int) -> float:
        raise NotImplementedError

    def monotonic_ms(self) -> float:
        raise NotImplementedError

    async def yield_frame(self) -> None:
        raise NotImplementedError


class LifecycleService(Protocol):
    def consume(self, events: Sequence[pygame.event.Event]) -> tuple[LifecycleEvent, ...]:
        raise NotImplementedError


class BrowserBridge(Protocol):
    def local_storage_get(self, key: str) -> str | None:
        raise NotImplementedError

    def local_storage_set(self, key: str, value: str) -> None:
        raise NotImplementedError

    def local_storage_remove(self, key: str) -> None:
        raise NotImplementedError

    def local_storage_keys(self, prefix: str) -> tuple[str, ...]:
        raise NotImplementedError

    def query_param(self, name: str) -> str | None:
        raise NotImplementedError

    def request_fullscreen(self) -> bool:
        raise NotImplementedError

    def document_hidden(self) -> bool:
        raise NotImplementedError

    def publish_audio_status(self, status: AudioStatus) -> None:
        raise NotImplementedError

    def publish_diagnostic(
        self,
        name: str,
        payload: Mapping[str, DiagnosticPrimitive],
    ) -> None:
        raise NotImplementedError


def publish_test_status(
    bridge: BrowserBridge | None,
    status: WebTestStatus,
) -> None:
    """Publish the product summary only under the exact browser E2E opt-in."""
    if bridge is None or bridge.query_param("e2e") != "1":
        return
    bridge.publish_diagnostic(
        WEB_TEST_DIAGNOSTIC_NAME,
        {
            "activePlayers": status.active_players,
            "clearedStages": status.cleared_stages,
            "saveStatus": status.save_status,
            "saveVersion": status.save_version,
            "state": status.state,
        },
    )


@dataclass(frozen=True, slots=True)
class PlatformServices:
    storage: StorageService
    audio: AudioService
    display: DisplayService
    time: TimeService
    lifecycle: LifecycleService
    browser: BrowserBridge | None
    capabilities: PlatformCapabilities
