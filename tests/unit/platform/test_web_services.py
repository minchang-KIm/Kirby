from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pygame
import pytest

from windsprig.config import GameConfig
from windsprig.platform import (
    AudioService,
    AudioStatus,
    BrowserBridge,
    DisplayCapabilities,
    DisplayService,
    LifecycleService,
    PlatformCapabilities,
    PlatformServices,
    StorageCapabilities,
    StorageService,
    TimeService,
)
from windsprig.platform.native import PygameDisplayService, PygameLifecycleService, PygameTimeService
from windsprig.platform.web import (
    PygbagBrowserBridge,
    WebAudioService,
    WebDisplayService,
    WebStorage,
    create_web_services,
)


@dataclass
class FakeLocalStorage:
    values: dict[str, str] = field(default_factory=dict)

    @property
    def length(self) -> int:
        return len(self.values)

    def getItem(self, key: str) -> str | None:
        return self.values.get(key)

    def setItem(self, key: str, value: str) -> None:
        self.values[key] = value

    def removeItem(self, key: str) -> None:
        self.values.pop(key, None)

    def key(self, index: int) -> str:
        return sorted(self.values)[index]


@dataclass
class FakeElement:
    fullscreen_requests: int = 0

    def requestFullscreen(self) -> None:
        self.fullscreen_requests += 1


@dataclass
class FakeDocument:
    hidden: bool = False
    documentElement: object = field(default_factory=FakeElement)


@dataclass
class FakeLocation:
    search: str = "?foundation_probe=1&message=hello+wind"


class FakeNavigator:
    def getGamepads(self) -> list[object]:
        return []


class FakeWindow:
    def __init__(self) -> None:
        self.localStorage = FakeLocalStorage({"foreign:save.json": "untouched"})
        self.document = FakeDocument()
        self.location = FakeLocation()
        self.navigator = FakeNavigator()


class FailingLocalStorage:
    @property
    def length(self) -> int:
        raise RuntimeError("local storage blocked")

    def getItem(self, _key: str) -> str | None:
        raise RuntimeError("local storage blocked")

    def setItem(self, _key: str, _value: str) -> None:
        raise RuntimeError("local storage blocked")

    def removeItem(self, _key: str) -> None:
        raise RuntimeError("local storage blocked")

    def key(self, _index: int) -> str:
        raise RuntimeError("local storage blocked")


class FailingStorageWindow(FakeWindow):
    def __init__(self) -> None:
        super().__init__()
        self.localStorage = FailingLocalStorage()


class ThrowingFeaturesWindow:
    localStorage = FakeLocalStorage()

    @property
    def document(self) -> object:
        raise RuntimeError("document unavailable")

    @property
    def location(self) -> object:
        raise RuntimeError("location unavailable")

    @property
    def navigator(self) -> object:
        raise RuntimeError("navigator unavailable")


class ThrowingFullscreenElement:
    def requestFullscreen(self) -> None:
        raise RuntimeError("fullscreen denied")


def test_web_storage_roundtrips_namespaced_text_schema() -> None:
    window = FakeWindow()
    storage = WebStorage(PygbagBrowserBridge(window))

    storage.write_text("save_data.json", '{"save_version":2}')

    assert storage.read_text("save_data.json") == '{"save_version":2}'
    assert window.localStorage.values["windsprig:save_data.json"] == '{"save_version":2}'
    assert storage.keys("save") == ("save_data.json",)
    storage.delete("save_data.json")
    assert storage.read_text("save_data.json") is None
    assert window.localStorage.values == {"foreign:save.json": "untouched"}


def test_web_storage_reports_non_atomic_persistent_capabilities() -> None:
    storage = WebStorage(PygbagBrowserBridge(FakeWindow()))

    assert storage.capabilities == StorageCapabilities(persistent=True, atomic_write=False, backup=True)


def test_local_storage_failures_remain_observable_to_save_callers() -> None:
    storage = WebStorage(PygbagBrowserBridge(FailingStorageWindow()))

    with pytest.raises(RuntimeError, match="local storage blocked"):
        storage.read_text("save_data.json")
    with pytest.raises(RuntimeError, match="local storage blocked"):
        storage.write_text("save_data.json", "data")
    with pytest.raises(RuntimeError, match="local storage blocked"):
        storage.delete("save_data.json")
    with pytest.raises(RuntimeError, match="local storage blocked"):
        storage.keys("save")


