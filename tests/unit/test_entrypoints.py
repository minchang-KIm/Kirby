from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

import windsprig.__main__ as entrypoint
import windsprig.game as legacy_game
from windsprig.config import GameConfig


def test_native_entrypoint_exposes_async_startup_contract() -> None:
    assert inspect.iscoroutinefunction(entrypoint.run_native)


async def test_native_entrypoint_owns_pygame_init_window_and_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    config = GameConfig()

    class FakeDisplay:
        def create_window(self, size: tuple[int, int], fullscreen: bool) -> None:
            calls.append(("window", size, fullscreen))

    services = SimpleNamespace(display=FakeDisplay())
    factory = object()

    class FakeApp:
        def __init__(self, app_config: object, app_services: object, app_factory: object) -> None:
            calls.append(("app", app_config, app_services, app_factory))

        async def run(self) -> int:
            calls.append("run")
            return 7

    monkeypatch.setattr(entrypoint.pygame, "init", lambda: calls.append("init"))
    monkeypatch.setattr(entrypoint.pygame, "quit", lambda: calls.append("quit"))
    monkeypatch.setattr(entrypoint, "GameConfig", lambda: config)
    monkeypatch.setattr(entrypoint, "create_native_services", lambda _config: services)
    monkeypatch.setattr(
        entrypoint,
        "create_foundation_screen_factory",
        lambda _config, _services, _now: factory,
    )
    monkeypatch.setattr(entrypoint, "GameApp", FakeApp)

    result = await entrypoint.run_native()

    assert result == 7
    assert calls[0] == "init"
    assert ("window", config.resolution, config.fullscreen) in calls
    assert calls[-1] == "quit"


def test_legacy_run_game_delegates_to_the_native_main_without_a_second_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(entrypoint, "main", lambda: 23)

    assert legacy_game.run_game() == 23
