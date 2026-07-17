"""Static safety and gate coverage for the camera-ready CI workflow."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_has_only_the_four_non_deploying_release_jobs() -> None:
    text = workflow_text()
    jobs_text = text.split("\njobs:\n", maxsplit=1)[1]
    jobs = re.findall(r"^  ([a-z][a-z-]*):\s*$", jobs_text, flags=re.MULTILINE)

    assert jobs == ["source-tests", "native-tests", "web-artifact", "windows-artifact"]
    assert "permissions:\n  contents: read" in text
    assert "pull_request_target" not in text
    prohibited = (
        "git push",
        "vercel",
        "gh release",
        "actions/create-release",
        "pypa/gh-action-pypi-publish",
        "permissions: write",
        "id-token: write",
    )
    assert all(token not in text.casefold() for token in prohibited)


def test_ci_pins_actions_and_uses_bounded_concurrent_jobs() -> None:
    text = workflow_text()

    assert "cancel-in-progress: true" in text
    assert "timeout-minutes: 25" in text
    assert "timeout-minutes: 35" in text
    assert "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5" in text
    assert "astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e" in text
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "persist-credentials: false" in text
    assert 'version: "0.11.28"' in text
    assert "@v4" not in text and "@v6" not in text


def test_source_job_checks_lock_lint_strict_types_identity_and_release_policy() -> None:
    text = workflow_text()

    assert "uv lock --check" in text
    assert "uv run --locked --no-sync ruff check ." in text
    assert (
        "uv run --locked --no-sync mypy windsprig/platform windsprig/input windsprig/meta "
        "windsprig/app.py windsprig/screens tools"
    ) in text
    assert "uv run --locked --no-sync pytest tests/unit/test_public_identity.py -v" in text
    assert "from tools.verify_release import verify_local_release" in text


def test_native_matrix_is_exact_and_excludes_packaged_browser_tests() -> None:
    text = workflow_text()

    assert "fail-fast: false" in text
    assert "os: [ubuntu-latest, windows-latest]" in text
    assert 'python: ["3.12", "3.13"]' in text
    assert (
        "pytest tests/unit tests/integration -q --cov=windsprig --cov-branch "
        "--cov-report=term-missing --cov-fail-under=85"
    ) in text


def test_web_job_builds_product_and_chromium_evidence() -> None:
    text = workflow_text()

    assert "playwright install --with-deps chromium" in text
    assert "python -I tools/build_web.py --output dist/web --probe" in text
    assert "tests/e2e/test_web_product.py" in text
    assert "tests/e2e/test_web_release_probe_boundary.py" in text
    assert "tests/e2e/test_web_pwa.py" in text
    assert re.search(
        r"if: always\(\)\s+run: uv run --locked --no-sync python tools/evaluate_web_feasibility.py",
        text,
    )
    assert text.count("if: always()") >= 2
    for path in (
        "artifacts/web-build.json",
        "artifacts/browser-probe.json",
        "docs/feasibility/pygbag-0.9.3.md",
    ):
        assert path in text


def test_windows_job_runs_contract_tests_build_smoke_and_uploads_release() -> None:
    text = workflow_text()

    assert "pytest tests/release/test_build_windows.py -q" in text
    assert "python tools/build_windows.py --output dist/release" in text
    assert "name: windsprig-windows-${{ github.sha }}" in text
    assert "path: dist/release" in text
    assert "if-no-files-found: error" in text
