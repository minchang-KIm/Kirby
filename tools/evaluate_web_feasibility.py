"""Evaluate and document the fail-closed Pygbag foundation gate."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import platform
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, Literal, NoReturn, TypeGuard, cast

Decision = Literal["pass", "fallback_required"]
BrowserRun = tuple[str, object]

PYGBAG_VERSION: Final = "0.9.3"
PYGAME_CE_VERSION: Final = "2.5.7"
PYTHON_BUILD: Final = "3.12"
RELEASE_VERSION: Final = "1.0.0"
COMPRESSED_LIMIT_BYTES: Final = 30 * 1024 * 1024
EXPECTED_FILES: Final = (
    "favicon.png",
    "index.html",
    "web-stage.apk",
    "web-stage.tar.gz",
)

_BUILD_KEYS: Final = frozenset(
    {
        "compressed_bytes",
        "compressed_limit_bytes",
        "files",
        "probe",
        "pygame_ce",
        "pygbag",
        "python_build",
        "release_version",
        "uncompressed_bytes",
    }
)
_BROWSER_KEYS: Final = frozenset(
    {
        "audio",
        "audio_status",
        "boot",
        "cached_ms",
        "cold_ms",
        "console_errors",
        "fps",
        "gameplay_active",
        "input",
        "save_restored",
        "save_written",
        "stage_complete",
    }
)
_REASON_ORDER: Final = (
    "build_report",
    "browser_report",
    "probe",
    "pygbag",
    "pygame_ce",
    "python_build",
    "release_version",
    "files",
    "uncompressed_bytes",
    "boot",
    "input",
    "audio",
    "audio_status",
    "stage_complete",
    "save_written",
    "save_restored",
    "gameplay_active",
    "cold_ms",
    "cached_ms",
    "fps",
    "console_errors",
    "compressed_limit_bytes",
    "compressed_bytes",
)
_COMMIT_PATTERN: Final = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class ArtifactEvidence:
    """One packaged file's repository-relative integrity evidence."""

    path: str
    size_bytes: int
    sha256: str


def _validated_report(value: object, expected_keys: frozenset[str]) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if any(not isinstance(key, str) for key in value):
        return None
    string_keys = cast("dict[str, object]", value)
    if set(string_keys) - expected_keys:
        return None
    return string_keys


def _is_positive_int(value: object) -> TypeGuard[int]:
    return type(value) is int and value > 0


def _is_nonnegative_int(value: object) -> TypeGuard[int]:
    return type(value) is int and value >= 0


def _is_finite_number(value: object) -> TypeGuard[int | float]:
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)


def evaluate(build: object, browser: object) -> tuple[Decision, tuple[str, ...]]:
    """Return a total binary decision for exact, pinned build and browser reports."""
    failed: set[str] = set()
    build_report = _validated_report(build, _BUILD_KEYS)
    browser_report = _validated_report(browser, _BROWSER_KEYS)

    if build_report is None:
        failed.add("build_report")
    else:
        if build_report.get("probe") is not True:
            failed.add("probe")
        expected_versions = {
            "pygbag": PYGBAG_VERSION,
            "pygame_ce": PYGAME_CE_VERSION,
            "python_build": PYTHON_BUILD,
            "release_version": RELEASE_VERSION,
        }
        for field, expected in expected_versions.items():
            if build_report.get(field) != expected:
                failed.add(field)
        if build_report.get("files") != list(EXPECTED_FILES):
            failed.add("files")
        if not _is_positive_int(build_report.get("uncompressed_bytes")):
            failed.add("uncompressed_bytes")
        if build_report.get("compressed_limit_bytes") != COMPRESSED_LIMIT_BYTES:
            failed.add("compressed_limit_bytes")
        compressed_bytes = build_report.get("compressed_bytes")
        if not _is_positive_int(compressed_bytes) or compressed_bytes > COMPRESSED_LIMIT_BYTES:
            failed.add("compressed_bytes")

    if browser_report is None:
        failed.add("browser_report")
    else:
        for field in (
            "boot",
            "input",
            "audio",
            "stage_complete",
            "save_written",
            "save_restored",
            "gameplay_active",
        ):
            if browser_report.get(field) is not True:
                failed.add(field)
        audio_status = browser_report.get("audio_status")
        if not isinstance(audio_status, str) or audio_status not in {"ready", "muted"}:
            failed.add("audio_status")

        cold_ms = browser_report.get("cold_ms")
        if not _is_nonnegative_int(cold_ms) or cold_ms > 12_000:
            failed.add("cold_ms")
        cached_ms = browser_report.get("cached_ms")
        if not _is_nonnegative_int(cached_ms) or cached_ms > 5_000:
            failed.add("cached_ms")
        fps = browser_report.get("fps")
        if not _is_finite_number(fps) or fps < 30:
            failed.add("fps")
        if type(browser_report.get("console_errors")) is not list or browser_report["console_errors"] != []:
            failed.add("console_errors")

    reasons = tuple(reason for reason in _REASON_ORDER if reason in failed)
    return ("pass", ()) if not reasons else ("fallback_required", reasons)


