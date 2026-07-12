from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

import pygame
import pytest

from windsprig.config import GameConfig
from windsprig.platform import (
    AudioService,
    AudioStatus,
    BrowserBridge,
    DisplayCapabilities,
    DisplayService,
    LifecycleEvent,
    LifecycleService,
    PlatformCapabilities,
    PlatformServices,
    StorageCapabilities,
    StorageService,
    TimeService,
)
from windsprig.platform.native import (
    NativeStorage,
    PygameAudioService,
    PygameDisplayService,
    PygameLifecycleService,
    PygameTimeService,
    create_native_services,
)


def test_native_storage_writes_under_local_app_data_atomically(tmp_path: Path) -> None:
    storage = NativeStorage(tmp_path / "Windsprig")
    storage.write_text("save_data.json", '{"save_version": 2}')
    assert storage.read_text("save_data.json") == '{"save_version": 2}'
    assert (tmp_path / "Windsprig" / "save_data.json").is_file()
    assert not list((tmp_path / "Windsprig").glob("*.tmp"))
    assert storage.keys("save") == ("save_data.json",)


def test_native_storage_rejects_escape_from_root(tmp_path: Path) -> None:
    storage = NativeStorage(tmp_path / "Windsprig")
    try:
        storage.write_text("../outside.json", "bad")
    except ValueError as error:
        assert "storage root" in str(error)
    else:
        raise AssertionError("path traversal was accepted")


def test_native_storage_rejects_symlink_escape_from_root(tmp_path: Path) -> None:
    root = tmp_path / "Windsprig"
    outside = tmp_path / "outside"
    outside.mkdir()
    storage = NativeStorage(root)
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(ValueError, match="storage root"):
        storage.write_text("linked/outside.json", "bad")

    assert not (outside / "outside.json").exists()


def test_native_storage_does_not_list_file_symlinks_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "Windsprig"
    outside = tmp_path / "outside.json"
    outside.write_text("secret", encoding="utf-8")
    storage = NativeStorage(root)
    try:
        (root / "linked.json").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    assert storage.keys("") == ()


