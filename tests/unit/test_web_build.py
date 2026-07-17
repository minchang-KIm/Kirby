"""Deterministic staging and browser-entry contracts for the Pygbag release path."""

from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pygame
import pytest

from tools import build_web


def _template_archive_validator():
    """Compile the exact pure validation function embedded in the web loader."""

    template = (Path(__file__).resolve().parents[2] / "web" / "template.tmpl").read_text(encoding="utf-8")
    tree = ast.parse(template.split("#<!--", 1)[1].split("# BEGIN BLOCK", 1)[0])
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_validated_archive_members"
    ]
    if len(functions) != 1:
        raise AssertionError("template must define exactly one archive validator")
    module = ast.Module(body=functions, type_ignores=[])
    namespace: dict[str, object] = {
        "PurePosixPath": __import__("pathlib").PurePosixPath,
        "stat": __import__("stat"),
        "unicodedata": __import__("unicodedata"),
    }
    exec(compile(module, "web/template.tmpl", "exec"), namespace)  # noqa: S102 - exact reviewed loader code
    return namespace["_validated_archive_members"]


def _zip_member(name: str, *, mode: int = 0o100644) -> zipfile.ZipInfo:
    member = zipfile.ZipInfo(name)
    # ZipInfo normalizes the host separator in its constructor on Windows;
    # restore the raw central-directory spelling to exercise the web/POSIX gate.
    member.filename = name
    member.create_system = 3
    member.external_attr = mode << 16
    return member


@pytest.mark.parametrize(
    "names",
    [
        ("assets/main.py", "assets/main.py"),
        ("assets/Main.py", "assets/main.py"),
        ("assets/caf\u00e9.py", "assets/cafe\u0301.py"),
        ("assets/foo", "assets/foo/bar.py"),
        ("assets/foo/bar.py", "assets/foo"),
        ("C:/evil.py",),
        ("assets\\evil.py",),
        ("assets//evil.py",),
        ("assets/./evil.py",),
        ("assets/../evil.py",),
        ("assets/CON",),
        ("assets/trailing. ",),
    ],
)
def test_template_archive_validator_rejects_ambiguous_or_nonportable_members(
    names: tuple[str, ...],
) -> None:
    validate = _template_archive_validator()

    with pytest.raises(RuntimeError, match="unsafe application archive member|archive path collision"):
        validate(tuple(_zip_member(name) for name in names))


def test_template_archive_validator_rejects_symlinks_and_preserves_safe_order() -> None:
    validate = _template_archive_validator()
    safe = (_zip_member("assets/main.py"), _zip_member("assets/data/one.json"))

    assert validate(safe) == safe
    with pytest.raises(RuntimeError, match="unsafe application archive member"):
        validate((_zip_member("assets/link", mode=0o120777),))


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
    for name in (
        "index-shell.html",
        "main.py",
        "manifest.webmanifest",
        "runtime-manifest.json",
        "service-worker.js",
        "template.tmpl",
    ):
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
    (assets / "generated" / "ui" / "favicon.png").write_bytes(b"favicon")
    (assets / "generated" / "ui" / "social-card.png").write_bytes(b"social")
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
        "assets/generated/ui/favicon.png",
        "assets/generated/ui/icons.png",
        "assets/generated/ui/social-card.png",
        "index-shell.html",
        "levels/level.json",
        "main.py",
        "manifest.webmanifest",
        "runtime-manifest.json",
        "service-worker.js",
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
    for name in (
        "index-shell.html",
        "main.py",
        "manifest.webmanifest",
        "runtime-manifest.json",
        "service-worker.js",
        "template.tmpl",
    ):
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


def test_normalized_apk_stores_pcm_audio_and_deflates_other_members_deterministically(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "game.apk"
    payloads = {
        "assets/main.py": b"print('windsprig')\n" * 40,
        "assets/audio/confirm.wav": b"RIFF" + b"\x00" * 4_096,
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, payload in reversed(tuple(payloads.items())):
            archive.writestr(name, payload)

    build_web._normalize_zip(archive_path)
    first = archive_path.read_bytes()
    build_web._normalize_zip(archive_path)

    assert archive_path.read_bytes() == first
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == sorted(payloads)
        assert {name: archive.read(name) for name in archive.namelist()} == payloads
        assert archive.getinfo("assets/main.py").compress_type == zipfile.ZIP_DEFLATED
        assert archive.getinfo("assets/audio/confirm.wav").compress_type == zipfile.ZIP_STORED


def test_prune_unused_pygbag_archives_keeps_only_the_loader_referenced_apk(
    tmp_path: Path,
) -> None:
    output = tmp_path / "web"
    output.mkdir()
    (output / "index.html").write_text(
        '<script>platform.fopen("game.apk", "rb")</script>',
        encoding="utf-8",
    )
    apk = output / "game.apk"
    tarball = output / "game.tar.gz"
    apk.write_bytes(b"apk")
    tarball.write_bytes(b"unused duplicate")

    build_web.prune_unused_pygbag_archives(output)

    assert apk.read_bytes() == b"apk"
    assert not tarball.exists()


def test_prune_unused_pygbag_archives_refuses_a_referenced_tarball(tmp_path: Path) -> None:
    output = tmp_path / "web"
    output.mkdir()
    (output / "index.html").write_text(
        '<script>platform.fopen("game.apk", "rb"); fetch("game.tar.gz")</script>',
        encoding="utf-8",
    )
    (output / "game.apk").write_bytes(b"apk")
    tarball = output / "game.tar.gz"
    tarball.write_bytes(b"still referenced")

    with pytest.raises(SystemExit, match="still references duplicate Pygbag archive"):
        build_web.prune_unused_pygbag_archives(output)

    assert tarball.read_bytes() == b"still referenced"


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


def test_pwa_favicon_has_one_canonical_original_source() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = root / "assets/generated/ui/favicon.png"

    assert canonical.is_file()
    assert not (root / "web/favicon.png").exists()
    image = pygame.image.load(canonical)
    assert image.get_size() == (192, 192)


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
    build_source = (root / "tools" / "build_web.py").read_text(encoding="utf-8")

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
    assert "_validated_archive_members" in template
    assert "PurePosixPath(name)" in template
    assert "member_path.is_absolute()" in template
    assert "member_path.as_posix() != name" in template
    assert "archive path collision" in template
    assert 'platform.fopen("{{cookiecutter.archive}}.tar.gz", "rb")' not in template
    assert "function custom_onload" in template
    assert 'id="canvas"' in template
    assert 'id="audio-status"' in template
    assert 'role="status"' in template
    assert "Loading Windsprig…" in template
    assert "physical keyboard or compatible gamepad" in template
    assert "<noscript>" in template
    preflight_call = "_preflight_build_recipe(Path(__file__).resolve().parents[1])"
    assert build_source.index(preflight_call) < build_source.index("from tools.release_common import")


def test_direct_web_build_requires_an_isolated_interpreter() -> None:
    script = Path(__file__).resolve().parents[2] / "tools" / "build_web.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "python -I tools/build_web.py" in completed.stderr