def collect_artifacts(
    artifact_root: Path,
    build: object,
) -> tuple[tuple[ArtifactEvidence, ...], tuple[str, ...]]:
    """Hash the exact build manifest and verify its aggregate byte measurements."""
    build_report = _validated_report(build, _BUILD_KEYS)
    if build_report is None or build_report.get("files") != list(EXPECTED_FILES):
        return (), ("artifact_files",)
    try:
        if not artifact_root.is_dir() or artifact_root.is_symlink():
            return (), ("artifact_files",)
        paths = sorted(
            (path for path in artifact_root.rglob("*") if path.is_file()),
            key=lambda path: path.as_posix(),
        )
        relative_paths = [path.relative_to(artifact_root).as_posix() for path in paths]
        if relative_paths != list(EXPECTED_FILES) or any(path.is_symlink() for path in paths):
            return (), ("artifact_files",)
        payloads = [path.read_bytes() for path in paths]
    except (OSError, ValueError):
        return (), ("artifact_files",)

    artifacts = tuple(
        ArtifactEvidence(
            path=relative_path,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        for relative_path, payload in zip(relative_paths, payloads, strict=True)
    )
    reasons: list[str] = []
    if sum(artifact.size_bytes for artifact in artifacts) != build_report.get("uncompressed_bytes"):
        reasons.append("artifact_sizes")
    compressed_bytes = sum(
        len(gzip.compress(payload, compresslevel=9, mtime=0)) for payload in payloads
    )
    if compressed_bytes != build_report.get("compressed_bytes"):
        reasons.append("artifact_compressed_bytes")
    return artifacts, tuple(reasons)


def _display(value: object) -> str:
    if value is None:
        return "<missing>"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return "<invalid>"


def _observed(report: object, field: str) -> str:
    if not isinstance(report, dict) or field not in report:
        return "<missing>"
    return _display(report[field])


def _requirement_result(reason: str, reasons: tuple[str, ...]) -> str:
    return "fail" if reason in reasons else "pass"


def render(
    decision: Decision,
    reasons: tuple[str, ...],
    build: object,
    browser: object,
    *,
    source_commit: str = "<unavailable>",
    artifacts: Sequence[ArtifactEvidence] = (),
    local_runs: Sequence[BrowserRun] = (),
    tool_versions: Mapping[str, str] | None = None,
) -> str:
    """Render deterministic, source-bound evidence without concealing malformed values."""
    route = (
        "pygame-ce/Pygbag remains the approved shared runtime."
        if decision == "pass"
        else "Stop downstream implementation and create the TypeScript/Phaser replacement plans before resuming."
    )
    reason_text = "none" if not reasons else ", ".join(f"`{reason}`" for reason in reasons)
    build_report = build if isinstance(build, dict) else {}
    browser_report = browser if isinstance(browser, dict) else {}

    requirement_rows = (
        ("probe artifact", "probe", _observed(build_report, "probe"), "exactly true"),
        ("boot", "boot", _observed(browser_report, "boot"), "exactly true"),
        ("input", "input", _observed(browser_report, "input"), "exactly true"),
        ("audio available or visibly muted", "audio", _observed(browser_report, "audio"), "exactly true"),
        ("audio status", "audio_status", _observed(browser_report, "audio_status"), "ready or muted"),
        ("stage complete", "stage_complete", _observed(browser_report, "stage_complete"), "exactly true"),
        ("save written", "save_written", _observed(browser_report, "save_written"), "exactly true"),
        ("save restored", "save_restored", _observed(browser_report, "save_restored"), "exactly true"),
        ("gameplay active", "gameplay_active", _observed(browser_report, "gameplay_active"), "exactly true"),
        ("cold interactive", "cold_ms", _observed(browser_report, "cold_ms"), "≤ 12000 ms"),
        ("cached interactive", "cached_ms", _observed(browser_report, "cached_ms"), "≤ 5000 ms"),
        ("Gameplay FPS", "fps", _observed(browser_report, "fps"), "≥ 30, active StageRuntime only"),
        ("console errors", "console_errors", _observed(browser_report, "console_errors"), "exact empty list"),
        (
            "compressed transfer",
            "compressed_bytes",
            _observed(build_report, "compressed_bytes"),
            f"≤ {COMPRESSED_LIMIT_BYTES} bytes",
        ),
    )
    requirements = "\n".join(
        f"| {label} | `{observed}` | {rule} | {_requirement_result(reason, reasons)} |"
        for label, reason, observed, rule in requirement_rows
    )

    artifact_rows = "\n".join(
        f"| `{artifact.path}` | {artifact.size_bytes} | `{artifact.sha256}` |" for artifact in artifacts
    )
    if not artifact_rows:
        artifact_rows = "| _unavailable_ | _unavailable_ | _unavailable_ |"

    runs = tuple(local_runs) or (("decision report", browser_report),)
    run_rows = "\n".join(
        "| "
        + " | ".join(
            (
                label,
                _observed(report, "cold_ms"),
                _observed(report, "cached_ms"),
                _observed(report, "fps"),
                _observed(report, "gameplay_active"),
                _observed(report, "console_errors"),
            )
        )
        + " |"
        for label, report in runs
    )
    extra_tool_rows = "\n".join(
        f"| {name} | `{observed_version}` |"
        for name, observed_version in sorted((tool_versions or {}).items(), key=lambda item: item[0].casefold())
    )
    if extra_tool_rows:
        extra_tool_rows = "\n" + extra_tool_rows

    return f"""# Pygbag 0.9.3 Feasibility Decision

**Status:** {decision}

**Decision:** {route}

**Failed requirements:** {reason_text}

## Source and toolchain

- Source commit: `{source_commit}`

| Component | Observed version |
| --- | --- |
| pygame-ce | `{_observed(build_report, "pygame_ce").strip('"')}` |
| Pygbag | `{_observed(build_report, "pygbag").strip('"')}` |
| Pygbag Python build | `{_observed(build_report, "python_build").strip('"')}` |
| Windsprig release | `{_observed(build_report, "release_version").strip('"')}` |{extra_tool_rows}

## Requirement evidence

| Requirement | Observed | Rule | Result |
| --- | --- | --- | --- |
{requirements}

## Gameplay-only measurements

FPS is sampled only across consecutive rendered frames backed by an active real `StageRuntime`.

| Metric | Observed | Rule |
| --- | ---: | --- |
| Gameplay FPS | {_observed(browser_report, "fps")} | ≥ 30, active StageRuntime only |

| Run | Cold interactive (ms) | Cached interactive (ms) | Gameplay FPS | Gameplay active | Console errors |
| --- | ---: | ---: | ---: | --- | --- |
{run_rows}

## Artifact integrity

- Declared uncompressed bytes: {_observed(build_report, "uncompressed_bytes")}
- Declared compressed bytes: {_observed(build_report, "compressed_bytes")}
- Canonical compressed limit: {COMPRESSED_LIMIT_BYTES} bytes
- Declared files: {_observed(build_report, "files")}

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
{artifact_rows}

## Scope Invariant

This decision does not remove or defer the six worlds, 30 stages, 90 stable motes, six unique bosses,
complete action/state flow, local four-player support, browser build, Windows build, English/Korean support,
accessibility, performance budgets, or release evidence required by the camera-ready design.
"""


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant: {value}")


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_report(path: Path) -> object:
    try:
        return cast(
            object,
            json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_json_constant,
            ),
        )
    except (OSError, UnicodeError, ValueError):
        return None


