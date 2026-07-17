"""Policy tests for the canonical Vercel static deployment contract."""

from __future__ import annotations

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from tools.verify_release import verify_local_release

ROOT = Path(__file__).resolve().parents[2]
VERCEL_CONFIG = ROOT / "vercel.json"
VERCEL_IGNORE = ROOT / ".vercelignore"

_ALLOWED_CONFIG_KEYS = {
    "$schema",
    "buildCommand",
    "cleanUrls",
    "headers",
    "installCommand",
    "outputDirectory",
    "rewrites",
    "trailingSlash",
}
_REVALIDATE = "public, max-age=0, must-revalidate"
_CACHE_SOURCE = r"/(.*)"
_SPA_SOURCE = r"/((?!.*\.).*)"


def _load_vercel_config() -> dict[str, Any]:
    config = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    return config


def _header_map(rule: dict[str, Any]) -> dict[str, str]:
    headers = rule["headers"]
    assert isinstance(headers, list)
    assert all(set(header) == {"key", "value"} for header in headers)
    result = {header["key"]: header["value"] for header in headers}
    assert len(result) == len(headers), "duplicate header names create ambiguous policy"
    return result


def _ignore_patterns() -> list[str]:
    raw_lines = VERCEL_IGNORE.read_text(encoding="utf-8").splitlines()
    assert all(line == line.strip() for line in raw_lines)
    return [line for line in raw_lines if line and not line.startswith("#")]


def _is_ignored(path: str, patterns: list[str]) -> bool:
    """Match the denylist syntax used here, following .gitignore path semantics."""
    normalized = path.strip("/")
    parts = PurePosixPath(normalized).parts
    for pattern in patterns:
        anchored = pattern.startswith("/")
        candidate = pattern.removeprefix("/").rstrip("/")
        if anchored:
            if fnmatchcase(normalized, candidate) or normalized.startswith(f"{candidate}/"):
                return True
        elif "/" in candidate:
            if fnmatchcase(normalized, candidate) or normalized.startswith(f"{candidate}/"):
                return True
        elif any(fnmatchcase(part, candidate) for part in parts):
            return True
    return False


def test_vercel_configuration_uses_only_the_current_static_contract() -> None:
    config = _load_vercel_config()

    assert set(config) == _ALLOWED_CONFIG_KEYS
    assert config["$schema"] == "https://openapi.vercel.sh/vercel.json"
    assert config["cleanUrls"] is True
    assert config["trailingSlash"] is False
    assert isinstance(config["headers"], list)
    assert isinstance(config["rewrites"], list)
    assert not ({"builds", "routes", "version", "public"} & set(config))


def test_vercel_build_is_pinned_locked_and_stages_only_the_web_output() -> None:
    config = _load_vercel_config()

    assert config["installCommand"] == ("python -m pip install uv==0.11.28 && uv sync --all-extras --locked")
    assert config["buildCommand"] == "uv run python -I tools/build_web.py --output dist/web"
    assert config["outputDirectory"] == "dist/web"
    assert "latest" not in config["installCommand"].lower()
    assert config["installCommand"].count("uv==0.11.28") == 1


def test_vercel_security_headers_apply_to_every_response() -> None:
    config = _load_vercel_config()
    security_rule = config["headers"][0]

    assert set(security_rule) == {"source", "headers"}
    assert security_rule["source"] == "/(.*)"
    assert _header_map(security_rule) == {
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Content-Type-Options": "nosniff",
    }


def test_vercel_cache_policy_revalidates_every_stable_artifact() -> None:
    config = _load_vercel_config()
    cache_rules = [
        (rule["source"], _header_map(rule)["Cache-Control"])
        for rule in config["headers"]
        if "Cache-Control" in _header_map(rule)
    ]

    assert cache_rules == [(_CACHE_SOURCE, _REVALIDATE)]
    assert all("immutable" not in value for _source, value in cache_rules)

    compiled = [(re.compile(source), value) for source, value in cache_rules]
    stable_paths = (
        "/",
        "/index",
        "/index.html",
        "/build-info.json",
        "/service-worker.js",
        "/manifest.webmanifest",
        "/favicon.png",
        "/web-stage.apk",
        "/web-stage.tar.gz",
        "/runtime/module.wasm",
        "/play",
        "/campaign/stage-1",
        "/robots.txt",
        "/runtime.js.map",
    )
    for path in stable_paths:
        matches = [(source.pattern, value) for source, value in compiled if source.fullmatch(path)]
        assert matches == [(_CACHE_SOURCE, _REVALIDATE)], f"unsafe cache policy for {path}"


