"""Source-binding contracts for deterministic browser artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.web_source_manifest import (
    SourceProvenanceError,
    inspect_runtime_source,
    runtime_source_files,
)


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _committed_runtime(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "web").mkdir(parents=True)
    (root / "windsprig").mkdir()
    (root / "levels").mkdir()
    (root / "assets" / "generated" / "ui").mkdir(parents=True)
    (root / "assets" / "fonts").mkdir()
    (root / "web" / "main.py").write_text("print('web')\n", encoding="utf-8")
    (root / "web" / "template.tmpl").write_text("<html></html>\n", encoding="utf-8")
    (root / "web" / "runtime-manifest.json").write_text("{}\n", encoding="utf-8")
    (root / "web" / "favicon.png").write_bytes(b"png")
    (root / "windsprig" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "levels" / "stage.json").write_text("{}\n", encoding="utf-8")
    (root / "assets" / "generated" / "ui" / "icons.png").write_bytes(b"png")
    (root / "assets" / "fonts" / "font.ttf").write_bytes(b"font")
    (root / "assets" / "LICENSES.md").write_text("# Licenses\n", encoding="utf-8")
    (root / "tools").mkdir()
    (root / "tools" / "build_web.py").write_text("BUILD = 1\n", encoding="utf-8")
    (root / "tools" / "release_common.py").write_text("RELEASE = 1\n", encoding="utf-8")
    (root / "tools" / "web_runtime.py").write_text("RUNTIME = 1\n", encoding="utf-8")
    (root / "tools" / "web_source_manifest.py").write_text("SOURCE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "1.0.0"\n', encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("windsprig/ignored.py\n", encoding="utf-8")
    _git(root, "init", "--quiet")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Windsprig Tests",
        "-c",
        "user.email=windsprig-tests@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return root


def test_runtime_manifest_is_stable_and_bound_to_clean_head(tmp_path: Path) -> None:
    root = _committed_runtime(tmp_path)

    first = inspect_runtime_source(root)
    second = inspect_runtime_source(root)

    assert first == second
    assert len(first.source_commit) == 40
    assert len(first.sha256) == 64
    assert first.files == (
        "assets/LICENSES.md",
        "assets/fonts/font.ttf",
        "assets/generated/ui/icons.png",
        "levels/stage.json",
        "web/favicon.png",
        "web/main.py",
        "web/runtime-manifest.json",
        "web/template.tmpl",
        "windsprig/app.py",
    )


def test_runtime_manifest_rejects_dirty_or_ignored_packageable_sources(tmp_path: Path) -> None:
    root = _committed_runtime(tmp_path)
    (root / "windsprig" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(SourceProvenanceError, match="tracked runtime source is dirty"):
        inspect_runtime_source(root)

    _git(root, "restore", "windsprig/app.py")
    (root / "windsprig" / "ignored.py").write_text("SURPRISE = True\n", encoding="utf-8")

    with pytest.raises(SourceProvenanceError, match="not tracked by Git"):
        inspect_runtime_source(root)


@pytest.mark.parametrize(
    "relative",
    [
        "pyproject.toml",
        "uv.lock",
        "tools/build_web.py",
        "tools/release_common.py",
        "tools/web_runtime.py",
        "tools/web_source_manifest.py",
    ],
)
def test_runtime_manifest_rejects_dirty_build_recipe_sources(tmp_path: Path, relative: str) -> None:
    root = _committed_runtime(tmp_path)
    path = root / relative
    path.write_bytes(path.read_bytes() + b"# dirty\n")

    with pytest.raises(SourceProvenanceError, match="build recipe source is dirty"):
        inspect_runtime_source(root)


def test_browser_runtime_sources_never_depend_on_host_font_discovery() -> None:
    root = Path(__file__).resolve().parents[3]
    packaged_python = [path for path in runtime_source_files(root) if path.suffix == ".py"]

    offenders = [
        path.relative_to(root).as_posix()
        for path in packaged_python
        if "pygame.font.SysFont" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
