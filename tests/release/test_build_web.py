"""Release contracts for reproducible Pygbag staging."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from tools import build_web
from tools.build_web import attach_release_manifest
from tools.release_common import BuildIdentity
from tools.web_runtime import RuntimeManifest

_REAL_SUBPROCESS_RUN = subprocess.run


def _make_directory_link(link: Path, target: Path) -> None:
    """Create a real directory symlink, falling back to a Windows junction."""
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        if os.name != "nt":
            pytest.skip(f"directory links unavailable: {error}")
        junction = _REAL_SUBPROCESS_RUN(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip(f"directory links unavailable: {error}; {junction.stderr}")


def _remove_directory_link(link: Path) -> None:
    if getattr(os.path, "isjunction", lambda _path: False)(link):
        os.rmdir(link)
    elif link.is_symlink():
        link.unlink()


def test_attach_release_manifest_indexes_staged_runtime_deterministically(
    tmp_path: Path,
) -> None:
    output = tmp_path / "web"
    (output / "assets").mkdir(parents=True)
    (output / "index.html").write_text("<canvas id='canvas'></canvas>", encoding="utf-8")
    (output / "windsprig.apk").write_bytes(b"game")
    (output / "assets" / "runtime.js").write_text("start();\n", encoding="utf-8")
    (output / "build-info.json").write_text("stale", encoding="utf-8")
    identity = BuildIdentity("1.0.0", "b" * 40, "web")

    manifest_path = attach_release_manifest(output, identity)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_path == output / "build-info.json"
    assert manifest == {
        "commit_sha": "b" * 40,
        "files": ["assets/runtime.js", "index.html", "windsprig.apk"],
        "target": "web",
        "version": "1.0.0",
    }


def test_attach_release_manifest_requires_pygbag_entry_and_application_archive(
    tmp_path: Path,
) -> None:
    output = tmp_path / "web"
    output.mkdir()
    identity = BuildIdentity("1.0.0", "c" * 40, "web")

    with pytest.raises(FileNotFoundError, match="index.html"):
        attach_release_manifest(output, identity)

    (output / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="application archive"):
        attach_release_manifest(output, identity)


def test_attach_release_manifest_rejects_wrong_boundary_types(tmp_path: Path) -> None:
    identity = BuildIdentity("1.0.0", "d" * 40, "web")

    with pytest.raises(TypeError, match="output"):
        attach_release_manifest(cast(Path, "web"), identity)
    with pytest.raises(TypeError, match="identity"):
        attach_release_manifest(tmp_path, cast(BuildIdentity, object()))


def test_attach_release_manifest_rejects_a_non_web_identity(tmp_path: Path) -> None:
    output = tmp_path / "web"
    output.mkdir()
    (output / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
    (output / "windsprig.apk").write_bytes(b"game")

    with pytest.raises(ValueError, match="identity target must be web"):
        attach_release_manifest(
            output,
            BuildIdentity("1.0.0", "d" * 40, "source"),
        )


def test_attach_release_manifest_rejects_a_directory_link_before_descent(
    tmp_path: Path,
) -> None:
    output = tmp_path / "web"
    output.mkdir()
    (output / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
    (output / "windsprig.apk").write_bytes(b"game")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = output / "linked-assets"
    _make_directory_link(link, outside)

    try:
        with pytest.raises(ValueError, match="link or reparse point"):
            attach_release_manifest(
                output,
                BuildIdentity("1.0.0", "d" * 40, "web"),
            )

        assert not (output / "build-info.json").exists()
    finally:
        _remove_directory_link(link)


def test_attach_release_manifest_uses_a_no_follow_walker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "web"
    output.mkdir()
    (output / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
    (output / "windsprig.apk").write_bytes(b"game")

    def fail_rglob(_path: Path, _pattern: str) -> object:
        raise AssertionError("Path.rglob must not inspect release artifacts")

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    attach_release_manifest(
        output,
        BuildIdentity("1.0.0", "d" * 40, "web"),
    )


def test_attach_release_manifest_rejects_child_swapped_after_lstat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "web"
    assets = output / "assets"
    assets.mkdir(parents=True)
    (output / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
    (output / "windsprig.apk").write_bytes(b"game")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    backup = output / "assets-backup"
    original_lstat = Path.lstat
    swapped = False

    def swap_after_lstat(path: Path) -> os.stat_result:
        nonlocal swapped
        state = original_lstat(path)
        if path == assets and not swapped:
            swapped = True
            assets.rename(backup)
            _make_directory_link(assets, outside)
        return state

    monkeypatch.setattr(Path, "lstat", swap_after_lstat)
    try:
        with pytest.raises(ValueError, match="identity changed|link or reparse point"):
            attach_release_manifest(
                output,
                BuildIdentity("1.0.0", "d" * 40, "web"),
            )

        assert not (output / "build-info.json").exists()
    finally:
        _remove_directory_link(assets)
        backup.rename(assets)


def _patch_build_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
) -> list[list[str]]:
    """Replace external tooling while retaining real copy, report, and manifest behavior."""
    (root / "web").mkdir(parents=True)
    commands: list[list[str]] = []
    monkeypatch.setattr(build_web, "ROOT", root)
    monkeypatch.setattr(build_web, "verify_toolchain_versions", lambda: None)
    monkeypatch.setattr(build_web, "generate_favicon", lambda _path: None)
    monkeypatch.setattr(
        build_web,
        "inspect_runtime_source",
        lambda _root: SimpleNamespace(sha256="e" * 64, source_commit="a" * 40),
    )

    def fake_stage_sources(_root: Path, stage: Path, *, probe: bool) -> None:
        del probe
        stage.mkdir(parents=True)

    def fake_pygbag(command: list[str], *, cwd: Path, check: bool) -> None:
        assert cwd == root
        assert check is True
        commands.append(command)
        built = root / "build" / "web-stage" / "build" / "web"
        built.mkdir(parents=True)
        (built / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
        (built / "runtime.js").write_text("start();\n", encoding="utf-8")
        (built / "windsprig.apk").write_bytes(b"game")

    monkeypatch.setattr(build_web, "stage_sources", fake_stage_sources)
    monkeypatch.setattr(subprocess, "run", fake_pygbag)
    monkeypatch.setattr(build_web, "_normalize_archives", lambda _output: None)
    monkeypatch.setattr(build_web, "verify_probe_artifacts", lambda _output, *, probe: None)
    monkeypatch.setattr(
        build_web,
        "load_runtime_manifest",
        lambda _path: RuntimeManifest(1, "test-runtime", (), "f" * 64),
        raising=False,
    )
    monkeypatch.setattr(
        build_web,
        "stage_runtime_assets",
        lambda _manifest, _cache, _output: 0,
        raising=False,
    )
    monkeypatch.setattr(
        build_web,
        "verify_same_origin_runtime_index",
        lambda _index: None,
        raising=False,
    )
    monkeypatch.setattr(
        build_web,
        "read_build_identity",
        lambda _root, _target: BuildIdentity("1.2.3", "a" * 40, "web"),
    )
    return commands


def test_build_web_stages_one_pygbag_artifact_at_an_explicit_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    commands = _patch_build_dependencies(monkeypatch, root)
    output = tmp_path / "publish" / "web"

    report = build_web.build_web(probe=True, output=output)

    assert len(commands) == 1
    assert commands[0][1:3] == ["-m", "pygbag"]
    assert commands[0].count("pygbag") == 1
    cdn_index = commands[0].index("--cdn")
    assert commands[0][cdn_index + 1] == "runtime/0.9.3/"
    assert report["probe"] is True
    assert report["release_version"] == "1.2.3"
    assert json.loads((output / "build-info.json").read_text(encoding="utf-8")) == {
        "commit_sha": "a" * 40,
        "files": ["index.html", "runtime.js", "windsprig.apk"],
        "target": "web",
        "version": "1.2.3",
    }


def test_build_web_stages_runtime_before_size_measurement_and_release_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _patch_build_dependencies(monkeypatch, root)
    output = tmp_path / "publish" / "web"
    staged_payload = b"pinned-runtime"
    calls: list[str] = []

    def stage_runtime(
        _manifest: RuntimeManifest,
        cache: Path,
        built: Path,
    ) -> int:
        calls.append("stage")
        assert cache == root / "build" / "web-runtime-cache"
        runtime = built / "runtime" / "0.9.3" / "pythons.js"
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(staged_payload)
        return len(staged_payload)

    def verify_index(index: Path) -> None:
        calls.append("verify")
        assert index == root / "build" / "web-stage" / "build" / "web" / "index.html"

    monkeypatch.setattr(build_web, "stage_runtime_assets", stage_runtime, raising=False)
    monkeypatch.setattr(
        build_web,
        "verify_same_origin_runtime_index",
        verify_index,
        raising=False,
    )

    report = build_web.build_web(probe=False, output=output)
    release_manifest = json.loads((output / "build-info.json").read_text(encoding="utf-8"))

    assert calls == ["stage", "verify"]
    assert report["browser_runtime_bytes"] == len(staged_payload)
    assert report["browser_runtime_manifest_sha256"] == "f" * 64
    assert "runtime/0.9.3/pythons.js" in report["files"]
    assert "runtime/0.9.3/pythons.js" in release_manifest["files"]


def test_web_template_uses_only_the_relative_vt_runtime_graph() -> None:
    template = (Path(__file__).resolve().parents[2] / "web" / "template.tmpl").read_text(encoding="utf-8")

    assert "http://" not in template
    assert "https://" not in template
    assert 'src="runtime/browserfs/2.0.0/browserfs.min.js"' in template
    assert 'src="{{cookiecutter.cdn}}pythons.js"' in template
    assert 'data-os="vt,snd,gui"' in template
    assert 'data-os="vtx' not in template


def test_build_web_refreshes_only_the_allowlisted_default_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    commands = _patch_build_dependencies(monkeypatch, root)
    output = root / "dist" / "web"
    output.mkdir(parents=True)
    (output / "stale.txt").write_text("stale", encoding="utf-8")

    build_web.build_web(probe=False)

    assert len(commands) == 1
    assert not (output / "stale.txt").exists()
    assert (output / "build-info.json").is_file()


def test_build_web_rejects_commit_drift_before_attaching_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _patch_build_dependencies(monkeypatch, root)
    monkeypatch.setattr(
        build_web,
        "read_build_identity",
        lambda _root, _target: BuildIdentity("1.2.3", "f" * 40, "web"),
    )
    output = tmp_path / "publish" / "web"

    with pytest.raises(SystemExit, match="HEAD changed"):
        build_web.build_web(probe=False, output=output)

    assert not (output / "build-info.json").exists()


def test_build_web_revalidates_destination_before_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _patch_build_dependencies(monkeypatch, root)
    dist = root / "dist"
    dist.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    def redirect_destination(_root: Path, stage: Path, *, probe: bool) -> None:
        del probe
        stage.mkdir(parents=True)
        dist.rmdir()
        _make_directory_link(dist, outside)

    monkeypatch.setattr(build_web, "stage_sources", redirect_destination)
    try:
        with pytest.raises(ValueError, match="link or reparse point"):
            build_web.build_web(probe=False)

        assert not (outside / "web").exists()
    finally:
        _remove_directory_link(dist)


def test_build_web_rejects_a_link_in_pygbag_output_without_copying_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _patch_build_dependencies(monkeypatch, root)
    outside = tmp_path / "outside-assets"
    outside.mkdir()
    (outside / "secret.txt").write_text("do not publish", encoding="utf-8")
    linked_assets = root / "build" / "web-stage" / "build" / "web" / "linked-assets"

    def inject_link(_built: Path) -> None:
        _make_directory_link(linked_assets, outside)

    monkeypatch.setattr(build_web, "_normalize_archives", inject_link)
    output = tmp_path / "published" / "web"
    try:
        with pytest.raises(ValueError, match="link or reparse point"):
            build_web.build_web(probe=False, output=output)

        assert not output.exists()
    finally:
        _remove_directory_link(linked_assets)


def test_atomic_publication_rolls_back_a_child_swapped_after_final_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    staged = root / "build" / "web-stage" / "build" / "web"
    assets = staged / "assets"
    assets.mkdir(parents=True)
    (staged / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
    (staged / "windsprig.apk").write_bytes(b"game")
    attach_release_manifest(staged, BuildIdentity("1.0.0", "d" * 40, "web"))
    output = root / "dist" / "web"
    parent_identity = build_web._prepare_web_output(root, output)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    backup = staged / "assets-backup"
    original_walk = build_web._regular_artifact_files
    walks = 0

    def swap_after_final_walk(path: Path) -> list[Path]:
        nonlocal walks
        files = original_walk(path)
        walks += 1
        if walks == 2:
            assets.rename(backup)
            _make_directory_link(assets, outside)
        return files

    monkeypatch.setattr(build_web, "_regular_artifact_files", swap_after_final_walk)
    try:
        with pytest.raises(ValueError, match="link or reparse point"):
            build_web._publish_web_output(staged, output, parent_identity)

        assert not output.exists()
        assert not (output / "assets" / "secret.txt").exists()
        assert (outside / "secret.txt").read_text(encoding="utf-8") == "secret"
    finally:
        for container in (output, staged):
            _remove_directory_link(container / "assets")
            container_backup = container / "assets-backup"
            if container_backup.exists() and container.exists():
                container_backup.rename(container / "assets")


def test_build_web_refuses_to_replace_an_existing_custom_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    commands = _patch_build_dependencies(monkeypatch, root)
    output = tmp_path / "published-web"
    output.mkdir()
    survivor = output / "keep.txt"
    survivor.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="custom web output already exists"):
        build_web.build_web(probe=False, output=output)

    assert survivor.read_text(encoding="utf-8") == "keep"
    assert commands == []


def test_build_web_rejects_a_relative_output_that_escapes_the_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    commands = _patch_build_dependencies(monkeypatch, root)

    with pytest.raises(ValueError, match="relative web output must stay inside"):
        build_web.build_web(probe=False, output=Path("../outside"))

    assert commands == []


def test_main_forwards_probe_and_output_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bool, Path | None]] = []

    def fake_build_web(probe: bool, output: Path | None = None) -> dict[str, object]:
        calls.append((probe, output))
        return {}

    monkeypatch.setattr(
        build_web,
        "build_web",
        fake_build_web,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["tools/build_web.py", "--probe", "--output", "dist/web"],
    )

    assert build_web.main() == 0
    assert calls == [(True, Path("dist/web"))]


def test_web_entry_uses_shared_game_app_without_native_shutdown() -> None:
    source = (Path(__file__).resolve().parents[2] / "web" / "main.py").read_text(encoding="utf-8")

    assert "from windsprig.app import GameApp" in source
    assert "create_foundation_screen_factory" in source
    assert "create_web_services" in source
    assert "asyncio.run(main())" in source
    assert "pygame.quit" not in source
    assert "SystemExit" not in source
