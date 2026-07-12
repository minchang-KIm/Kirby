"""Deterministic staging and browser-entry contracts for the Pygbag release path."""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pygame
import pytest

from tools import build_web


def test_stage_sources_copies_only_runtime_files_and_probe_module(tmp_path: Path) -> None:
    root = tmp_path
    web = root / "web"
    package = root / "windsprig"
    levels = root / "levels"
    assets = root / "assets"
    web.mkdir()
    package.mkdir()
    levels.mkdir()
    (assets / "generated" / "ui").mkdir(parents=True)
    (assets / "fonts").mkdir()
    for name in ("main.py", "runtime-manifest.json", "template.tmpl", "favicon.png"):
        (web / name).write_bytes(name.encode())
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "feasibility.py").write_text("PROBE = True\n", encoding="utf-8")
    (package / "content.json").write_text("{}", encoding="utf-8")
    (package / ".env").write_text("SECRET=value", encoding="utf-8")
    (package / "token.pem").write_text("secret", encoding="utf-8")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "cached.pyc").write_bytes(b"cache")
    (levels / "level.json").write_text("{}", encoding="utf-8")
    (assets / "generated" / "ui" / "icons.png").write_bytes(b"icons")
    (assets / "fonts" / "font.ttf").write_bytes(b"font")
    (assets / "LICENSES.md").write_text("# Licenses\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_game.py").write_text("", encoding="utf-8")
    stage = root / "build" / "web-stage"

    build_web.stage_sources(root, stage, probe=True)

    staged = {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()}
    assert staged == {
        "assets/LICENSES.md",
        "assets/fonts/font.ttf",
        "assets/generated/ui/icons.png",
        "favicon.png",
        "levels/level.json",
        "main.py",
        "runtime-manifest.json",
        "template.tmpl",
        "windsprig/__init__.py",
        "windsprig/_build_flags.py",
        "windsprig/content.json",
        "windsprig/feasibility.py",
    }
    assert (stage / "windsprig" / "_build_flags.py").read_text(encoding="utf-8") == (
        '"""Generated browser artifact capabilities; do not edit."""\n\nFOUNDATION_PROBE_AVAILABLE = True\n'
    )


def test_non_probe_staging_overrides_source_capability_to_false(tmp_path: Path) -> None:
    root = tmp_path
    web = root / "web"
    package = root / "windsprig"
    levels = root / "levels"
    assets = root / "assets"
    web.mkdir()
    package.mkdir()
    levels.mkdir()
    assets.mkdir()
    for name in ("main.py", "runtime-manifest.json", "template.tmpl", "favicon.png"):
        (web / name).write_bytes(name.encode())
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "_build_flags.py").write_text(
        "FOUNDATION_PROBE_AVAILABLE = True\n",
        encoding="utf-8",
    )

    stage = root / "build" / "web-stage"
    build_web.stage_sources(root, stage, probe=False)

    assert (stage / "windsprig" / "_build_flags.py").read_text(encoding="utf-8") == (
        '"""Generated browser artifact capabilities; do not edit."""\n\nFOUNDATION_PROBE_AVAILABLE = False\n'
    )


