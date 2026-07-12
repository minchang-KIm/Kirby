"""Bind browser artifacts to the exact clean, tracked runtime source tree."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_COMMIT_PATTERN: Final = re.compile(r"[0-9a-f]{40}\Z")
_IGNORED_DIRS: Final = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "test", "tests"}
)
_ALLOWED_SUFFIXES: Final = frozenset(
    {".json", ".jpg", ".jpeg", ".md", ".ogg", ".otf", ".png", ".py", ".ttf", ".txt", ".webp"}
)
_SECRET_SUFFIXES: Final = frozenset({".key", ".p12", ".pem", ".pfx"})
_WEB_ENTRY_FILES: Final = (
    "favicon.png",
    "main.py",
    "runtime-manifest.json",
    "template.tmpl",
)
_GENERATED_RUNTIME_FILES: Final = frozenset({"windsprig/_build_flags.py"})
_SOURCE_ONLY_RUNTIME_FILES: Final = frozenset({"assets/fonts/NotoSansKR[wght].ttf"})


class SourceProvenanceError(RuntimeError):
    """Raised when a browser build cannot be bound to clean tracked source."""


@dataclass(frozen=True, slots=True)
class RuntimeSourceManifest:
    """Canonical identity for every repository file eligible for web staging."""

    source_commit: str
    sha256: str
    files: tuple[str, ...]


def _is_runtime_file(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.startswith(".") or path.suffix.lower() in _SECRET_SUFFIXES:
        return False
    if any(token in lowered for token in ("credential", "secret")):
        return False
    return path.suffix.lower() in _ALLOWED_SUFFIXES


def runtime_source_files(root: Path) -> tuple[Path, ...]:
    """Return the one canonical file set consumed by browser staging."""
    lexical_root = Path(root).absolute()
    files: list[Path] = []
    for filename in _WEB_ENTRY_FILES:
        path = lexical_root / "web" / filename
        if not path.is_file():
            raise SourceProvenanceError(f"required web source is missing: {path}")
        files.append(path)

    # Runtime assets use the same source identity and cleanliness gate as Python
    # and level data, so browser packaging cannot silently omit or replace art.
    for directory in ("assets", "windsprig", "levels"):
        source = lexical_root / directory
        if not source.is_dir():
            raise SourceProvenanceError(f"required runtime source directory is missing: {source}")
        for path in source.rglob("*"):
            relative = path.relative_to(lexical_root)
            if relative.as_posix() in _GENERATED_RUNTIME_FILES:
                continue
            if relative.as_posix() in _SOURCE_ONLY_RUNTIME_FILES:
                continue
            if any(part.lower() in _IGNORED_DIRS for part in relative.parts):
                continue
            if path.is_file() and _is_runtime_file(path):
                files.append(path)
    return tuple(sorted(files, key=lambda path: path.relative_to(lexical_root).as_posix()))


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceProvenanceError(f"Git provenance command failed: {' '.join(arguments)}") from error
    return completed.stdout


def inspect_runtime_source(root: Path) -> RuntimeSourceManifest:
    """Validate clean tracked inputs and return their commit and content digest."""
    lexical_root = Path(root).absolute()
    source_files = runtime_source_files(lexical_root)
    relative_files = tuple(path.relative_to(lexical_root).as_posix() for path in source_files)

    source_commit = _git(lexical_root, "rev-parse", "HEAD").strip()
    if not _COMMIT_PATTERN.fullmatch(source_commit):
        raise SourceProvenanceError("Git HEAD is not a full lowercase commit SHA")
    status = _git(
        lexical_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        "web",
        "assets",
        "windsprig",
        "levels",
    )
    if status:
        raise SourceProvenanceError("tracked runtime source is dirty")

    tracked = frozenset(
        value
        for value in _git(lexical_root, "ls-files", "-z", "--", "web", "assets", "windsprig", "levels").split("\0")
        if value
    )
    untracked_packageable = tuple(path for path in relative_files if path not in tracked)
    if untracked_packageable:
        joined = ", ".join(untracked_packageable)
        raise SourceProvenanceError(f"packageable runtime source is not tracked by Git: {joined}")

    digest = hashlib.sha256()
    digest.update(b"windsprig-runtime-manifest-v1\0")
    for relative, path in zip(relative_files, source_files, strict=True):
        payload = path.read_bytes()
        relative_bytes = relative.encode("utf-8")
        digest.update(len(relative_bytes).to_bytes(4, "big"))
        digest.update(relative_bytes)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return RuntimeSourceManifest(source_commit, digest.hexdigest(), relative_files)