def _resolve_source_commit(requested: str | None) -> tuple[str, tuple[str, ...]]:
    if requested is not None:
        return (requested, ()) if _COMMIT_PATTERN.fullmatch(requested) else ("<unavailable>", ("source_commit",))
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "<unavailable>", ("source_commit",)
    commit = completed.stdout.strip()
    return (commit, ()) if _COMMIT_PATTERN.fullmatch(commit) else ("<unavailable>", ("source_commit",))


def _collect_tool_versions() -> dict[str, str]:
    """Record exact local gate-tool versions without making them decision policy."""
    observed = {"Evaluator Python": platform.python_version()}
    distributions = {
        "mypy": "mypy",
        "Playwright": "playwright",
        "pytest": "pytest",
        "pytest-cov": "pytest-cov",
        "Ruff": "ruff",
    }
    for label, distribution in distributions.items():
        try:
            observed[label] = version(distribution)
        except PackageNotFoundError:
            observed[label] = "<unavailable>"
    try:
        completed = subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        fields = completed.stdout.strip().split()
        observed["uv"] = fields[1] if len(fields) >= 2 and fields[0] == "uv" else "<unavailable>"
    except (OSError, subprocess.SubprocessError):
        observed["uv"] = "<unavailable>"
    return observed


def _merge_reasons(*groups: Sequence[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for group in groups:
        for reason in group:
            if reason not in merged:
                merged.append(reason)
    return tuple(merged)


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate report files, always write evidence, and encode the binary decision in the exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("artifacts/web-build.json"))
    parser.add_argument("--browser", type=Path, default=Path("artifacts/browser-probe.json"))
    parser.add_argument("--browser-run", type=Path, action="append", default=[])
    parser.add_argument("--artifact-root", type=Path, default=Path("dist/web"))
    parser.add_argument("--source-commit")
    parser.add_argument("--write", type=Path, required=True)
    args = parser.parse_args(argv)

    build = _load_report(args.build)
    browser = _load_report(args.browser)
    _, report_reasons = evaluate(build, browser)
    artifacts, artifact_reasons = collect_artifacts(args.artifact_root, build)
    source_commit, source_reasons = _resolve_source_commit(args.source_commit)

    local_runs: list[BrowserRun] = []
    local_run_reasons: list[str] = []
    for index, path in enumerate(args.browser_run, start=1):
        report = _load_report(path)
        local_runs.append((f"local run {index}", report))
        _, run_reasons = evaluate(build, report)
        local_run_reasons.extend(f"local_run_{index}.{reason}" for reason in run_reasons if reason != "build_report")

    reasons = _merge_reasons(report_reasons, artifact_reasons, source_reasons, local_run_reasons)
    decision: Decision = "pass" if not reasons else "fallback_required"
    evidence = render(
        decision,
        reasons,
        build,
        browser,
        source_commit=source_commit,
        artifacts=artifacts,
        local_runs=local_runs,
        tool_versions=_collect_tool_versions(),
    )
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(evidence, encoding="utf-8")
    print(f"Pygbag feasibility: {decision}")
    return 0 if decision == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