@pytest.mark.parametrize("probe", [False, True])
def test_probe_marker_is_verified_in_both_packaged_source_manifests(
    tmp_path: Path,
    probe: bool,
) -> None:
    output = tmp_path / "web"
    output.mkdir()
    member = "assets/windsprig/_build_flags.py"
    marker = (
        b'"""Generated browser artifact capabilities; do not edit."""\n\n'
        + f"FOUNDATION_PROBE_AVAILABLE = {probe!r}\n".encode()
    )
    with zipfile.ZipFile(output / "game.apk", "w") as archive:
        archive.writestr(member, marker)
    with tarfile.open(output / "game.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo(member)
        info.size = len(marker)
        archive.addfile(info, io.BytesIO(marker))

    build_web.verify_probe_artifacts(output, probe=probe)

    with tarfile.open(output / "game.tar.gz", "w:gz") as archive:
        mismatched_marker = marker.replace(str(probe).encode(), str(not probe).encode())
        info = tarfile.TarInfo(member)
        info.size = len(mismatched_marker)
        archive.addfile(info, io.BytesIO(mismatched_marker))
    with pytest.raises(SystemExit, match="probe capability mismatch"):
        build_web.verify_probe_artifacts(output, probe=probe)


def test_cleanup_removes_only_an_exact_allowlisted_relative_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    target = root / "build" / "web-stage"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    build_web._remove_build_target(root, Path("build/web-stage"))

    assert not target.exists()


@pytest.mark.parametrize(
    "relative_target",
    [Path("../outside"), Path("build"), Path("build/not-web-stage")],
)
def test_cleanup_rejects_non_allowlisted_and_lexically_escaping_targets(
    tmp_path: Path,
    relative_target: Path,
) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="allowlisted relative build target"):
        build_web._remove_build_target(root, relative_target)

    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_cleanup_rejects_absolute_targets(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(ValueError, match="allowlisted relative build target"):
        build_web._remove_build_target(root, root / "build" / "web-stage")


def test_cleanup_rejects_a_real_symlinked_ancestor_without_touching_destination(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    target = outside / "web-stage"
    target.mkdir(parents=True)
    survivor = target / "keep.txt"
    survivor.write_text("keep", encoding="utf-8")
    link = root / "build"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        if os.name != "nt":
            pytest.skip(f"directory symlinks unavailable: {error}")
        junction = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            check=False,
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip(f"directory links unavailable: {error}; {junction.stderr}")

    try:
        with pytest.raises(ValueError, match="link or reparse point"):
            build_web._remove_build_target(root, Path("build/web-stage"))

        assert survivor.read_text(encoding="utf-8") == "keep"
    finally:
        if getattr(os.path, "isjunction", lambda _path: False)(link):
            os.rmdir(link)
        elif link.is_symlink():
            link.unlink()


def test_cleanup_rejects_a_monkeypatched_junction_ancestor_before_rmtree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    target = root / "dist" / "web"
    target.mkdir(parents=True)
    rmtree_calls: list[Path] = []
    original_isjunction = getattr(os.path, "isjunction", lambda _path: False)

    def fake_isjunction(path: object) -> bool:
        candidate = Path(path)
        return candidate == root / "dist" or bool(original_isjunction(path))

    monkeypatch.setattr(os.path, "isjunction", fake_isjunction, raising=False)
    monkeypatch.setattr(build_web.shutil, "rmtree", lambda path: rmtree_calls.append(Path(path)))

    with pytest.raises(ValueError, match="link or reparse point"):
        build_web._remove_build_target(root, Path("dist/web"))

    assert rmtree_calls == []


def test_cleanup_rejects_a_resolved_escape_before_rmtree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    target = root / "build" / "web-stage"
    target.mkdir(parents=True)
    escaped = tmp_path / "escaped" / "web-stage"
    original_resolve = Path.resolve
    rmtree_calls: list[Path] = []

    def fake_resolve(path: Path, strict: bool = False) -> Path:
        if path == target:
            return escaped
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    monkeypatch.setattr(build_web.shutil, "rmtree", lambda path: rmtree_calls.append(Path(path)))

    with pytest.raises(ValueError, match="resolves outside repository root"):
        build_web._remove_build_target(root, Path("build/web-stage"))

    assert rmtree_calls == []


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
    assert "runtime/browserfs/2.0.0/browserfs.min.js" in template
    assert "async def custom_site()" in template
    assert 'platform.fopen("{{cookiecutter.archive}}.apk", "rb")' in template
    assert "PurePosixPath(member.filename)" in template
    assert "member_path.is_absolute()" in template
    assert '".." in member_path.parts' in template
    assert 'platform.fopen("{{cookiecutter.archive}}.tar.gz", "rb")' not in template
    assert "function custom_onload" in template
    assert 'id="canvas"' in template
    assert 'id="audio-status"' in template
    assert 'role="status"' in template
    assert "Loading Windsprig…" in template
    assert "physical keyboard or compatible gamepad" in template
    assert "<noscript>" in template
