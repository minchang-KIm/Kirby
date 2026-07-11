"""Deterministic staging and browser-entry contracts for the Pygbag release path."""

from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from tools import build_web


def test_stage_sources_copies_only_runtime_files_and_probe_module(tmp_path: Path) -> None:
    root = tmp_path
    web = root / "web"
    package = root / "windsprig"
    levels = root / "levels"
    web.mkdir()
    package.mkdir()
    levels.mkdir()
    for name in ("main.py", "template.tmpl", "favicon.png"):
        (web / name).write_bytes(name.encode())
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "feasibility.py").write_text("PROBE = True\n", encoding="utf-8")
    (package / "content.json").write_text("{}", encoding="utf-8")
    (package / ".env").write_text("SECRET=value", encoding="utf-8")
    (package / "token.pem").write_text("secret", encoding="utf-8")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "cached.pyc").write_bytes(b"cache")
    (levels / "level.json").write_text("{}", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_game.py").write_text("", encoding="utf-8")
    stage = root / "build" / "web-stage"

    build_web.stage_sources(root, stage, probe=True)

    staged = {
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file()
    }
    assert staged == {
        "favicon.png",
        "levels/level.json",
        "main.py",
        "template.tmpl",
        "windsprig/__init__.py",
        "windsprig/content.json",
        "windsprig/feasibility.py",
    }


def test_version_drift_is_rejected_by_the_pinned_build(monkeypatch: pytest.MonkeyPatch) -> None:
    versions = {"pygbag": "0.9.4", "pygame-ce": "2.5.7"}
    monkeypatch.setattr(build_web, "version", versions.__getitem__)

    with pytest.raises(SystemExit, match="pygbag version drift"):
        build_web.verify_toolchain_versions()


def test_favicon_generation_is_byte_deterministic_and_original(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    build_web.generate_favicon(first)
    build_web.generate_favicon(second)

    assert first.read_bytes() == second.read_bytes()
    image = pygame.image.load(first)
    assert image.get_size() == (64, 64)
    assert image.get_at((32, 32))[:3] == (121, 224, 180)
    assert image.get_at((45, 17))[:3] == (246, 201, 93)


def test_compressed_transfer_measurement_is_stable_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_bytes(b"z" * 500)
    (tmp_path / "a.txt").write_bytes(b"a" * 500)

    first = build_web.measure_output(tmp_path)
    second = build_web.measure_output(tmp_path)

    assert first == second
    assert first["files"] == ["a.txt", "z.txt"]
    assert first["compressed_bytes"] > 0
    assert first["uncompressed_bytes"] == 1000


def test_browser_entry_and_template_keep_the_real_loader_and_runtime_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    entry = (root / "web" / "main.py").read_text(encoding="utf-8")
    template = (root / "web" / "template.tmpl").read_text(encoding="utf-8")

    assert "GameApp" in entry
    assert "create_web_services" in entry
    assert "create_foundation_screen_factory" in entry
    assert "asyncio.run(main())" in entry
    assert "pygame.quit" not in entry
    assert "SystemExit" not in entry
    assert "{{cookiecutter.cdn}}pythons.js" in template
    assert "BrowserFS/2.0.0/browserfs.min.js" in template
    assert "async def custom_site()" in template
    assert "function custom_onload" in template
    assert 'id="canvas"' in template
    assert "Loading Windsprig…" in template
    assert "physical keyboard or compatible gamepad" in template
    assert "<noscript>" in template
