"""Fail-closed checks for local Windsprig release material and artifacts."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CANONICAL_SUMMARY = (
    "Ride the living wind, harmonize enemy echoes, and restore six hand-crafted sky worlds in a "
    "storybook action-platform adventure for one to four local players."
)

PUBLIC_PATHS = (
    "README.md",
    "CHANGELOG.md",
    "CREDITS.md",
    "PRIVACY.md",
    "SECURITY.md",
    "SUPPORT.md",
    "assets/LICENSES.md",
    "docs/launch",
    "packaging",
    "web",
    "windsprig",
)
REQUIRED_FILES = (
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "CREDITS.md",
    "PRIVACY.md",
    "SECURITY.md",
    "SUPPORT.md",
    "assets/LICENSES.md",
    "docs/launch/release-copy.md",
)
_TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".spec",
    ".tmpl",
    ".toml",
    ".txt",
    ".webmanifest",
    ".yml",
    ".yaml",
}
_PROTECTED_IDENTIFIER = re.compile(r"\b(?:kirby|nintendo)\b|return\s+to\s+dream\s+land", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|example\.com", re.IGNORECASE)


def _public_text_files(root: Path) -> Iterable[Path]:
    for relative in PUBLIC_PATHS:
        path = root / relative
        candidates = (path,) if path.is_file() else path.rglob("*") if path.is_dir() else ()
        for candidate in sorted(item for item in candidates if item.is_file()):
            if candidate.suffix.lower() in _TEXT_SUFFIXES:
                yield candidate


def _read_text(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"unreadable release text: {path.name}: {type(exc).__name__}")
        return ""


def _load_manifest(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid release manifest: {path.as_posix()}: {type(exc).__name__}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"release manifest must be an object: {path.as_posix()}")
        return None
    return payload


def verify_local_release(root: Path) -> list[str]:
    """Return deterministic release-policy errors; an empty list means locally ready."""

    release_root = root.resolve()
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (release_root / relative).is_file():
            errors.append(f"missing required release file: {relative}")

    project_file = release_root / "pyproject.toml"
    if not project_file.is_file():
        errors.append("missing required release file: pyproject.toml")
    else:
        try:
            project = tomllib.loads(project_file.read_text(encoding="utf-8"))
            version = project["project"]["version"]
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
            errors.append(f"invalid project metadata: {type(exc).__name__}")
        else:
            if version != "1.0.0":
                errors.append("pyproject version is not 1.0.0")

    readable = {
        relative: release_root / relative
        for relative in REQUIRED_FILES
        if (release_root / relative).is_file()
    }
    texts = {
        relative: _read_text(path, errors)
        for relative, path in readable.items()
        if path.suffix != "" or relative == "LICENSE"
    }

    readme = texts.get("README.md", "")
    release_copy = texts.get("docs/launch/release-copy.md", "")
    if CANONICAL_SUMMARY not in readme:
        errors.append("README is missing the canonical product summary")
    if CANONICAL_SUMMARY not in release_copy:
        errors.append("release copy is missing the canonical product summary")

    required_fragments = {
        "CHANGELOG.md": ("## [1.0.0] - 2026-07-11",),
        "CREDITS.md": (
            "Snowball_tree",
            "Noto Sans KR",
            "SIL Open Font License 1.1",
            "Original generated art",
            "Original generated audio",
        ),
        "PRIVACY.md": ("No account", "No analytics", "No server save"),
        "SECURITY.md": ("1.0.x", "security/advisories/new"),
        "SUPPORT.md": ("%LOCALAPPDATA%/Windsprig", "github.com/minchang-KIm/windsprig/issues"),
        "docs/launch/release-copy.md": ("No account or telemetry", "keyboard or compatible gamepad", "1024×576"),
    }
    for relative, fragments in required_fragments.items():
        text = texts.get(relative, "")
        for fragment in fragments:
            if fragment not in text:
                errors.append(f"{relative} is missing required release text: {fragment}")

    for file in _public_text_files(release_root):
        text = _read_text(file, errors)
        relative = file.relative_to(release_root).as_posix()
        if _PROTECTED_IDENTIFIER.search(text):
            errors.append(f"protected prototype identifier in public path: {relative}")
        if _PLACEHOLDER.search(text):
            errors.append(f"placeholder release text in public path: {relative}")

    for target, relative in (("web", "dist/web/build-info.json"), ("windows", "dist/Windsprig/build-info.json")):
        manifest_path = release_root / relative
        if not manifest_path.exists():
            continue
        manifest = _load_manifest(manifest_path, errors)
        if manifest is not None:
            if manifest.get("version") != "1.0.0":
                errors.append(f"{target} manifest version mismatch")
            if manifest.get("target") != target:
                errors.append(f"{target} manifest target mismatch")

    return sorted(set(errors))