def test_native_storage_removes_temporary_file_when_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage = NativeStorage(tmp_path / "Windsprig")
    storage.write_text("save_data.json", "old data")

    def fail_replace(_source: os.PathLike[str], _destination: os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        storage.write_text("save_data.json", "new data")

    assert storage.read_text("save_data.json") == "old data"
    assert not list(storage.root.glob("*.tmp"))


def test_native_storage_canonicalizes_relative_root_once(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    storage = NativeStorage(Path("Windsprig"))
    storage.write_text("save_data.json", "stable")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert storage.root == (tmp_path / "Windsprig").resolve()
    assert storage.read_text("save_data.json") == "stable"
    assert storage.keys("save") == ("save_data.json",)


def test_native_factory_uses_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    services = create_native_services(GameConfig())
    assert services.capabilities.is_web is False
    assert services.storage.capabilities.atomic_write is True
    assert services.storage.root == tmp_path / "Windsprig"
    asyncio.run(services.time.yield_frame())


def test_native_factory_exposes_exact_native_capabilities(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    services = create_native_services(GameConfig())
    assert services.browser is None
    assert services.storage.capabilities == StorageCapabilities(True, True, True)
    assert services.display.capabilities == DisplayCapabilities(fullscreen=True)
    assert services.capabilities == PlatformCapabilities(
        is_web=False,
        persistent_storage=True,
        fullscreen=True,
        gamepads=True,
        audio_requires_gesture=False,
    )


def test_native_factory_ignores_relative_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", "relative-app-data")
    monkeypatch.setattr(Path, "home", classmethod(lambda _path_type: home))

    services = create_native_services(GameConfig())

    assert services.storage.root == home / "AppData" / "Local" / "Windsprig"
    assert not (tmp_path / "relative-app-data").exists()


def test_native_service_implementations_match_platform_protocols(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    services: PlatformServices = create_native_services(GameConfig())
    storage: StorageService = services.storage
    audio: AudioService = services.audio
    display: DisplayService = services.display
    time: TimeService = services.time
    lifecycle: LifecycleService = services.lifecycle
    browser: BrowserBridge | None = services.browser
    assert (storage, audio, display, time, lifecycle, browser) == (
        services.storage,
        services.audio,
        services.display,
        services.time,
        services.lifecycle,
        None,
    )


def test_audio_initializes_and_plays_only_known_cues() -> None:
    pygame.mixer.quit()
    try:
        pygame.mixer.init()
        sound = pygame.mixer.Sound(buffer=b"\x00" * 256)
        audio = PygameAudioService(requires_gesture=False, sounds={"known": sound})
        assert audio.play_cue("known") is False

        assert asyncio.run(audio.initialize()) == AudioStatus(ready=True, muted=False)
        audio.set_bus_volume("sfx", 0.25)
        assert audio.play_cue("missing") is False
        assert audio.play_cue("known") is True
        assert sound.get_volume() == pytest.approx(0.25, abs=0.01)
        audio.pause()
        audio.resume()
    finally:
        pygame.mixer.quit()


def test_audio_initialization_failure_becomes_muted_status(monkeypatch: pytest.MonkeyPatch) -> None:
    pygame.mixer.quit()
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    def fail_init() -> None:
        raise pygame.error("no audio device")

    monkeypatch.setattr(pygame.mixer, "init", fail_init)
    audio = PygameAudioService(requires_gesture=False)
    assert asyncio.run(audio.initialize()) == AudioStatus(
        ready=False,
        muted=True,
        error_code="audio_init_failed",
    )
    assert audio.play_cue("missing") is False


def test_audio_can_require_a_user_gesture_before_initialization() -> None:
    pygame.mixer.quit()
    audio = PygameAudioService(requires_gesture=True)
    assert asyncio.run(audio.initialize()) == AudioStatus(
        ready=False,
        muted=True,
        error_code="gesture_required",
    )
    assert pygame.mixer.get_init() is None


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.01, 1.01, "0.5"])
def test_audio_bus_volume_rejects_invalid_values_without_changing_the_previous_volume(value: object) -> None:
    pygame.mixer.quit()
    try:
        pygame.mixer.init()
        sound = pygame.mixer.Sound(buffer=b"\x00" * 256)
        audio = PygameAudioService(requires_gesture=False, sounds={"known": sound})
        assert asyncio.run(audio.initialize()).ready
        audio.set_bus_volume("sfx", 0.25)

        with pytest.raises((TypeError, ValueError)):
            audio.set_bus_volume("sfx", value)  # type: ignore[arg-type]

        assert audio.play_cue("known")
        assert sound.get_volume() == pytest.approx(0.25, abs=0.01)
        assert math.isfinite(sound.get_volume())
    finally:
        pygame.mixer.quit()


def test_audio_service_rejects_unknown_buses_before_playback_or_volume_mutation() -> None:
    audio = PygameAudioService(requires_gesture=False)

    with pytest.raises(ValueError, match="audio bus"):
        audio.set_bus_volume("voice", 0.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="audio bus"):
        audio.play_cue("known", "voice")  # type: ignore[arg-type]


def test_user_mute_and_focus_pause_are_visible_and_restore_the_previous_mute_state() -> None:
    pygame.mixer.quit()
    try:
        pygame.mixer.init()
        sound = pygame.mixer.Sound(buffer=b"\x00" * 256)
        audio = PygameAudioService(requires_gesture=False, sounds={"known": sound})
        assert asyncio.run(audio.initialize()) == AudioStatus(ready=True, muted=False)

        audio.set_muted(True)
        assert audio.status == AudioStatus(ready=True, muted=True)
        assert audio.play_cue("known") is False
        audio.pause()
        assert audio.status == AudioStatus(ready=True, muted=True, error_code="focus_lost")
        audio.resume()
        assert audio.status == AudioStatus(ready=True, muted=True)

        audio.set_muted(False)
        assert audio.status == AudioStatus(ready=True, muted=False)
        assert audio.play_cue("known") is True
        with pytest.raises(TypeError, match="muted must be a boolean"):
            audio.set_muted(1)  # type: ignore[arg-type]
    finally:
        pygame.mixer.quit()


def test_display_presents_a_letterboxed_logical_canvas() -> None:
    pygame.display.quit()
    display = PygameDisplayService((1280, 720))
    try:
        canvas = display.create_window((1280, 720), fullscreen=False)
        window = pygame.display.get_surface()
        assert window is not None
        assert window.get_flags() & pygame.RESIZABLE
        pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        assert canvas.get_size() == (1280, 720)
        canvas.fill("red")

        display.present(canvas)

        canvas_center = canvas.get_at((640, 360))
        assert canvas_center.r == 255 and canvas_center.g == 0 and canvas_center.b == 0
        assert window.get_at((400, 20)) == pygame.Color("black")
        center = window.get_at((400, 300))
        assert center.r >= 250 and center.g == 0 and center.b == 0
        assert window.get_at((400, 580)) == pygame.Color("black")
    finally:
        pygame.display.quit()


def test_display_toggles_fullscreen_headlessly() -> None:
    pygame.display.quit()
    display = PygameDisplayService((1280, 720))
    try:
        display.create_window((1280, 720), fullscreen=False)
        assert display.set_fullscreen(True) is True
        assert pygame.display.get_surface().get_flags() & pygame.FULLSCREEN
        assert display.set_fullscreen(False) is True
        assert pygame.display.get_surface().get_flags() & pygame.RESIZABLE
    finally:
        pygame.display.quit()


def test_display_rejects_a_logical_size_that_differs_from_configuration() -> None:
    pygame.display.quit()
    display = PygameDisplayService((1280, 720))
    with pytest.raises(ValueError, match="logical size"):
        display.create_window((640, 360), fullscreen=False)
    assert pygame.display.get_surface() is None


def test_display_requests_desktop_resolution_for_fullscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    pygame.display.quit()
    requested_sizes: list[tuple[int, int]] = []
    set_mode = pygame.display.set_mode

    def record_set_mode(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
        requested_sizes.append(size)
        return set_mode(size, flags)

    monkeypatch.setattr(pygame.display, "set_mode", record_set_mode)
    display = PygameDisplayService((1280, 720))
    try:
        display.create_window((1280, 720), fullscreen=False)
        assert display.set_fullscreen(True) is True
        assert requested_sizes[-1] == (0, 0)
    finally:
        pygame.display.quit()


def test_lifecycle_maps_quit_and_focus_events_in_order() -> None:
    lifecycle = PygameLifecycleService()
    events = (
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE),
        pygame.event.Event(pygame.WINDOWFOCUSLOST),
        pygame.event.Event(pygame.WINDOWFOCUSGAINED),
        pygame.event.Event(pygame.QUIT),
    )
    assert lifecycle.consume(events) == (
        LifecycleEvent("focus_lost"),
        LifecycleEvent("focus_gained"),
        LifecycleEvent("quit"),
    )


def test_time_service_reports_float_milliseconds() -> None:
    time = PygameTimeService()
    assert isinstance(time.tick(0), float)
    assert isinstance(time.monotonic_ms(), float)


def test_time_service_yields_to_the_event_loop() -> None:
    time = PygameTimeService()

    async def observe_yield() -> None:
        yielded = False

        async def mark_yielded() -> None:
            nonlocal yielded
            yielded = True

        task = asyncio.create_task(mark_yielded())
        try:
            await time.yield_frame()
            assert yielded is True
            assert task.done()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(observe_yield())