def test_spa_rewrite_preserves_real_assets_and_uses_clean_url_destination() -> None:
    config = _load_vercel_config()

    assert config["rewrites"] == [{"source": _SPA_SOURCE, "destination": "/index"}]
    spa_source = re.compile(config["rewrites"][0]["source"])
    for route in ("/", "/play", "/campaign/stage-1"):
        assert spa_source.fullmatch(route), f"SPA route is not rewritten: {route}"
    for asset in (
        "/index.html",
        "/build-info.json",
        "/web-stage.apk",
        "/runtime/module.wasm",
        "/.well-known/security.txt",
    ):
        assert not spa_source.fullmatch(asset), f"real asset would be swallowed: {asset}"


def test_vercel_source_upload_excludes_generated_and_private_state() -> None:
    patterns = _ignore_patterns()

    assert len(patterns) == len(set(patterns)), "duplicate ignore patterns obscure the upload policy"
    required_patterns = {
        ".agents",
        ".cache",
        ".codex",
        ".coverage",
        ".coverage.*",
        ".env",
        ".env.*",
        ".git",
        ".github",
        ".hypothesis",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".superpowers",
        ".tox",
        ".venv",
        ".vercel",
        ".vscode",
        "*.egg-info",
        "*.key",
        "*.p12",
        "*.pem",
        "*.pfx",
        "*.py[cod]",
        "/build.spec",
        "ENV",
        "__pycache__",
        "__pypackages__",
        "artifacts",
        "build",
        "dist",
        "docs",
        "env",
        "htmlcov",
        "node_modules",
        "playwright-report",
        "save",
        "test-results",
        "tests",
        "venv",
    }
    assert required_patterns <= set(patterns)

    excluded_samples = (
        ".env.production",
        ".superpowers/sdd/report.md",
        ".venv/Scripts/python.exe",
        "artifacts/release/windows.zip",
        "build/Windsprig/Windsprig.exe",
        "build.spec",
        "dist/web/index.html",
        "docs/superpowers/plans/distribution.md",
        "playwright-report/index.html",
        "save/profile.json",
        "test-results/browser/results.json",
        "tests/release/test_release_policy.py",
        "web/private.pem",
        "windsprig.egg-info/PKG-INFO",
        "windsprig/__pycache__/app.cpython-312.pyc",
    )
    for path in excluded_samples:
        assert _is_ignored(path, patterns), f"private or generated source would upload: {path}"


def test_vercel_source_upload_keeps_every_remote_build_input() -> None:
    patterns = _ignore_patterns()
    required_inputs = (
        ".vercelignore",
        "assets/LICENSES.md",
        "assets/generated/ui/favicon.png",
        "assets/generated/ui/social-card.png",
        "levels/level_01.json",
        "pyproject.toml",
        "tools/build_web.py",
        "tools/release_common.py",
        "tools/web_runtime.py",
        "tools/web_source_manifest.py",
        "uv.lock",
        "vercel.json",
        "web/index-shell.html",
        "web/main.py",
        "web/manifest.webmanifest",
        "web/runtime-manifest.json",
        "web/service-worker.js",
        "web/template.tmpl",
        "windsprig/__init__.py",
        "windsprig/app.py",
    )

    for path in required_inputs:
        assert (ROOT / path).is_file(), f"declared remote build input is missing: {path}"
        assert not _is_ignored(path, patterns), f"remote build input is excluded: {path}"

    dangerously_broad_patterns = {"*", "/*", "*.json", "*.lock", "*.py", "*.toml"}
    assert dangerously_broad_patterns.isdisjoint(patterns)


def test_release_documents_and_active_artifacts_are_consistent() -> None:
    assert verify_local_release(ROOT) == []


def test_public_release_copy_states_local_only_save_and_input_requirements() -> None:
    copy = (ROOT / "docs/launch/release-copy.md").read_text(encoding="utf-8")

    assert "No account or telemetry" in copy
    assert "keyboard or compatible gamepad" in copy
    assert "1024×576" in copy


def test_public_support_and_policy_documents_name_actionable_routes() -> None:
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")

    assert "%LOCALAPPDATA%/Windsprig" in support
    assert "github.com/minchang-KIm/windsprig/issues" in support
    assert "security/advisories/new" in security
    assert "1.0.x" in security
    assert all(term in privacy for term in ("No account", "No analytics", "No server save"))


