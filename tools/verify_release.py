"""Fail-closed checks for local Windsprig release material and artifacts."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from tools.release_common import BuildIdentity

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
_MAX_LIVE_RESPONSE_BYTES = 2 * 1024 * 1024

LiveFetcher = Callable[[str], tuple[int, str]]


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


def fetch_url(url: str) -> tuple[int, str]:
    """Fetch one bounded UTF-8 production resource without accepting compression ambiguity."""

    request = Request(
        url,
        headers={"Accept": "text/html,application/json;q=0.9", "User-Agent": "Windsprig-Release-Verifier/1.0"},
        method="GET",
    )
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as error:
        with error:
            payload = error.read(_MAX_LIVE_RESPONSE_BYTES + 1)
        if len(payload) > _MAX_LIVE_RESPONSE_BYTES:
            raise ValueError("production response exceeds verifier limit") from error
        return int(error.code), payload.decode("utf-8")
    with response:
        payload = response.read(_MAX_LIVE_RESPONSE_BYTES + 1)
        if len(payload) > _MAX_LIVE_RESPONSE_BYTES:
            raise ValueError("production response exceeds verifier limit")
        return int(response.status), payload.decode("utf-8")


def _canonical_production_origin(url: str) -> str:
    if type(url) is not str:
        raise TypeError("url must be a string")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("production URL must be a canonical HTTPS origin")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("production URL must be a canonical HTTPS origin") from None
    if port not in {None, 443}:
        raise ValueError("production URL must be a canonical HTTPS origin")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("production URL must be a canonical HTTPS origin") from None
    return f"https://{host}"


def _live_response(
    fetcher: LiveFetcher,
    url: str,
    label: str,
    errors: list[str],
) -> tuple[int, str] | None:
    try:
        response = fetcher(url)
        if not isinstance(response, tuple) or len(response) != 2:
            raise TypeError("fetcher result must be a status/text tuple")
        status, text = response
        if type(status) is not int or type(text) is not str:
            raise TypeError("fetcher result must contain an integer status and string text")
        return status, text
    except Exception as exc:
        errors.append(f"production {label} request failed: {type(exc).__name__}")
        return None


def _live_build_info(text: str) -> dict[str, object] | None:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_live_object,
            parse_constant=_reject_live_constant,
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or any(type(key) is not str for key in payload):
        return None
    return cast(dict[str, object], payload)


def _reject_live_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_live_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate live JSON field: {key}")
        result[key] = value
    return result


def verify_live_web(
    url: str,
    version: str,
    sha: str,
    *,
    fetcher: LiveFetcher = fetch_url,
) -> list[str]:
    """Verify that one canonical production origin serves the exact release identity."""

    origin = _canonical_production_origin(url)
    try:
        BuildIdentity(version, "0" * 40, "web")
    except (TypeError, ValueError):
        raise ValueError("version must be a semantic version") from None
    try:
        BuildIdentity("1.0.0", sha, "web")
    except (TypeError, ValueError):
        raise ValueError("sha must be exactly 40 lowercase hexadecimal characters") from None
    if not callable(fetcher):
        raise TypeError("fetcher must be callable")

    errors: list[str] = []
    shell = _live_response(fetcher, f"{origin}/", "shell", errors)
    if shell is not None:
        shell_status, shell_text = shell
        if shell_status != 200:
            errors.append(f"production shell returned {shell_status}")
        if "Windsprig: Echoes of the Gale" not in shell_text:
            errors.append("production shell title missing")

    info_response = _live_response(fetcher, f"{origin}/build-info.json", "build info", errors)
    if info_response is not None:
        info_status, info_text = info_response
        if info_status != 200:
            errors.append(f"production build info returned {info_status}")
        else:
            info = _live_build_info(info_text)
            if info is None:
                errors.append("production build info is invalid JSON")
            else:
                if info.get("version") != version:
                    errors.append("production version mismatch")
                if info.get("commit_sha") != sha:
                    errors.append("production commit mismatch")
                if info.get("target") != "web":
                    errors.append("production target mismatch")
    return sorted(set(errors))
