"""Fail-closed contracts for the binary Pygbag feasibility decision."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from tools.evaluate_web_feasibility import (
    ArtifactEvidence,
    collect_artifacts,
    evaluate,
    main,
    render,
)

EXPECTED_FILES = [
    "favicon.png",
    "index.html",
    "web-stage.apk",
    "web-stage.tar.gz",
]


def passing_build() -> dict[str, object]:
    return {
        "compressed_bytes": 20_000_000,
        "compressed_limit_bytes": 31_457_280,
        "files": EXPECTED_FILES.copy(),
        "probe": True,
        "pygame_ce": "2.5.7",
        "pygbag": "0.9.3",
        "python_build": "3.12",
        "release_version": "1.0.0",
        "uncompressed_bytes": 21_000_000,
    }


def passing_browser() -> dict[str, object]:
    return {
        "audio": True,
        "audio_status": "ready",
        "boot": True,
        "cached_ms": 3_200,
        "cold_ms": 9_000,
        "console_errors": [],
        "fps": 58.0,
        "gameplay_active": True,
        "input": True,
        "save_restored": True,
        "save_written": True,
        "stage_complete": True,
    }


def test_evaluator_requires_every_signal_and_budget() -> None:
    decision, reasons = evaluate(passing_build(), passing_browser())

    assert decision == "pass"
    assert reasons == ()


def test_evaluator_never_calls_partial_success_a_pass() -> None:
    build = passing_build()
    build["compressed_bytes"] = 31_457_281
    browser = passing_browser()
    browser["save_restored"] = False
    browser["console_errors"] = ["Uncaught RuntimeError"]

    decision, reasons = evaluate(build, browser)

    assert decision == "fallback_required"
    assert reasons == ("save_restored", "console_errors", "compressed_bytes")


@pytest.mark.parametrize(
    "field",
    [
        "boot",
        "input",
        "audio",
        "stage_complete",
        "save_written",
        "save_restored",
        "gameplay_active",
    ],
)
@pytest.mark.parametrize("bad_value", [False, None, 1, "true"])
def test_evaluator_requires_exact_true_browser_signals(field: str, bad_value: object) -> None:
    browser = passing_browser()
    browser[field] = bad_value

    assert evaluate(passing_build(), browser) == ("fallback_required", (field,))


@pytest.mark.parametrize("audio_status", ["ready", "muted"])
def test_evaluator_accepts_both_visible_audio_outcomes(audio_status: str) -> None:
    browser = passing_browser()
    browser["audio_status"] = audio_status

    assert evaluate(passing_build(), browser) == ("pass", ())


@pytest.mark.parametrize("audio_status", [None, True, "", "silent", "READY", [], {}])
def test_evaluator_rejects_missing_or_unknown_visible_audio_semantics(audio_status: object) -> None:
    browser = passing_browser()
    browser["audio_status"] = audio_status

    assert evaluate(passing_build(), browser) == ("fallback_required", ("audio_status",))


@pytest.mark.parametrize(
    ("field", "boundary", "failure"),
    [
        ("cold_ms", 12_000, 12_001),
        ("cached_ms", 5_000, 5_001),
        ("fps", 30.0, 29.999),
    ],
)
def test_evaluator_enforces_inclusive_browser_budgets(
    field: str,
    boundary: int | float,
    failure: int | float,
) -> None:
    browser = passing_browser()
    browser[field] = boundary
    assert evaluate(passing_build(), browser) == ("pass", ())

    browser[field] = failure
    assert evaluate(passing_build(), browser) == ("fallback_required", (field,))


@pytest.mark.parametrize("field", ["cold_ms", "cached_ms"])
@pytest.mark.parametrize("bad_value", [True, False, None, "100", 1.5, -1, float("nan"), float("inf")])
def test_evaluator_rejects_malformed_timing_numbers_without_raising(field: str, bad_value: object) -> None:
    browser = passing_browser()
    browser[field] = bad_value

    assert evaluate(passing_build(), browser) == ("fallback_required", (field,))


@pytest.mark.parametrize(
    "bad_value",
    [True, False, None, "60", -1, float("nan"), float("inf"), float("-inf")],
)
def test_evaluator_rejects_non_finite_or_malformed_fps_without_raising(bad_value: object) -> None:
    browser = passing_browser()
    browser["fps"] = bad_value

    assert evaluate(passing_build(), browser) == ("fallback_required", ("fps",))


@pytest.mark.parametrize("bad_value", [None, "", {}, (), [1], ["boom"]])
def test_evaluator_requires_an_exact_empty_console_error_list(bad_value: object) -> None:
    browser = passing_browser()
    browser["console_errors"] = bad_value

    assert evaluate(passing_build(), browser) == ("fallback_required", ("console_errors",))


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("probe", False),
        ("probe", 1),
        ("pygbag", "0.9.4"),
        ("pygame_ce", "2.5.6"),
        ("python_build", "3.13"),
        ("release_version", "1.0.1"),
        ("files", list(reversed(EXPECTED_FILES))),
        ("files", EXPECTED_FILES + ["unexpected.txt"]),
        ("uncompressed_bytes", True),
        ("uncompressed_bytes", 0),
        ("compressed_limit_bytes", 99_999_999),
    ],
)
def test_evaluator_validates_build_provenance_and_schema(field: str, bad_value: object) -> None:
    build = passing_build()
    build[field] = bad_value

    assert evaluate(build, passing_browser()) == ("fallback_required", (field,))


@pytest.mark.parametrize(
    "bad_value",
    [True, False, None, "20000000", 20_000_000.0, 0, -1, float("nan"), float("inf")],
)
def test_evaluator_rejects_malformed_compressed_sizes_without_raising(bad_value: object) -> None:
    build = passing_build()
    build["compressed_bytes"] = bad_value

    assert evaluate(build, passing_browser()) == ("fallback_required", ("compressed_bytes",))


def test_evaluator_uses_the_canonical_size_limit_not_an_inflated_report_value() -> None:
    build = passing_build()
    build["compressed_limit_bytes"] = 99_999_999
    build["compressed_bytes"] = 31_457_281

    assert evaluate(build, passing_browser()) == (
        "fallback_required",
        ("compressed_limit_bytes", "compressed_bytes"),
    )


@pytest.mark.parametrize(
    ("build", "browser", "reason"),
    [
        ([], passing_browser(), "build_report"),
        (None, passing_browser(), "build_report"),
        (passing_build(), [], "browser_report"),
        (passing_build(), None, "browser_report"),
    ],
)
def test_evaluator_rejects_non_object_report_roots(
    build: object,
    browser: object,
    reason: str,
) -> None:
    assert evaluate(build, browser) == ("fallback_required", (reason,))


@pytest.mark.parametrize("report_name", ["build", "browser"])
def test_evaluator_rejects_unknown_or_non_string_report_keys(report_name: str) -> None:
    build = passing_build()
    browser = passing_browser()
    report = build if report_name == "build" else browser
    report["unexpected"] = True
    report[1] = True  # type: ignore[index]

    expected = "build_report" if report_name == "build" else "browser_report"
    assert evaluate(build, browser) == ("fallback_required", (expected,))


def test_evaluator_is_deterministic_and_does_not_mutate_reports() -> None:
    build = passing_build()
    browser = passing_browser()
    originals = copy.deepcopy((build, browser))

    first = evaluate(build, browser)
    second = evaluate(build, browser)

    assert first == second == ("pass", ())
    assert (build, browser) == originals


def _write_artifact_tree(root: Path) -> dict[str, object]:
    payloads = {
        "favicon.png": b"favicon",
        "index.html": b"<title>Windsprig</title>",
        "web-stage.apk": b"apk payload",
        "web-stage.tar.gz": b"tar payload",
    }
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    build = passing_build()
    build["compressed_bytes"] = sum(
        len(gzip.compress(payload, compresslevel=9, mtime=0)) for payload in payloads.values()
    )
    build["uncompressed_bytes"] = sum(len(payload) for payload in payloads.values())
    return build


def test_collect_artifacts_records_sizes_and_hashes_and_matches_the_build_report(tmp_path: Path) -> None:
    build = _write_artifact_tree(tmp_path)

    artifacts, reasons = collect_artifacts(tmp_path, build)

    assert reasons == ()
    assert [artifact.path for artifact in artifacts] == EXPECTED_FILES
    assert artifacts[1] == ArtifactEvidence(
        path="index.html",
        size_bytes=len(b"<title>Windsprig</title>"),
        sha256=hashlib.sha256(b"<title>Windsprig</title>").hexdigest(),
    )


def test_collect_artifacts_fails_closed_for_a_missing_or_mismatched_manifest(tmp_path: Path) -> None:
    build = _write_artifact_tree(tmp_path)
    (tmp_path / "index.html").unlink()

    artifacts, reasons = collect_artifacts(tmp_path, build)

    assert artifacts == ()
    assert reasons == ("artifact_files",)


def test_render_is_deterministic_and_contains_code_study_evidence(tmp_path: Path) -> None:
    build = _write_artifact_tree(tmp_path)
    browser = passing_browser()
    artifacts, artifact_reasons = collect_artifacts(tmp_path, build)
    assert artifact_reasons == ()
    runs = (("local run 1", browser), ("local run 2", {**browser, "cold_ms": 9_100}))

    first = render(
        "pass",
        (),
        build,
        browser,
        source_commit="a" * 40,
        artifacts=artifacts,
        local_runs=runs,
        tool_versions={"Evaluator Python": "3.12.10", "Playwright": "1.61.0", "uv": "0.10.7"},
    )
    second = render(
        "pass",
        (),
        build,
        browser,
        source_commit="a" * 40,
        artifacts=artifacts,
        local_runs=runs,
        tool_versions={"Evaluator Python": "3.12.10", "Playwright": "1.61.0", "uv": "0.10.7"},
    )

    assert first == second
    assert first.endswith("\n")
    assert first.count("**Status:** pass") == 1
    assert "`" + "a" * 40 + "`" in first
    assert "pygame-ce | `2.5.7`" in first
    assert "Pygbag | `0.9.3`" in first
    assert "Evaluator Python | `3.12.10`" in first
    assert "Playwright | `1.61.0`" in first
    assert "uv | `0.10.7`" in first
    assert "Gameplay FPS | 58.0" in first
    assert "save written | `true`" in first
    assert "audio status | `ready`" in first
    assert "local run 1" in first and "local run 2" in first
    assert hashlib.sha256(b"<title>Windsprig</title>").hexdigest() in first
    assert "six worlds, 30 stages, 90 stable motes" in first


def test_cli_writes_pass_evidence_and_returns_zero(tmp_path: Path) -> None:
    artifact_root = tmp_path / "dist" / "web"
    artifact_root.mkdir(parents=True)
    build = _write_artifact_tree(artifact_root)
    build_path = tmp_path / "web-build.json"
    browser_path = tmp_path / "browser-probe.json"
    output_path = tmp_path / "evidence" / "pygbag.md"
    build_path.write_text(json.dumps(build), encoding="utf-8")
    browser_path.write_text(json.dumps(passing_browser()), encoding="utf-8")

    result = main(
        [
            "--build",
            str(build_path),
            "--browser",
            str(browser_path),
            "--artifact-root",
            str(artifact_root),
            "--source-commit",
            "b" * 40,
            "--write",
            str(output_path),
        ]
    )

    assert result == 0
    assert output_path.is_file()
    assert "**Status:** pass" in output_path.read_text(encoding="utf-8")


def test_cli_writes_fallback_evidence_and_returns_two(tmp_path: Path) -> None:
    artifact_root = tmp_path / "dist" / "web"
    artifact_root.mkdir(parents=True)
    build = _write_artifact_tree(artifact_root)
    browser = passing_browser()
    browser["save_written"] = False
    build_path = tmp_path / "web-build.json"
    browser_path = tmp_path / "browser-probe.json"
    output_path = tmp_path / "evidence" / "pygbag.md"
    build_path.write_text(json.dumps(build), encoding="utf-8")
    browser_path.write_text(json.dumps(browser), encoding="utf-8")

    result = main(
        [
            "--build",
            str(build_path),
            "--browser",
            str(browser_path),
            "--artifact-root",
            str(artifact_root),
            "--source-commit",
            "c" * 40,
            "--write",
            str(output_path),
        ]
    )

    evidence = output_path.read_text(encoding="utf-8")
    assert result == 2
    assert "**Status:** fallback_required" in evidence
    assert "save_written" in evidence


@pytest.mark.parametrize(
    ("build_text", "browser_text"),
    [
        ("{broken", "null"),
        ('{"probe": true, "probe": false}', json.dumps(passing_browser())),
        (json.dumps(passing_build()), '{"fps": NaN}'),
        (json.dumps(passing_build()), "[]"),
    ],
)
def test_cli_turns_malformed_json_into_named_fallback_evidence(
    tmp_path: Path,
    build_text: str,
    browser_text: str,
) -> None:
    build_path = tmp_path / "web-build.json"
    browser_path = tmp_path / "browser-probe.json"
    output_path = tmp_path / "evidence.md"
    build_path.write_text(build_text, encoding="utf-8")
    browser_path.write_text(browser_text, encoding="utf-8")

    result = main(
        [
            "--build",
            str(build_path),
            "--browser",
            str(browser_path),
            "--artifact-root",
            str(tmp_path / "missing-artifacts"),
            "--source-commit",
            "d" * 40,
            "--write",
            str(output_path),
        ]
    )

    evidence = output_path.read_text(encoding="utf-8")
    assert result == 2
    assert "**Status:** fallback_required" in evidence
    assert "build_report" in evidence or "browser_report" in evidence


def test_cli_uses_two_explicit_local_run_measurements_when_available(tmp_path: Path) -> None:
    artifact_root = tmp_path / "dist" / "web"
    artifact_root.mkdir(parents=True)
    build = _write_artifact_tree(artifact_root)
    build_path = tmp_path / "web-build.json"
    browser_path = tmp_path / "browser-probe.json"
    run_one_path = tmp_path / "browser-probe-run-1.json"
    run_two_path = tmp_path / "browser-probe-run-2.json"
    output_path = tmp_path / "evidence.md"
    build_path.write_text(json.dumps(build), encoding="utf-8")
    browser_path.write_text(json.dumps(passing_browser()), encoding="utf-8")
    run_one_path.write_text(json.dumps({**passing_browser(), "cold_ms": 8_900}), encoding="utf-8")
    run_two_path.write_text(json.dumps({**passing_browser(), "cold_ms": 9_100}), encoding="utf-8")

    result = main(
        [
            "--build",
            str(build_path),
            "--browser",
            str(browser_path),
            "--browser-run",
            str(run_one_path),
            "--browser-run",
            str(run_two_path),
            "--artifact-root",
            str(artifact_root),
            "--source-commit",
            "e" * 40,
            "--write",
            str(output_path),
        ]
    )

    evidence = output_path.read_text(encoding="utf-8")
    assert result == 0
    assert "local run 1 | 8900" in evidence
    assert "local run 2 | 9100" in evidence
