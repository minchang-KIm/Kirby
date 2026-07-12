"""Source-binding contracts for deterministic browser artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.web_source_manifest import SourceProvenanceError, inspect_runtime_source


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
    (root / "web" / "main.py").write_text("print('web')\n", encoding="utf-8")
    (root / "web" / "template.tmpl").write_text("<html></html>\n", encoding="utf-8")
    (root / "web" / "runtime-manifest.json").write_text("{}\n", encoding="utf-8")
    (root / "web" / "favicon.png").write_bytes(b"png")
    (root / "windsprig" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "levels" / "stage.json").write_text("{}\n", encoding="utf-8")
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