def test_bridge_reports_browser_features_and_decodes_query() -> None:
    bridge = PygbagBrowserBridge(FakeWindow())

    assert bridge.query_param("foundation_probe") == "1"
    assert bridge.query_param("message") == "hello wind"
    assert bridge.query_param("missing") is None
    assert bridge.document_hidden() is False
    assert bridge.request_fullscreen() is True


def test_bridge_browser_feature_failures_return_protocol_fallbacks() -> None:
    bridge = PygbagBrowserBridge(ThrowingFeaturesWindow())

    assert bridge.query_param("foundation_probe") is None
    assert bridge.document_hidden() is False
    assert bridge.request_fullscreen() is False


def test_bridge_denied_fullscreen_returns_false() -> None:
    window = FakeWindow()
    window.document.documentElement = ThrowingFullscreenElement()

    assert PygbagBrowserBridge(window).request_fullscreen() is False


def test_web_audio_requires_a_gesture_before_mixer_initialization(monkeypatch: pytest.MonkeyPatch) -> None:
    pygame.mixer.quit()
    initializations: list[bool] = []
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", lambda: initializations.append(True))
    audio = WebAudioService()

    assert asyncio.run(audio.initialize()) == AudioStatus(
        ready=False,
        muted=True,
        error_code="gesture_required",
    )
    assert initializations == []
    assert asyncio.run(audio.initialize(after_user_gesture=True)) == AudioStatus(ready=True, muted=False)
    assert initializations == [True]


def test_web_display_requests_browser_fullscreen_but_cannot_exit() -> None:
    window = FakeWindow()
    bridge = PygbagBrowserBridge(window)
    display = WebDisplayService((1280, 720), bridge)
    element = window.document.documentElement
    assert isinstance(element, FakeElement)

    assert display.set_fullscreen(True) is True
    assert element.fullscreen_requests == 1
    assert display.set_fullscreen(False) is False
    assert element.fullscreen_requests == 1


def test_web_display_routes_initial_fullscreen_through_browser_bridge() -> None:
    pygame.display.quit()
    window = FakeWindow()
    display = WebDisplayService((1280, 720), PygbagBrowserBridge(window))
    element = window.document.documentElement
    assert isinstance(element, FakeElement)
    try:
        canvas = display.create_window((1280, 720), fullscreen=True)

        assert canvas.get_size() == (1280, 720)
        assert element.fullscreen_requests == 1
        assert pygame.display.get_surface().get_flags() & pygame.RESIZABLE
    finally:
        pygame.display.quit()


def test_web_display_reuses_native_letterboxing() -> None:
    pygame.display.quit()
    display = WebDisplayService((1280, 720), PygbagBrowserBridge(FakeWindow()))
    assert isinstance(display, PygameDisplayService)
    try:
        canvas = display.create_window((1280, 720), fullscreen=False)
        window = pygame.display.get_surface()
        assert window is not None
        pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        canvas.fill("red")

        display.present(canvas)

        assert window.get_at((400, 20)) == pygame.Color("black")
        center = window.get_at((400, 300))
        assert center.r >= 250 and center.g == 0 and center.b == 0
        assert window.get_at((400, 580)) == pygame.Color("black")
    finally:
        pygame.display.quit()


def test_web_factory_exposes_exact_capabilities_and_shared_services() -> None:
    from windsprig.platform import create_web_services as exported_create_web_services

    services: PlatformServices = create_web_services(GameConfig(), window=FakeWindow())
    storage: StorageService = services.storage
    audio: AudioService = services.audio
    display: DisplayService = services.display
    time: TimeService = services.time
    lifecycle: LifecycleService = services.lifecycle
    browser: BrowserBridge | None = services.browser

    assert exported_create_web_services is create_web_services
    assert (storage, audio, display, time, lifecycle, browser) == (
        services.storage,
        services.audio,
        services.display,
        services.time,
        services.lifecycle,
        services.browser,
    )
    assert isinstance(services.time, PygameTimeService)
    assert isinstance(services.lifecycle, PygameLifecycleService)
    assert services.display.capabilities == DisplayCapabilities(fullscreen=True)
    assert services.capabilities == PlatformCapabilities(
        is_web=True,
        persistent_storage=True,
        fullscreen=True,
        gamepads=True,
        audio_requires_gesture=True,
    )


def test_web_factory_handles_throwing_optional_browser_features() -> None:
    services = create_web_services(GameConfig(), window=ThrowingFeaturesWindow())

    assert services.display.capabilities == DisplayCapabilities(fullscreen=False)
    assert services.capabilities == PlatformCapabilities(
        is_web=True,
        persistent_storage=True,
        fullscreen=False,
        gamepads=False,
        audio_requires_gesture=True,
    )
