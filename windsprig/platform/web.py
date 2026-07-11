from __future__ import annotations

from typing import Protocol, cast
from urllib.parse import parse_qs

import pygame

from windsprig.config import GameConfig
from windsprig.platform.native import (
    PygameAudioService,
    PygameDisplayService,
    PygameLifecycleService,
    PygameTimeService,
)
from windsprig.platform.services import (
    AudioStatus,
    BrowserBridge,
    DisplayCapabilities,
    PlatformCapabilities,
    PlatformServices,
    StorageCapabilities,
)


def _optional_attribute(value: object | None, name: str) -> object | None:
    if value is None:
        return None
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def _required_attribute(value: object, name: str) -> object:
    return cast(object, getattr(value, name))


class _LocalStorage(Protocol):
    @property
    def length(self) -> int:
        raise NotImplementedError

    def getItem(self, key: str) -> object | None:
        raise NotImplementedError

    def setItem(self, key: str, value: str) -> None:
        raise NotImplementedError

    def removeItem(self, key: str) -> None:
        raise NotImplementedError

    def key(self, index: int) -> object | None:
        raise NotImplementedError


class _WindowWithLocalStorage(Protocol):
    localStorage: _LocalStorage


class _AudioStatusElement(Protocol):
    textContent: str
    hidden: bool


class PygbagBrowserBridge:
    def __init__(self, window: object) -> None:
        self.window = window

    def _local_storage(self) -> _LocalStorage:
        return cast(_WindowWithLocalStorage, self.window).localStorage

    def local_storage_get(self, key: str) -> str | None:
        value = self._local_storage().getItem(key)
        return None if value is None else str(value)

    def local_storage_set(self, key: str, value: str) -> None:
        self._local_storage().setItem(key, value)

    def local_storage_remove(self, key: str) -> None:
        self._local_storage().removeItem(key)

    def local_storage_keys(self, prefix: str) -> tuple[str, ...]:
        storage = self._local_storage()
        keys: list[str] = []
        for index in range(int(storage.length)):
            value = storage.key(index)
            if value is None:
                continue
            key = str(value)
            if key.startswith(prefix):
                keys.append(key)
        return tuple(sorted(keys))

    def query_param(self, name: str) -> str | None:
        location = _optional_attribute(self.window, "location")
        search = _optional_attribute(location, "search")
        if search is None:
            return None
        try:
            query = parse_qs(str(search).removeprefix("?"))
        except Exception:
            return None
        values = query.get(name)
        return values[0] if values else None

    def request_fullscreen(self) -> bool:
        document = _optional_attribute(self.window, "document")
        element = _optional_attribute(document, "documentElement")
        request = _optional_attribute(element, "requestFullscreen")
        if not callable(request):
            return False
        try:
            request()
        except Exception:
            return False
        return True

    def document_hidden(self) -> bool:
        document = _optional_attribute(self.window, "document")
        hidden = _optional_attribute(document, "hidden")
        if hidden is None:
            return False
        try:
            return bool(hidden)
        except Exception:
            return False

    def publish_audio_status(self, status: AudioStatus) -> None:
        if status.error_code == "gesture_required":
            text = "Audio: click the game to enable"
        elif status.ready and not status.muted:
            text = "Audio: ready"
        else:
            text = "Audio: muted"
        document = _optional_attribute(self.window, "document")
        get_element = _optional_attribute(document, "getElementById")
        if not callable(get_element):
            return
        try:
            element = get_element("audio-status")
            if element is None:
                return
            status_element = cast(_AudioStatusElement, element)
            status_element.textContent = text
            status_element.hidden = False
        except Exception:
            return

    def fullscreen_available(self) -> bool:
        document = _optional_attribute(self.window, "document")
        element = _optional_attribute(document, "documentElement")
        return callable(_optional_attribute(element, "requestFullscreen"))

    def gamepads_available(self) -> bool:
        navigator = _optional_attribute(self.window, "navigator")
        return callable(_optional_attribute(navigator, "getGamepads"))


class WebStorage:
    def __init__(self, bridge: BrowserBridge) -> None:
        self.bridge = bridge
        self._capabilities = StorageCapabilities(persistent=True, atomic_write=False, backup=True)

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    def read_text(self, key: str) -> str | None:
        return self.bridge.local_storage_get(f"windsprig:{key}")

    def write_text(self, key: str, value: str) -> None:
        self.bridge.local_storage_set(f"windsprig:{key}", value)

    def delete(self, key: str) -> None:
        self.bridge.local_storage_remove(f"windsprig:{key}")

    def keys(self, prefix: str) -> tuple[str, ...]:
        namespace = "windsprig:"
        return tuple(
            key.removeprefix(namespace)
            for key in self.bridge.local_storage_keys(namespace + prefix)
        )


class WebAudioService(PygameAudioService):
    def __init__(self, bridge: BrowserBridge) -> None:
        super().__init__(requires_gesture=True)
        self.bridge = bridge
        self._status = AudioStatus(ready=False, muted=True, error_code="gesture_required")
        self.bridge.publish_audio_status(self._status)

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        if not after_user_gesture:
            self._status = AudioStatus(ready=False, muted=True, error_code="gesture_required")
        else:
            self._status = await super().initialize(after_user_gesture=True)
        self.bridge.publish_audio_status(self._status)
        return self._status


class WebDisplayService(PygameDisplayService):
    def __init__(self, logical_size: tuple[int, int], bridge: PygbagBrowserBridge) -> None:
        super().__init__(logical_size)
        self.bridge = bridge
        self._capabilities = DisplayCapabilities(fullscreen=bridge.fullscreen_available())

    def create_window(self, logical_size: tuple[int, int], fullscreen: bool) -> pygame.Surface:
        canvas = super().create_window(logical_size, fullscreen=False)
        if fullscreen:
            self.set_fullscreen(True)
        return canvas

    def set_fullscreen(self, enabled: bool) -> bool:
        if not enabled:
            return False
        requested = self.bridge.request_fullscreen()
        if requested:
            self._fullscreen = True
        return requested


def create_web_services(config: GameConfig, window: object | None = None) -> PlatformServices:
    if window is None:
        import platform

        window = _required_attribute(platform, "window")
    bridge = PygbagBrowserBridge(window)
    fullscreen = bridge.fullscreen_available()
    gamepads = bridge.gamepads_available()
    return PlatformServices(
        storage=WebStorage(bridge),
        audio=WebAudioService(bridge),
        display=WebDisplayService(config.resolution, bridge),
        time=PygameTimeService(),
        lifecycle=PygameLifecycleService(),
        browser=bridge,
        capabilities=PlatformCapabilities(
            is_web=True,
            persistent_storage=True,
            fullscreen=fullscreen,
            gamepads=gamepads,
            audio_requires_gesture=True,
        ),
    )