def test_ci_covers_source_web_and_windows_artifacts() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert all(name in ci for name in ("source-tests:", "web-artifact:", "windows-artifact:"))
    assert "python -I tools/build_web.py" in ci
    assert "python tools/build_windows.py" in ci
    assert "tests/e2e/test_web_product.py" in ci
    assert "tests/e2e/test_web_pwa.py" in ci


def test_release_workflow_is_tag_bound_and_publishes_checksums() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'tags: ["v*.*.*"]' in release
    assert "contents: write" in release
    assert "--verify-tag" in release
    assert "gh release create" in release
    assert "*.sha256" in release
    assert "github.ref_name" in release
    assert "verify-and-package:" in release
    assert "publish-release:" in release
    assert "needs: verify-and-package" in release


def test_release_workflow_scopes_write_token_and_never_interpolates_tag_in_shell() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    run_blocks = re.findall(r"\n\s+run:\s*(?:\|\s*\n(?:(?:\s{10,}.*\n?)+)|[^\n]+)", release)

    assert release.count("GH_TOKEN: ${{ github.token }}") == 1
    assert release.count("REF_NAME: ${{ github.ref_name }}") == 2
    assert all("${{ github.ref_name }}" not in block for block in run_blocks)
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in release
    publish = release.split("  publish-release:", maxsplit=1)[1]
    assert "contents: write" in publish
    assert "uv run" not in publish
    assert "pytest" not in publish
    assert "tools/" not in publish


@pytest.mark.parametrize("relative", [".github/workflows/ci.yml", ".github/workflows/release.yml"])
def test_release_workflows_pin_third_party_actions(relative: str) -> None:
    workflow = (ROOT / relative).read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s+([^\s#]+)", workflow)

    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)


def test_live_verifier_reports_version_shell_commit_and_target_mismatch() -> None:
    from tools.verify_release import verify_live_web

    def fake_fetch(url: str) -> tuple[int, str]:
        if url.endswith("build-info.json"):
            return 200, json.dumps({"version": "0.9.0", "commit_sha": "x" * 40, "target": "windows"})
        return 200, "<title>Wrong</title>"

    errors = verify_live_web("https://example.invalid", "1.0.0", "d" * 40, fetcher=fake_fetch)

    assert errors == [
        "production commit mismatch",
        "production shell title missing",
        "production target mismatch",
        "production version mismatch",
    ]


def test_live_verifier_reports_network_and_malformed_metadata_without_raising() -> None:
    from tools.verify_release import verify_live_web

    def fake_fetch(url: str) -> tuple[int, str]:
        if url.endswith("build-info.json"):
            return 200, "{broken"
        raise OSError("offline")

    assert verify_live_web("https://example.invalid/", "1.0.0", "d" * 40, fetcher=fake_fetch) == [
        "production build info is invalid JSON",
        "production shell request failed: OSError",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://windsprig.invalid",
        "https://user@windsprig.invalid",
        "https://windsprig.invalid/path",
        "https://windsprig.invalid?preview=1",
    ],
)
def test_live_verifier_rejects_noncanonical_production_origins(url: str) -> None:
    from tools.verify_release import verify_live_web

    with pytest.raises(ValueError, match="canonical HTTPS origin"):
        verify_live_web(url, "1.0.0", "d" * 40, fetcher=lambda _url: (200, ""))


def test_sites_brief_and_required_link_contract_are_canonical() -> None:
    brief = (ROOT / "docs/launch/sites-brief.md").read_text(encoding="utf-8")
    links = json.loads((ROOT / "docs/qa/sites-link-check.json").read_text(encoding="utf-8"))

    assert "Catch the wind. Carry its echoes." in brief
    assert "30 hand-crafted stages · 6 multi-phase bosses · 90 hidden Wind Motes" in brief
    assert all(
        heading in brief
        for heading in ("## Gameplay", "## Six worlds", "## Local co-op", "## Accessibility", "## Press kit")
    )
    assert links == {
        "broken_links_allowed": 0,
        "required_http_status": 200,
        "required_labels": ["Play Windsprig", "Download for Windows", "Source", "Support", "Privacy"],
        "responsive_widths_px": [390, 768, 1440],
        "version": "1.0.0",
    }
