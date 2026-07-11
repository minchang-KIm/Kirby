from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pygame

from windsprig.config import GameConfig
from windsprig.platform.services import (
    AudioBus,
    AudioStatus,
    DisplayCapabilities,
    LifecycleEvent,
    LifecycleKind,
    PlatformCapabilities,
    PlatformServices,
    StorageCapabilities,
)


class NativeStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._resolved_root = self.root
        self._capabilities = StorageCapabilities(persistent=True, atomic_write=True, backup=True)

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    def _path(self, key: str) -> Path:
        relative = Path(key)
        if not key or relative.is_absolute() or relative.drive:
            raise ValueError("storage key escapes storage root")
        candidate = (self._resolved_root / relative).resolve()
        if candidate == self._resolved_root or self._resolved_root not in candidate.parents:
            raise ValueError("storage key escapes storage root")
        return candidate

    def read_text(self, key: str) -> str | None:
        path = self._path(key)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def write_text(self, key: str, value: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def keys(self, prefix: str) -> tuple[str, ...]:
        keys: list[str] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            key = path.relative_to(self.root).as_posix()
            try:
                contained = self._path(key)
            except ValueError:
                continue
            if contained.is_file() and key.startswith(prefix):
                keys.append(key)
        return tuple(sorted(keys))


class PygameAudioService:
    def __init__(
        self,
        requires_gesture: bool,
        sounds: Mapping[str, pygame.mixer.Sound] | None = None,
    ) -> None:
        self.requires_gesture = requires_gesture
        self._sounds = dict(sounds or {})
        self._bus_volumes: dict[AudioBus, float] = {"music": 1.0, "sfx": 1.0}
        self._status = AudioStatus(ready=False, muted=True)

    @property
    def status(self) -> AudioStatus:
        return self._status

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        if self.requires_gesture and not after_user_gesture:
            self._status = AudioStatus(ready=False, muted=True, error_code="gesture_required")
            return self._status
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
        except pygame.error:
            self._status = AudioStatus(ready=False, muted=True, error_code="audio_init_failed")
        else:
            self._status = AudioStatus(ready=True, muted=False)
        return self._status

    def play_cue(self, cue_id: str, bus: AudioBus = "sfx") -> bool:
        if not self._status.ready or self._status.muted:
            return False
        sound = self._sounds.get(cue_id)
        if sound is None:
            return False
        try:
            sound.set_volume(self._bus_volumes[bus])
            channel = sound.play(loops=-1 if bus == "music" else 0)
        except pygame.error:
            return False
        return channel is not None

    def pause(self) -> None:
        if not self._status.ready:
            return
        try:
            pygame.mixer.pause()
        except pygame.error:
            return

    def resume(self) -> None:
        if not self._status.ready:
            return
        try:
            pygame.mixer.unpause()
        except pygame.error:
            return

    def set_bus_volume(self, bus: AudioBus, value: float) -> None:
        self._bus_volumes[bus] = max(0.0, min(1.0, value))


class PygameDisplayService:
    def __init__(self, logical_size: tuple[int, int]) -> None:
        self.logical_size = logical_size
        self._canvas = pygame.Surface(logical_size)
        self._window: pygame.Surface | None = None
        self._fullscreen = False
        self._capabilities = DisplayCapabilities(fullscreen=True)

    @property
    def capabilities(self) -> DisplayCapabilities:
        return self._capabilities

    def create_window(self, logical_size: tuple[int, int], fullscreen: bool) -> pygame.Surface:
        if logical_size != self.logical_size:
            raise ValueError("logical size differs from configured display size")
        if not pygame.display.get_init():
            pygame.display.init()
        flags = pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE
        window_size = (0, 0) if fullscreen else logical_size
        self._window = pygame.display.set_mode(window_size, flags)
        self._fullscreen = fullscreen
        return self._canvas

    def present(self, canvas: pygame.Surface) -> None:
        window = self._window
        if window is None:
            raise RuntimeError("display window has not been created")
        window_width, window_height = window.get_size()
        logical_width, logical_height = self.logical_size
        scale = min(window_width / logical_width, window_height / logical_height)
        scaled_size = (max(1, int(logical_width * scale)), max(1, int(logical_height * scale)))
        offset = ((window_width - scaled_size[0]) // 2, (window_height - scaled_size[1]) // 2)
        window.fill("black")
        window.blit(pygame.transform.smoothscale(canvas, scaled_size), offset)
        pygame.display.flip()

    def set_fullscreen(self, enabled: bool) -> bool:
        if enabled == self._fullscreen and self._window is not None:
            return True
        if not pygame.display.get_init():
            pygame.display.init()
        flags = pygame.FULLSCREEN if enabled else pygame.RESIZABLE
        window_size = (0, 0) if enabled else self.logical_size
        try:
            self._window = pygame.display.set_mode(window_size, flags)
        except pygame.error:
            return False
        self._fullscreen = enabled
        return True


class PygameTimeService:
    def __init__(self) -> None:
        self._clock = pygame.time.Clock()

    def tick(self, target_fps: int) -> float:
        return float(self._clock.tick(target_fps))

    def monotonic_ms(self) -> float:
        return float(pygame.time.get_ticks())

    async def yield_frame(self) -> None:
        await asyncio.sleep(0)


class PygameLifecycleService:
    def consume(self, events: Sequence[pygame.event.Event]) -> tuple[LifecycleEvent, ...]:
        translated: list[LifecycleEvent] = []
        for event in events:
            kind: LifecycleKind | None = None
            if event.type == pygame.QUIT:
                kind = "quit"
            elif event.type == pygame.WINDOWFOCUSLOST:
                kind = "focus_lost"
            elif event.type == pygame.WINDOWFOCUSGAINED:
                kind = "focus_gained"
            if kind is not None:
                translated.append(LifecycleEvent(kind))
        return tuple(translated)


def create_native_services(config: GameConfig) -> PlatformServices:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) / "Windsprig" if local_app_data else Path.home() / "AppData" / "Local" / "Windsprig"
    if not root.is_absolute():
        root = Path.home() / "AppData" / "Local" / "Windsprig"
    return PlatformServices(
        storage=NativeStorage(root),
        audio=PygameAudioService(requires_gesture=False),
        display=PygameDisplayService(config.resolution),
        time=PygameTimeService(),
        lifecycle=PygameLifecycleService(),
        browser=None,
        capabilities=PlatformCapabilities(
            is_web=False,
            persistent_storage=True,
            fullscreen=True,
            gamepads=True,
            audio_requires_gesture=False,
        ),
    )
