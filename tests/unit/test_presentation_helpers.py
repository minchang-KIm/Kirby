"""Behavioral coverage for the legacy presentation helpers retained by the shared runtime."""

from __future__ import annotations

from types import SimpleNamespace

import pygame
import pytest

from windsprig.assets import AssetManager
from windsprig.audio import AudioManager
from windsprig.camera import Camera
from windsprig.hud import HudRenderer


def test_asset_manager_builds_the_complete_tile_and_sprite_catalog() -> None:
    assets = AssetManager(tile_size=32)

    assets.load_all()

    assert set(assets.tiles) == {
        "solid",
        "one_way",
        "hazard",
        "checkpoint",
        "goal",
        "collectible",
    }
    assert set(assets.sprites) == {
        "player_idle",
        "player_attack",
        "enemy_grunt",
        "enemy_brute",
    }
    assert all(surface.get_size() == (32, 32) for surface in assets.tiles.values())
    assert assets.sprites["player_idle"].get_size() == (28, 28)
    assert assets.sprites["enemy_brute"].get_size() == (30, 30)
    assert assets.tiles["solid"].get_at((16, 16))[:3] == (66, 78, 96)
    assert assets.sprites["player_idle"].get_at((14, 14))[:3] == (255, 170, 194)


def test_audio_manager_initializes_an_uninitialized_mixer(monkeypatch: pytest.MonkeyPatch) -> None:
    initialized: list[bool] = []
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", lambda: initialized.append(True))

    audio = AudioManager()

    assert audio.enabled is True
    assert initialized == [True]
    assert audio.play_sfx("jump") is None
    assert audio.play_bgm("world_1") is None


def test_audio_manager_reuses_an_initialized_mixer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: (44_100, -16, 2))
    monkeypatch.setattr(pygame.mixer, "init", lambda: pytest.fail("mixer was initialized twice"))

    assert AudioManager().enabled is True


def test_audio_manager_degrades_to_disabled_when_mixer_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_init() -> None:
        raise pygame.error("no audio device")

    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", fail_init)

    assert AudioManager().enabled is False


def test_camera_smooths_toward_clamped_world_bounds_and_converts_coordinates() -> None:
    camera = Camera(viewport_width=100, viewport_height=80, world_width=300, world_height=200, smoothing=0.5)

    camera.update(-100, -100)
    assert (camera.x, camera.y) == (0.0, 0.0)

    camera.update(1_000, 1_000)
    assert (camera.x, camera.y) == (100.0, 60.0)
    assert camera.world_to_screen(130.4, 81.6) == (30, 22)


def test_camera_remains_at_origin_when_the_world_is_smaller_than_the_viewport() -> None:
    camera = Camera(viewport_width=200, viewport_height=160, world_width=100, world_height=80)

    camera.update(500, 500)

    assert (camera.x, camera.y) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("paused", "lost", "won", "expected"),
    [
        (True, True, True, "Paused - Press Esc"),
        (False, True, True, "You Died - Press R"),
        (False, False, True, "Stage Clear!"),
        (False, False, False, None),
    ],
)
def test_hud_draws_metrics_and_uses_deterministic_overlay_precedence(
    monkeypatch: pytest.MonkeyPatch,
    paused: bool,
    lost: bool,
    won: bool,
    expected: str | None,
) -> None:
    pygame.font.init()
    renderer = HudRenderer()
    screen = pygame.Surface((640, 360), pygame.SRCALPHA)
    overlays: list[str] = []
    monkeypatch.setattr(renderer, "_draw_center_overlay", lambda _screen, text: overlays.append(text))
    simulation = SimpleNamespace(
        player=SimpleNamespace(hp=7, max_hp=10),
        collected_count=2,
        frame_index=42,
        paused=paused,
        lost=lost,
        won=won,
    )

    renderer.draw(screen, simulation)

    assert screen.get_bounding_rect().width > 0
    assert overlays == ([] if expected is None else [expected])


def test_hud_center_overlay_draws_a_centered_panel_and_message() -> None:
    pygame.font.init()
    renderer = HudRenderer()
    screen = pygame.Surface((640, 360), pygame.SRCALPHA)

    renderer._draw_center_overlay(screen, "Paused")

    center = screen.get_at((320, 180))
    border = screen.get_at((320, 135))
    assert center.a > 0
    assert border[:3] == (255, 255, 255)
