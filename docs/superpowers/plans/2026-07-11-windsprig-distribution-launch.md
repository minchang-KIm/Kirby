# Windsprig Distribution and Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, verify, publish, and evidence the camera-ready Windsprig browser, Windows, Vercel, Sites, and GitHub v1.0.0 release surfaces from one tagged commit.

**Architecture:** Consume the completed `windsprig` application through one async browser entry and one native entry. Deterministic build scripts stage immutable web and Windows artifacts with embedded version metadata, while CI independently tests both artifacts before Vercel, Sites, and GitHub release publication. Release verification reads machine-generated manifests and live endpoints instead of trusting build intent.

**Tech Stack:** Python 3.12, pygame-ce, Pygbag, PyInstaller, uv, pytest, Playwright for Python, GitHub Actions, Vercel static hosting, Sites, PowerShell on Windows runners.

## Global Constraints

- Public title: `Windsprig: Echoes of the Gale`; Python package and executable identity: `windsprig`.
- The public game, package, executable, window title, repository display name, documentation, screenshots, and website must not use Nintendo, Kirby, Return to Dream Land, or any Nintendo character, logo, visual asset, audio, level, or copy.
- Keep all six worlds, 30 stages, six unique bosses, and 90 stable Wind Motes in v1.0.0.
- Browser gameplay targets desktop Chromium with a physical keyboard or standards-compatible gamepad and a viewport of at least 1024×576.
- Vercel serves the canonical playable production URL; Sites serves the launch/press surface; GitHub hosts source, CI, immutable release archives, notes, notices, and SHA-256 checksums.
- Browser and Windows builds must come from the same tagged commit and embed the same semantic version and commit SHA.
- Browser cached start must be at most 5 seconds, cold start at most 12 seconds with visible progress, and compressed transfer target at most 30 MB.
- Windows saves must live under `%LOCALAPPDATA%/Windsprig`; browser saves remain local and are never transmitted.
- No public release may be declared complete without automated gates, computer/browser hands-on QA, live URL verification, and current evidence for every release-matrix row.

---

## File Structure

```text
web/
  main.py                         Pygbag entry invoking the shared async app
  index-shell.html                accessible branded launch/loading shell source
  manifest.webmanifest            install metadata
  service-worker.js               immutable runtime cache policy
  favicon.png                     original product icon from presentation plan
  social-card.png                 original release card from presentation plan
tools/
  build_web.py                    reproducible Pygbag build and shell staging
  build_windows.py                PyInstaller staging, archive, and hash generation
  release_common.py               version/SHA/manifests and deterministic ZIP helpers
  verify_release.py               local artifact and live endpoint verifier
packaging/
  windows.spec                    supported PyInstaller entry and data manifest
  version_info.txt                Windows product/file metadata
  smoke-config.json               isolated packaged-app smoke route
dist/
  web/                            ignored generated static artifact
  release/                        ignored generated Windows/web archives and hashes
.github/workflows/
  ci.yml                          source, browser, and Windows validation
  release.yml                     tag-bound immutable artifact publication
tests/release/
  test_release_common.py
  test_build_web.py
  test_build_windows.py
  test_release_policy.py
tests/e2e/
  conftest.py
  test_web_product.py
vercel.json                       canonical static deployment contract
.vercelignore                     source exclusions that cannot affect staged output
.openai/hosting.json              Sites launch-surface hosting metadata
docs/launch/
  sites-brief.md                  exact editorial content and asset inventory
  release-copy.md                 canonical title, description, controls, support copy
docs/qa/
  v1.0.0-checklist.md             human release checklist and evidence index
CHANGELOG.md
CREDITS.md
PRIVACY.md
SECURITY.md
SUPPORT.md
```

## Shared Interfaces Consumed

These interfaces are produced by the earlier foundation, gameplay, and presentation plans. If an earlier plan uses a different name, reconcile that earlier plan before starting this plan; do not introduce an adapter with duplicate semantics.

```python
# windsprig/app.py
class GameApp:
    def __init__(self, config: GameConfig, services: PlatformServices, screen_factory: ScreenFactory) -> None: ...
    async def run(self) -> int: ...
    async def run_frame(self) -> None: ...

# windsprig/platform/services.py
@dataclass(frozen=True)
class PlatformServices:
    storage: StorageService
    audio: AudioService
    display: DisplayService
    time: TimeService
    lifecycle: LifecycleService
    browser: BrowserBridge | None
    capabilities: PlatformCapabilities

# windsprig/platform/web.py
def create_web_services(config: GameConfig, window: object | None = None) -> PlatformServices: ...

# windsprig/platform/native.py
def create_native_services(config: GameConfig) -> PlatformServices: ...

# windsprig/bootstrap.py
def create_product_screen_factory(
    config: GameConfig,
    services: PlatformServices,
    now_utc: Callable[[], datetime],
) -> ProductScreenFactory: ...
```

---

### Task 1: Deterministic release metadata and archive primitives

**Files:**
- Create: `tools/release_common.py`
- Create: `tests/release/test_release_common.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `pyproject.toml` project version and `git rev-parse HEAD`.
- Produces: `BuildIdentity`, `read_build_identity()`, `write_build_manifest()`, `sha256_file()`, and `write_reproducible_zip()` for every later artifact task.

- [ ] **Step 1: Write failing metadata, hash, and ZIP reproducibility tests**

```python
# tests/release/test_release_common.py
from __future__ import annotations

import json
from pathlib import Path
import zipfile

from tools.release_common import (
    BuildIdentity,
    sha256_file,
    write_build_manifest,
    write_reproducible_zip,
)


def test_manifest_contains_one_version_sha_and_target(tmp_path: Path) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="a" * 40, target="web")
    destination = tmp_path / "build-info.json"
    write_build_manifest(destination, identity, files=["index.html", "game.apk"])
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "commit_sha": "a" * 40,
        "files": ["game.apk", "index.html"],
        "target": "web",
        "version": "1.0.0",
    }


def test_reproducible_zip_has_stable_bytes_and_sorted_members(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "z.txt").write_text("z", encoding="utf-8")
    (source / "a.txt").write_text("a", encoding="utf-8")
    first = write_reproducible_zip(source, tmp_path / "first.zip")
    second = write_reproducible_zip(source, tmp_path / "second.zip")
    assert sha256_file(first) == sha256_file(second)
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["a.txt", "z.txt"]
        assert {item.date_time for item in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
```

- [ ] **Step 2: Run the focused tests and confirm the missing module failure**

Run: `uv run pytest tests/release/test_release_common.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'tools.release_common'`.

- [ ] **Step 3: Implement deterministic metadata and archives**

```python
# tools/release_common.py
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
from typing import Literal
import zipfile


Target = Literal["web", "windows", "source"]


@dataclass(frozen=True)
class BuildIdentity:
    version: str
    commit_sha: str
    target: Target


def read_build_identity(root: Path, target: Target) -> BuildIdentity:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if len(commit) != 40:
        raise ValueError(f"expected a full git SHA, received {commit!r}")
    return BuildIdentity(version=str(project["version"]), commit_sha=commit, target=target)


def write_build_manifest(path: Path, identity: BuildIdentity, files: list[str]) -> Path:
    payload = asdict(identity) | {"files": sorted(files)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_reproducible_zip(source_dir: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(source_dir).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    return destination
```

Append the generated output exclusions to `.gitignore`:

```gitignore
dist/web/
dist/release/
web/build/
.vercel/
test-results/
playwright-report/
```

- [ ] **Step 4: Run the tests and verify deterministic output**

Run: `uv run pytest tests/release/test_release_common.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit the release primitives**

```powershell
git add tools/release_common.py tests/release/test_release_common.py .gitignore
git commit -m "build: add deterministic release manifests"
```

---

### Task 2: Web entry point and reproducible Pygbag staging

**Files:**
- Modify: `web/main.py`
- Modify: `tools/build_web.py`
- Create: `tests/release/test_build_web.py`

**Interfaces:**
- Consumes: the foundation plan's proven `web/main.py`, `build_web(probe: bool)`, Pygbag 0.9.3 pin, and Task 1 release helpers.
- Produces: `python tools/build_web.py --output dist/web`, a static artifact containing `index.html`, Pygbag runtime files, application archive, and `build-info.json`.

- [ ] **Step 1: Write a failing test for staging and release metadata**

```python
# tests/release/test_build_web.py
from __future__ import annotations

import json
from pathlib import Path

from tools.build_web import attach_release_manifest
from tools.release_common import BuildIdentity


def test_attach_release_manifest_indexes_staged_runtime(tmp_path: Path) -> None:
    output = tmp_path / "web"
    output.mkdir()
    (output / "index.html").write_text("<canvas id='canvas'></canvas>", encoding="utf-8")
    (output / "windsprig.apk").write_bytes(b"game")
    identity = BuildIdentity("1.0.0", "b" * 40, "web")
    attach_release_manifest(output, identity)
    manifest = json.loads((output / "build-info.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0"
    assert manifest["commit_sha"] == "b" * 40
    assert manifest["files"] == ["index.html", "windsprig.apk"]
```

- [ ] **Step 2: Run the focused test and confirm the missing module failure**

Run: `uv run pytest tests/release/test_build_web.py -q`

Expected: collection fails because the foundation builder does not yet export `attach_release_manifest`.

- [ ] **Step 3: Verify the shared browser entry remains the proven foundation entry**

```python
# tests/release/test_build_web.py
def test_web_entry_uses_shared_game_app_without_native_shutdown() -> None:
    source = (Path(__file__).resolve().parents[2] / "web" / "main.py").read_text(encoding="utf-8")
    assert "from windsprig.app import GameApp" in source
    assert "create_product_screen_factory" in source
    assert "create_web_services" in source
    assert "asyncio.run(main())" in source
    assert "pygame.quit" not in source
    assert "SystemExit" not in source
```

Do not replace `web/main.py` with a second app-construction API. Browser query parameters remain behind the foundation `BrowserBridge.query_param()` boundary.

- [ ] **Step 4: Extend the proven builder with release identity**

```python
# additions to tools/build_web.py
from tools.release_common import BuildIdentity, read_build_identity, write_build_manifest

def attach_release_manifest(output: Path, identity: BuildIdentity) -> Path:
    if not (output / "index.html").is_file():
        raise FileNotFoundError(f"Pygbag did not create {output / 'index.html'}")
    files = [
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and path.name != "build-info.json"
    ]
    write_build_manifest(output / "build-info.json", identity, files)
    return output / "build-info.json"
```

Change the foundation builder signature to `build_web(probe: bool, output: Path | None = None) -> dict[str, object]`; resolve `output` to `ROOT / "dist" / "web"` when omitted. After Pygbag output, shell staging, and size reporting succeed, call:

```python
attach_release_manifest(output, read_build_identity(ROOT, "web"))
```

Extend its existing `argparse` parser with `--output`; retain `--probe`. Do not add another Pygbag invocation or dependency table. The foundation lock already pins `pygbag==0.9.3` and `playwright==1.61.0` under the `web` extra.

- [ ] **Step 5: Run the unit test, then build the actual artifact**

Run: `uv run pytest tests/release/test_build_web.py -q`

Expected: `1 passed`.

Run: `uv run python tools/build_web.py --output dist/web`

Expected: exit 0; `dist/web/index.html`, an application archive, and `dist/web/build-info.json` exist; the manifest SHA equals `git rev-parse HEAD`.

- [ ] **Step 6: Commit the reproducible web build**

```powershell
git add web/main.py tools/build_web.py tests/release/test_build_web.py
git commit -m "build: stage reproducible Pygbag web artifacts"
```

---

### Task 3: Branded accessible PWA shell and cache policy

**Files:**
- Create: `web/index-shell.html`
- Create: `web/manifest.webmanifest`
- Create: `web/service-worker.js`
- Modify: `tools/build_web.py`
- Modify: `tests/release/test_build_web.py`

**Interfaces:**
- Consumes: the staged Pygbag `index.html` from Task 2 and the original icon/social art from the presentation plan.
- Produces: a branded shell with loading status, skip link, keyboard/gamepad requirements, privacy-safe metadata, install manifest, and immutable application cache.

- [ ] **Step 1: Extend the test with shell, manifest, and service-worker assertions**

```python
# append to tests/release/test_build_web.py
from tools.build_web import apply_web_shell


def test_apply_web_shell_injects_accessible_metadata(tmp_path: Path) -> None:
    output = tmp_path / "dist"
    output.mkdir()
    (output / "index.html").write_text(
        "<html><head></head><body><canvas id='canvas'></canvas></body></html>", encoding="utf-8"
    )
    source = tmp_path / "web"
    source.mkdir()
    (source / "manifest.webmanifest").write_text('{"name":"Windsprig: Echoes of the Gale"}', encoding="utf-8")
    (source / "service-worker.js").write_text("const CACHE='windsprig-v1.0.0';", encoding="utf-8")
    apply_web_shell(output, source)
    html = (output / "index.html").read_text(encoding="utf-8")
    assert '<meta name="theme-color" content="#10233f">' in html
    assert 'aria-live="polite"' in html
    assert 'Windsprig: Echoes of the Gale' in html
    assert (output / "manifest.webmanifest").is_file()
    assert (output / "service-worker.js").is_file()
```

- [ ] **Step 2: Run the focused test and confirm the missing function failure**

Run: `uv run pytest tests/release/test_build_web.py::test_apply_web_shell_injects_accessible_metadata -q`

Expected: import fails because `apply_web_shell` is not defined.

- [ ] **Step 3: Add the exact release shell source**

```html
<!-- web/index-shell.html -->
<meta name="theme-color" content="#10233f">
<meta name="description" content="Ride the living wind, harmonize enemy echoes, and restore six hand-crafted sky worlds—solo or with up to four local players.">
<meta property="og:title" content="Windsprig: Echoes of the Gale">
<meta property="og:description" content="A storybook action-platform adventure playable in your browser.">
<meta property="og:image" content="/social-card.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/favicon.png">
<style>
  :root { color-scheme: dark; font-family: "Noto Sans KR", system-ui, sans-serif; background: #071426; color: #f7fbff; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: radial-gradient(circle at 50% 15%, #27577c, #071426 68%); }
  #windsprig-loader { position: fixed; inset: 0; display: grid; place-items: center; text-align: center; z-index: 3; }
  #windsprig-loader > div { max-width: 42rem; padding: 2rem; border: 2px solid #d8f27c; border-radius: 1.25rem; background: #10233fee; box-shadow: 0 1.5rem 5rem #0008; }
  #windsprig-loader h1 { margin: 0 0 .75rem; color: #f7fbff; }
  #windsprig-loader p { margin: .5rem 0; line-height: 1.5; }
  #windsprig-status { color: #d8f27c; font-weight: 700; }
  .skip-link { position: fixed; left: 1rem; top: -4rem; z-index: 10; padding: .75rem 1rem; background: #f7fbff; color: #071426; }
  .skip-link:focus { top: 1rem; }
  canvas { max-width: 100vw; max-height: 100vh; outline: none; }
</style>
<a class="skip-link" href="#canvas">Skip to game canvas</a>
<section id="windsprig-loader" aria-labelledby="windsprig-title">
  <div>
    <h1 id="windsprig-title">Windsprig: Echoes of the Gale</h1>
    <p id="windsprig-status" aria-live="polite">Gathering the wind…</p>
    <p>Requires a keyboard or compatible gamepad and a viewport of at least 1024×576.</p>
    <p>Your profiles stay in this browser. No account or telemetry is used.</p>
  </div>
</section>
<script>
  window.addEventListener("load", () => {
    navigator.serviceWorker?.register("/service-worker.js");
  });
</script>
```

```json
{
  "name": "Windsprig: Echoes of the Gale",
  "short_name": "Windsprig",
  "description": "A storybook local-co-op action-platform adventure.",
  "start_url": "/",
  "display": "fullscreen",
  "background_color": "#071426",
  "theme_color": "#10233f",
  "icons": [
    {"src": "/favicon.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/social-card.png", "sizes": "1200x630", "type": "image/png", "purpose": "any"}
  ]
}
```

```javascript
// web/service-worker.js
const CACHE = "windsprig-v1.0.0";
const CORE = ["/", "/manifest.webmanifest", "/favicon.png", "/social-card.png", "/build-info.json"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE))));
self.addEventListener("activate", event => event.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
));
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const networkFirst = event.request.mode === "navigate" || ["/build-info.json", "/service-worker.js"].includes(url.pathname);
  if (networkFirst) {
    event.respondWith(fetch(event.request).then(response => {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, copy));
    }
    return response;
  })));
});
```

- [ ] **Step 4: Implement deterministic shell injection**

```python
# add to tools/build_web.py
def apply_web_shell(output: Path, source: Path) -> None:
    index = output / "index.html"
    html = index.read_text(encoding="utf-8")
    shell = (source / "index-shell.html").read_text(encoding="utf-8")
    if "<head>" not in html or "<body>" not in html:
        raise ValueError("Pygbag index is missing head/body insertion points")
    head, body = shell.split('<a class="skip-link"', maxsplit=1)
    html = html.replace("<head>", "<head>" + head, 1)
    html = html.replace("<body>", '<body><a class="skip-link"' + body, 1)
    index.write_text(html, encoding="utf-8")
    for name in ("manifest.webmanifest", "service-worker.js", "favicon.png", "social-card.png"):
        shutil.copy2(source / name, output / name)
```

Call `apply_web_shell(output, ROOT / "web")` immediately before `attach_release_manifest()` writes the final file list.

- [ ] **Step 5: Run the web build tests and actual build**

Run: `uv run pytest tests/release/test_build_web.py -q`

Expected: all tests pass.

Run: `uv run python tools/build_web.py --output dist/web`

Expected: exit 0; the final HTML contains one `#windsprig-loader`; the manifest lists the shell, manifest, worker, icon, and card.

- [ ] **Step 6: Commit the PWA shell**

```powershell
git add web tools/build_web.py tests/release/test_build_web.py
git commit -m "feat(web): add accessible Windsprig launch shell"
```

---

### Task 4: Browser product E2E and startup budgets

**Files:**
- Modify: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_web_product.py`
- Modify: `windsprig/app.py`
- Modify: `windsprig/platform/services.py`
- Modify: `windsprig/platform/web.py`

**Interfaces:**
- Consumes: `BrowserBridge.query_param("e2e")`, the existing foundation web services, and the `dist/web` artifact.
- Produces: a read-only `window.__WINSPRIG_TEST__` status bridge available only when `?e2e=1`, plus Playwright evidence for boot, input, save reload, canvas rendering, console cleanliness, and transfer/startup budgets.

- [ ] **Step 1: Add failing browser tests**

```python
# tests/e2e/conftest.py
from __future__ import annotations

from contextlib import closing
import socket
from pathlib import Path
import subprocess
import sys
import time

import pytest


@pytest.fixture(scope="session")
def web_url() -> str:
    root = Path(__file__).resolve().parents[2] / "dist" / "web"
    if not (root / "index.html").is_file():
        pytest.fail("dist/web is missing; run tools/build_web.py first")
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--directory", str(root)])
    try:
        time.sleep(0.5)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        process.wait(timeout=5)
```

```python
# tests/e2e/test_web_product.py
from __future__ import annotations

from playwright.sync_api import Page, expect


def wait_for_state(page: Page, state: str) -> None:
    page.wait_for_function(
        "expected => window.__WINSPRIG_TEST__?.state === expected", state, timeout=12_000
    )


def test_web_boot_input_render_and_save_reload(page: Page, web_url: str) -> None:
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto(f"{web_url}/?e2e=1", wait_until="domcontentloaded")
    wait_for_state(page, "title")
    expect(page.locator("canvas")).to_be_visible()
    assert page.locator("canvas").screenshot() != b""
    page.keyboard.press("Enter")
    wait_for_state(page, "profile_select")
    page.keyboard.press("Enter")
    wait_for_state(page, "world_map")
    assert page.evaluate("() => window.__WINSPRIG_TEST__.saveVersion") == 2
    page.reload(wait_until="domcontentloaded")
    wait_for_state(page, "world_map")
    assert console_errors == []


def test_cached_boot_meets_five_second_budget(page: Page, web_url: str) -> None:
    page.goto(f"{web_url}/?e2e=1")
    wait_for_state(page, "title")
    page.reload(wait_until="domcontentloaded")
    elapsed_ms = page.evaluate("""async () => {
      const start = performance.now();
      while (window.__WINSPRIG_TEST__?.state !== 'title') await new Promise(r => setTimeout(r, 16));
      return performance.now() - start;
    }""")
    assert elapsed_ms <= 5_000
```

- [ ] **Step 2: Run the tests and verify the missing test bridge failure**

Run: `uv run playwright install chromium`

Run: `uv run pytest tests/e2e/test_web_product.py -q`

Expected: tests fail after page load because `window.__WINSPRIG_TEST__` is undefined.

- [ ] **Step 3: Expose a read-only E2E status bridge in the web adapter**

```python
# add to windsprig/platform/services.py and windsprig/platform/web.py
from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class WebTestStatus:
    state: str
    saveVersion: int


class BrowserBridge(Protocol):
    # Retain every foundation method and add this diagnostic-only operation.
    def publish_diagnostic(self, name: str, payload: Mapping[str, object]) -> None: ...


def publish_test_status(bridge: BrowserBridge | None, status: WebTestStatus) -> None:
    if bridge is None or bridge.query_param("e2e") != "1":
        return
    bridge.publish_diagnostic("__WINSPRIG_TEST__", asdict(status))
```

`PygbagBrowserBridge.publish_diagnostic()` creates a JavaScript object, copies only string/integer/boolean payload values, and assigns it to `window[name]`; it raises `TypeError` for any other value. Call `publish_test_status(services.browser, status)` after each screen transition and successful save. The bridge is disabled unless the URL contains `?e2e=1`, exposes no mutation hook, and is never included in deterministic state.

Retain the foundation lock pins `playwright==1.61.0` and `pygbag==0.9.3`; this task adds no second dependency group.

- [ ] **Step 4: Run the E2E tests and capture the transfer report**

Run: `uv run python tools/build_web.py --output dist/web`

Run: `uv run pytest tests/e2e/test_web_product.py -q`

Expected: both tests pass in Chromium with no console errors.

Run: `Get-ChildItem -Recurse -File dist/web | Measure-Object -Property Length -Sum`

Expected: total uncompressed staged size is reported and the corresponding compressed web archive created by the Task 12 release audit is at most 30 MB.

- [ ] **Step 5: Commit browser E2E coverage**

```powershell
git add tests/e2e windsprig/app.py windsprig/platform/services.py windsprig/platform/web.py
git commit -m "test(web): verify browser boot input and persistence"
```

---

### Task 5: Vercel static deployment contract

**Files:**
- Create: `vercel.json`
- Create: `.vercelignore`
- Create: `tests/release/test_release_policy.py`

**Interfaces:**
- Consumes: `dist/web` from Task 2 and the browser test suite from Task 4.
- Produces: one canonical static deployment configuration with correct output, routes, security headers, and immutable asset caching.

- [ ] **Step 1: Write failing Vercel policy tests**

```python
# tests/release/test_release_policy.py
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_vercel_serves_only_the_staged_web_artifact() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["installCommand"] == "python -m pip install uv==0.11.28 && uv sync --all-extras --locked"
    assert config["buildCommand"] == "uv run python tools/build_web.py --output dist/web"
    assert config["outputDirectory"] == "dist/web"
    assert {header["key"] for rule in config["headers"] for header in rule["headers"]} >= {
        "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"
    }


def test_vercel_source_upload_excludes_native_and_private_build_state() -> None:
    ignored = set((ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines())
    assert {".venv", "build", "dist/release", "save", "tests"} <= ignored
```

- [ ] **Step 2: Run the policy tests and confirm missing configuration failure**

Run: `uv run pytest tests/release/test_release_policy.py -q`

Expected: failures report missing `vercel.json` and `.vercelignore`.

- [ ] **Step 3: Add the exact Vercel contract**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "installCommand": "python -m pip install uv==0.11.28 && uv sync --all-extras --locked",
  "buildCommand": "uv run python tools/build_web.py --output dist/web",
  "outputDirectory": "dist/web",
  "cleanUrls": true,
  "trailingSlash": false,
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {"key": "X-Content-Type-Options", "value": "nosniff"},
        {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
        {"key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=(), payment=()"}
      ]
    },
    {
      "source": "/(.*)\\.(wasm|apk|data|png|ogg|woff2)",
      "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]
    },
    {
      "source": "/(index.html|build-info.json|service-worker.js)",
      "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]
    }
  ],
  "rewrites": [{"source": "/((?!.*\\.).*)", "destination": "/index.html"}]
}
```

```text
# .vercelignore
.git
.github
.hypothesis
.pytest_cache
.venv
build
dist/release
docs
save
tests
__pycache__
*.coverage
```

- [ ] **Step 4: Run policy and local Vercel builds**

Run: `uv run pytest tests/release/test_release_policy.py -q`

Expected: both tests pass.

Run: `vercel build`

Expected: exit 0; Vercel reports `dist/web` as the static output and does not upload `save`, `.venv`, or test state.

- [ ] **Step 5: Commit the deployment contract**

```powershell
git add vercel.json .vercelignore tests/release/test_release_policy.py
git commit -m "deploy: configure canonical Vercel web build"
```

---

### Task 6: Windows package, metadata, smoke route, and checksums

**Files:**
- Replace: `build.spec` with `packaging/windows.spec`
- Create: `packaging/version_info.txt`
- Create: `packaging/smoke-config.json`
- Create: `tools/build_windows.py`
- Create: `tests/release/test_build_windows.py`
- Modify: `windsprig/__main__.py`
- Modify: `windsprig/platform/native.py`

**Interfaces:**
- Consumes: `GameApp`, `create_product_screen_factory()`, the factory's shared `ProductScreenContext`, release helpers, original icon, asset/content directories, license and notices.
- Produces: `dist/release/Windsprig-1.0.0-windows-x64.zip`, matching `.sha256`, embedded `build-info.json`, and a packaged smoke command that exits 0 after mandatory initialization and one deterministic render/save cycle.

- [ ] **Step 1: Write failing staging and smoke-CLI tests**

```python
# tests/release/test_build_windows.py
from __future__ import annotations

import json
from pathlib import Path

from tools.build_windows import stage_windows_release
from tools.release_common import BuildIdentity, sha256_file


def test_stage_windows_release_contains_notices_metadata_and_hash(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "Windsprig.exe").write_bytes(b"exe")
    root = tmp_path / "root"
    root.mkdir()
    (root / "LICENSE").write_text("MIT", encoding="utf-8")
    (root / "CREDITS.md").write_text("Credits", encoding="utf-8")
    destination = tmp_path / "release"
    identity = BuildIdentity("1.0.0", "c" * 40, "windows")
    archive, checksum = stage_windows_release(bundle, root, destination, identity)
    assert archive.name == "Windsprig-1.0.0-windows-x64.zip"
    assert checksum.read_text(encoding="ascii").split()[0] == sha256_file(archive)
    assert json.loads((bundle / "build-info.json").read_text(encoding="utf-8"))["target"] == "windows"
```

```python
# append to tests/release/test_build_windows.py
def test_native_module_help_lists_isolated_smoke_arguments() -> None:
    import subprocess, sys
    result = subprocess.run([sys.executable, "-m", "windsprig", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--smoke-test" in result.stdout
    assert "--data-dir" in result.stdout
```

- [ ] **Step 2: Run focused tests and confirm missing builder/CLI failures**

Run: `uv run pytest tests/release/test_build_windows.py -q`

Expected: collection fails because `tools.build_windows` does not exist.

- [ ] **Step 3: Add the supported native CLI**

```python
# windsprig/__main__.py
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pygame

from windsprig.app import GameApp
from windsprig.bootstrap import create_product_screen_factory
from windsprig.config import GameConfig
from windsprig.platform.native import create_native_services


async def run_native(*, smoke_test: bool = False, data_dir: Path | None = None) -> int:
    pygame.init()
    config = GameConfig()
    services = create_native_services(config, data_dir=data_dir)
    factory = create_product_screen_factory(config, services, lambda: datetime.now(timezone.utc))
    services.display.create_window(config.resolution, config.fullscreen)
    app = GameApp(config, services, factory)
    try:
        if not smoke_test:
            return await app.run()
        for _ in range(3):
            await app.run_frame()
        context = factory.context
        profile = replace(context.save_data.profiles[0], display_name="Package Smoke")
        data = replace(
            context.save_data,
            profiles=(profile, context.save_data.profiles[1], context.save_data.profiles[2]),
        )
        return 0 if context.save_service.save(data).ok else 2
    finally:
        pygame.quit()


def main() -> int:
    parser = argparse.ArgumentParser(prog="Windsprig")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    return asyncio.run(run_native(smoke_test=args.smoke_test, data_dir=args.data_dir))


if __name__ == "__main__":
    raise SystemExit(main())
```

Extend the foundation native factory signature to `create_native_services(config: GameConfig, data_dir: Path | None = None)`. When `data_dir` is provided, resolve it and pass it to `NativeStorage`; otherwise retain the required `%LOCALAPPDATA%/Windsprig` default. This override exists only for tests and portable package diagnostics.

- [ ] **Step 4: Implement Windows staging and deterministic checksum generation**

```python
# tools/build_windows.py
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

from tools.release_common import BuildIdentity, read_build_identity, sha256_file, write_build_manifest, write_reproducible_zip


ROOT = Path(__file__).resolve().parents[1]


def stage_windows_release(
    bundle: Path, root: Path, destination: Path, identity: BuildIdentity
) -> tuple[Path, Path]:
    for name in ("LICENSE", "CREDITS.md"):
        shutil.copy2(root / name, bundle / name)
    files = [path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()]
    write_build_manifest(bundle / "build-info.json", identity, files)
    archive = write_reproducible_zip(bundle, destination / f"Windsprig-{identity.version}-windows-x64.zip")
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{sha256_file(archive)}  {archive.name}\n", encoding="ascii")
    return archive, checksum


def build(output: Path) -> None:
    identity = read_build_identity(ROOT, "windows")
    subprocess.run(["pyinstaller", "packaging/windows.spec", "--noconfirm", "--clean"], cwd=ROOT, check=True)
    bundle = ROOT / "dist" / "Windsprig"
    smoke_dir = ROOT / "build" / "smoke-data"
    subprocess.run(
        [str(bundle / "Windsprig.exe"), "--smoke-test", "--data-dir", str(smoke_dir)],
        cwd=ROOT,
        check=True,
        timeout=30,
    )
    stage_windows_release(bundle, ROOT, output, identity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "release")
    args = parser.parse_args()
    build(args.output.resolve())
```

- [ ] **Step 5: Replace the unsupported spec with the package-aware spec**

```python
# packaging/windows.spec
from pathlib import Path

root = Path(SPECPATH).parent.parent
datas = [
    (str(root / "windsprig" / "content"), "windsprig/content"),
    (str(root / "assets"), "assets"),
    (str(root / "LICENSE"), "."),
    (str(root / "CREDITS.md"), "."),
]
a = Analysis(
    [str(root / "windsprig" / "__main__.py")],
    pathex=[str(root)],
    datas=datas,
    hiddenimports=["pygame"],
    excludes=["pytest", "hypothesis", "playwright", "pygbag"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Windsprig", console=False,
    icon=str(root / "assets" / "branding" / "windsprig.ico"),
    version=str(root / "packaging" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Windsprig")
```

Create the complete PyInstaller version resource below. `Snowball_tree` is copied from the existing root `LICENSE`; do not replace it with an invented person or company.

```python
# packaging/version_info.txt
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040904B0",
        [
          StringStruct("FileDescription", "Windsprig: Echoes of the Gale"),
          StringStruct("FileVersion", "1.0.0.0"),
          StringStruct("InternalName", "Windsprig"),
          StringStruct("LegalCopyright", "Copyright (c) 2026 Snowball_tree"),
          StringStruct("OriginalFilename", "Windsprig.exe"),
          StringStruct("ProductName", "Windsprig: Echoes of the Gale"),
          StringStruct("ProductVersion", "1.0.0.0"),
        ],
      )
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])]),
  ],
)
```

Create `packaging/smoke-config.json`:

```json
{"frames": 3, "expect_screen": "title", "save_profile": "Package Smoke", "exit_code": 0}
```

- [ ] **Step 6: Run unit, clean package, smoke, metadata, and archive checks**

Run: `uv run pytest tests/release/test_build_windows.py -q`

Expected: all tests pass.

Run: `uv run python tools/build_windows.py --output dist/release`

Expected: exit 0; packaged smoke exits within 30 seconds; the ZIP and `.sha256` exist.

Run: `(Get-Item 'dist/Windsprig/Windsprig.exe').VersionInfo | Format-List ProductName,FileDescription,FileVersion,ProductVersion,OriginalFilename`

Expected: all five fields are populated with Windsprig and `1.0.0.0` values.

- [ ] **Step 7: Commit Windows distribution**

```powershell
git rm build.spec
git add packaging tools/build_windows.py tests/release/test_build_windows.py windsprig/__main__.py windsprig/platform/native.py
git commit -m "build(windows): package and smoke-test Windsprig"
```

---

### Task 7: Canonical release copy, notices, support, and policy scan

**Files:**
- Rewrite: `README.md`
- Rewrite: `assets/LICENSES.md`
- Create: `CHANGELOG.md`
- Create: `CREDITS.md`
- Create: `PRIVACY.md`
- Create: `SECURITY.md`
- Create: `SUPPORT.md`
- Create: `docs/launch/release-copy.md`
- Create: `tools/verify_release.py`
- Extend: `tests/release/test_release_policy.py`

**Interfaces:**
- Consumes: public identity, package metadata, asset/audio/font provenance, release manifests.
- Produces: one canonical copy source and `verify_local_release(root: Path) -> list[str]`, returning an empty list only when required local release evidence is present and consistent.

- [ ] **Step 1: Write failing release-policy tests**

```python
# append to tests/release/test_release_policy.py
from tools.verify_release import verify_local_release


def test_release_documents_and_active_artifacts_are_consistent() -> None:
    assert verify_local_release(ROOT) == []


def test_public_release_copy_states_local_only_save_and_input_requirements() -> None:
    copy = (ROOT / "docs/launch/release-copy.md").read_text(encoding="utf-8")
    assert "No account or telemetry" in copy
    assert "keyboard or compatible gamepad" in copy
    assert "1024×576" in copy
```

- [ ] **Step 2: Run policy tests and confirm missing-document failures**

Run: `uv run pytest tests/release/test_release_policy.py -q`

Expected: collection or assertions fail for the missing verifier and launch copy.

- [ ] **Step 3: Write the exact canonical release copy and policy documents**

`docs/launch/release-copy.md` must contain this canonical summary verbatim:

```markdown
# Windsprig: Echoes of the Gale

Ride the living wind, harmonize enemy echoes, and restore six hand-crafted sky worlds in a storybook action-platform adventure for one to four local players.

Play in a desktop Chromium browser or download the Windows x64 release. Browser play requires a keyboard or compatible gamepad and a viewport of at least 1024×576. No account or telemetry is used; browser profiles stay in that browser, and Windows profiles stay under `%LOCALAPPDATA%/Windsprig`.
```

The rewritten README must include: the canonical summary, current Vercel Play link, Sites press link, GitHub Releases link, two verified screenshots, browser/Windows requirements, exact keyboard/gamepad controls, accessibility features, correct `uv sync`/test/build commands, support/privacy/security links, and original-identity notice. `CHANGELOG.md` starts with `## [1.0.0] - 2026-07-11`. `CREDITS.md` lists each asset/font/audio source from `assets/LICENSES.md`, the code license holder from `LICENSE`, and no invented legal identity. `PRIVACY.md` states that the static product has no account, analytics, server save, or intentional data transmission. `SUPPORT.md` gives save locations, browser reset steps, controller troubleshooting, and the GitHub issue URL. `SECURITY.md` provides the repository's private GitHub vulnerability-reporting route and supported version `1.0.x`.

- [ ] **Step 4: Implement strict release verification**

```python
# tools/verify_release.py
from __future__ import annotations

import json
from pathlib import Path
import re


PUBLIC_PATHS = (
    "README.md", "CHANGELOG.md", "CREDITS.md", "PRIVACY.md", "SECURITY.md", "SUPPORT.md",
    "windsprig", "web", "packaging",
)
REQUIRED_FILES = (
    "LICENSE", "README.md", "CHANGELOG.md", "CREDITS.md", "PRIVACY.md", "SECURITY.md",
    "SUPPORT.md", "assets/LICENSES.md", "docs/launch/release-copy.md",
)


def verify_local_release(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing required release file: {relative}")
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "1.0.0"' not in project:
        errors.append("pyproject version is not 1.0.0")
    banned = re.compile(r"kirby|return to dream land", re.IGNORECASE)
    for relative in PUBLIC_PATHS:
        path = root / relative
        files = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for file in files:
            if file.suffix.lower() in {".png", ".ico", ".ogg", ".wav", ".woff2"}:
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            if banned.search(text):
                errors.append(f"protected prototype identifier in public path: {file.relative_to(root)}")
    for target in ("web", "windows"):
        manifest = root / ("dist/web/build-info.json" if target == "web" else "dist/Windsprig/build-info.json")
        if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))["version"] != "1.0.0":
            errors.append(f"{target} manifest version mismatch")
    return errors
```

- [ ] **Step 5: Run policy verification and link checks**

Run: `uv run pytest tests/release/test_release_policy.py -q`

Expected: all tests pass.

Run: `uv run python -c "from pathlib import Path; from tools.verify_release import verify_local_release; errors=verify_local_release(Path('.')); print(*errors, sep='\n'); raise SystemExit(bool(errors))"`

Expected: exit 0 with no output.

- [ ] **Step 6: Commit release documentation and policy**

```powershell
git add README.md assets/LICENSES.md CHANGELOG.md CREDITS.md PRIVACY.md SECURITY.md SUPPORT.md docs/launch tools/verify_release.py tests/release/test_release_policy.py
git commit -m "docs: prepare Windsprig v1 release materials"
```

---

### Task 8: GitHub source and artifact CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Extend: `tests/release/test_release_policy.py`

**Interfaces:**
- Consumes: all source/test/build commands from earlier plans.
- Produces: required source, web, Windows, and release checks; tag-bound archives created on GitHub-hosted clean runners.

- [ ] **Step 1: Add failing workflow contract tests**

```python
# append to tests/release/test_release_policy.py
def test_ci_covers_source_web_and_windows_artifacts() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert all(name in ci for name in ("source-tests:", "web-artifact:", "windows-artifact:"))
    assert "tools/build_web.py" in ci
    assert "tools/build_windows.py" in ci


def test_release_workflow_is_tag_bound_and_publishes_checksums() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "tags: [\"v*.*.*\"]" in release
    assert "gh release create" in release
    assert "*.sha256" in release
```

- [ ] **Step 2: Run the tests and confirm missing workflow failures**

Run: `uv run pytest tests/release/test_release_policy.py -q`

Expected: failures identify both missing workflow files.

- [ ] **Step 3: Add source, browser, and Windows CI jobs**

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
  push:
    branches: [main]

jobs:
  source-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with: {enable-cache: true}
      - run: uv sync --all-extras --locked
      - run: uv run pytest -q --cov=windsprig --cov-branch --cov-fail-under=85
      - run: uv run python tools/validate_content.py
      - run: uv run python -c "from pathlib import Path; from tools.verify_release import verify_local_release; raise SystemExit(bool(verify_local_release(Path('.'))))"

  web-artifact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --all-extras --locked
      - run: uv run playwright install --with-deps chromium
      - run: uv run python tools/build_web.py --output dist/web
      - run: uv run pytest tests/e2e/test_web_product.py -q
      - uses: actions/upload-artifact@v4
        with: {name: windsprig-web, path: dist/web, if-no-files-found: error}

  windows-artifact:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --all-extras --locked
      - run: uv run python tools/build_windows.py --output dist/release
      - uses: actions/upload-artifact@v4
        with: {name: windsprig-windows, path: dist/release, if-no-files-found: error}
```

- [ ] **Step 4: Add a tag-bound release workflow**

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ["v*.*.*"]

permissions:
  contents: write

jobs:
  verify-and-release:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --all-extras --locked
      - run: uv run pytest -q --cov=windsprig --cov-branch --cov-fail-under=85
      - run: uv run python tools/build_windows.py --output dist/release
      - run: uv run python tools/build_web.py --output dist/web
      - run: uv run python -c "from pathlib import Path; from tools.release_common import read_build_identity, write_reproducible_zip, sha256_file; i=read_build_identity(Path('.'), 'web'); z=write_reproducible_zip(Path('dist/web'), Path(f'dist/release/Windsprig-{i.version}-web.zip')); z.with_suffix(z.suffix+'.sha256').write_text(f'{sha256_file(z)}  {z.name}\n', encoding='ascii')"
      - shell: pwsh
        run: |
          $version = uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
          $expected = "v$version"
          if ("${{ github.ref_name }}" -ne $expected) { throw "tag/version mismatch" }
      - env:
          GH_TOKEN: ${{ github.token }}
        run: gh release create "${{ github.ref_name }}" dist/release/*.zip dist/release/*.sha256 --verify-tag --generate-notes --title "Windsprig ${{ github.ref_name }}"
```

- [ ] **Step 5: Validate workflow syntax and policy tests**

Run: `uv run pytest tests/release/test_release_policy.py -q`

Expected: all workflow contract tests pass.

Run: `git diff --check`

Expected: exit 0.

- [ ] **Step 6: Commit CI and release automation**

```powershell
git add .github/workflows tests/release/test_release_policy.py
git commit -m "ci: verify and publish Windsprig artifacts"
```

---

### Task 9: Sites launch/press surface brief and hosted build

**Files:**
- Create: `docs/launch/sites-brief.md`
- Create: `.openai/hosting.json`
- Create: `docs/qa/sites-link-check.json`

**Interfaces:**
- Consumes: canonical copy, logo, social card, screenshots, gameplay capture, controls, accessibility/support links, GitHub repository, GitHub release, and canonical Vercel play URL.
- Produces: a published Sites launch/press URL and a checked link manifest consumed by final verification.

- [ ] **Step 1: Write the exact Sites content brief**

```markdown
# Windsprig Sites Launch Brief

## Hero
Eyebrow: PLAY IN YOUR BROWSER · 1–4 LOCAL PLAYERS
Heading: Catch the wind. Carry its echoes.
Body: Restore six storybook sky worlds in a kinetic action-platform adventure about movement, mastery, and the abilities you choose to carry.
Primary CTA: Play Windsprig
Secondary CTA: Download for Windows

## Proof strip
30 hand-crafted stages · 6 multi-phase bosses · 90 hidden Wind Motes · Keyboard and gamepad · English and Korean

## Sections
1. Gameplay: draw, launch, or harmonize captured echoes.
2. Worlds: one card for each named world with its approved screenshot and mechanic.
3. Local co-op: join/leave, device support, and shared-camera explanation.
4. Accessibility: remappable controls, reduced motion, shake, volume, contrast, language.
5. Press kit: logo, social card, six screenshots, one gameplay capture, fact sheet, credits.
6. Support and privacy: local-only saves, requirements, support, privacy, source license.

## Required links
Play -> canonical Vercel production URL
Download -> GitHub v1.0.0 Windows ZIP
Source -> renamed GitHub repository
Support -> repository SUPPORT.md
Privacy -> repository PRIVACY.md
```

- [ ] **Step 2: Add Sites hosting metadata and expected-link record**

```json
{
  "name": "windsprig-launch",
  "title": "Windsprig: Echoes of the Gale",
  "description": "Official launch and press surface for Windsprig.",
  "source": "docs/launch/sites-brief.md"
}
```

```json
{
  "version": "1.0.0",
  "required_labels": ["Play Windsprig", "Download for Windows", "Source", "Support", "Privacy"],
  "required_http_status": 200,
  "broken_links_allowed": 0
}
```

- [ ] **Step 3: Build the launch surface with the Sites building skill**

Use the `sites:sites-building` skill with `docs/launch/sites-brief.md`, `docs/launch/release-copy.md`, the approved original brand assets, six world screenshots, and gameplay capture. The resulting surface must follow the exact section order and link labels above, use the original Windsprig palette/type system, and remain usable at 390 px, 768 px, and 1440 px widths.

Expected: a complete preview whose five required links point to the current Vercel/GitHub/support/privacy targets and whose copy contains no prototype identifier.

- [ ] **Step 4: Publish and verify with the Sites hosting skill**

Use `sites:sites-hosting` immediately after the build. Record the returned production URL in `README.md`, `docs/launch/release-copy.md`, and the final QA checklist. Open the URL in the browser, test all required links, and capture responsive screenshots at 390×844, 768×1024, and 1440×900.

Expected: HTTP 200, zero broken required links, current `1.0.0` metadata, and three readable responsive captures.

- [ ] **Step 5: Commit the launch brief and hosting contract**

```powershell
git add docs/launch/sites-brief.md .openai/hosting.json docs/qa/sites-link-check.json README.md docs/launch/release-copy.md
git commit -m "docs(site): define and link Windsprig launch surface"
```

---

### Task 10: Vercel preview, production deployment, and live verifier

**Files:**
- Extend: `tools/verify_release.py`
- Extend: `tests/release/test_release_policy.py`
- Create: `docs/qa/vercel-production.json`

**Interfaces:**
- Consumes: Vercel project authentication, Task 5 contract, Task 4 browser tests.
- Produces: inspected preview and production deployments plus `verify_live_web(url: str, version: str, sha: str) -> list[str]`.

- [ ] **Step 1: Write a local HTTP-backed test for live verification**

```python
# append to tests/release/test_release_policy.py
def test_live_verifier_reports_version_and_shell_mismatch() -> None:
    import json
    from tools.verify_release import verify_live_web
    def fake_fetch(url: str) -> tuple[int, str]:
        if url.endswith("build-info.json"):
            return 200, json.dumps({"version": "0.9.0", "commit_sha": "x" * 40})
        return 200, "<title>Wrong</title>"
    errors = verify_live_web("https://example.invalid", "1.0.0", "d" * 40, fetcher=fake_fetch)
    assert "production shell title missing" in errors
    assert "production version mismatch" in errors
    assert "production commit mismatch" in errors
```

- [ ] **Step 2: Run the focused test and confirm the missing verifier failure**

Run: `uv run pytest tests/release/test_release_policy.py::test_live_verifier_reports_version_and_shell_mismatch -q`

Expected: import fails because `verify_live_web` is not defined.

- [ ] **Step 3: Implement live endpoint verification**

```python
# append to tools/verify_release.py
from collections.abc import Callable
from urllib.request import urlopen


def fetch_url(url: str) -> tuple[int, str]:
    with urlopen(url, timeout=20) as response:
        return int(response.status), response.read().decode("utf-8")


def verify_live_web(
    url: str,
    version: str,
    sha: str,
    *,
    fetcher: Callable[[str], tuple[int, str]] = fetch_url,
) -> list[str]:
    errors: list[str] = []
    shell_status, shell_text = fetcher(url.rstrip("/") + "/")
    if shell_status != 200:
        errors.append(f"production shell returned {shell_status}")
    if "Windsprig: Echoes of the Gale" not in shell_text:
        errors.append("production shell title missing")
    info_status, info_text = fetcher(url.rstrip("/") + "/build-info.json")
    if info_status != 200:
        return errors + [f"production build info returned {info_status}"]
    info = json.loads(info_text)
    if info.get("version") != version:
        errors.append("production version mismatch")
    if info.get("commit_sha") != sha:
        errors.append("production commit mismatch")
    return errors
```

- [ ] **Step 4: Deploy and inspect an isolated preview using the Vercel deployment skill**

Use `vercel-deploy`/Vercel deployment guidance to link the repository without overwriting unrelated projects. Build locally, run `vercel deploy --prebuilt`, inspect the returned deployment, and run the full browser E2E suite against it.

Expected: preview state `READY`; build SHA matches local HEAD; browser E2E passes; no console/network errors; preview is not promoted if any check fails.

- [ ] **Step 5: Promote the verified build and write production evidence**

Run: `vercel deploy --prebuilt --prod`

Expected: command returns the canonical HTTPS production URL.

Run: `uv run python -c "import os,subprocess; from tools.verify_release import verify_live_web; sha=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(); errors=verify_live_web(os.environ['WINDSPRIG_PRODUCTION_URL'],'1.0.0',sha); print(*errors, sep='\n'); raise SystemExit(bool(errors))"`

Expected: exit 0 with no errors; the verifier reads the exact canonical URL from `WINDSPRIG_PRODUCTION_URL`.

Write `docs/qa/vercel-production.json` with the exact returned URL, deployment ID, version `1.0.0`, full commit SHA, deployment timestamp, and `verification: "passed"`.

- [ ] **Step 6: Commit the verifier and deployment evidence**

```powershell
git add tools/verify_release.py tests/release/test_release_policy.py docs/qa/vercel-production.json README.md docs/launch/release-copy.md
git commit -m "deploy: verify Windsprig production web release"
```

---

### Task 11: Computer and browser camera-ready QA evidence

**Files:**
- Create: `docs/qa/v1.0.0-checklist.md`
- Create: `docs/qa/evidence/README.md`
- Create generated captures under: `docs/qa/evidence/`

**Interfaces:**
- Consumes: current Windows ZIP, canonical Vercel deployment, Sites production surface, full campaign content, supported input devices.
- Produces: a completed requirement-by-requirement checklist with artifact SHA, URLs, device/display matrix, captures, failures, retest evidence, and zero open release blockers.

- [ ] **Step 1: Add the exact checklist before manual testing**

```markdown
# Windsprig v1.0.0 Camera-Ready QA

## Artifact identity
- [ ] Tested commit equals both build manifests and proposed v1.0.0 tag
- [ ] Windows ZIP SHA-256 matches its checksum file
- [ ] Vercel `/build-info.json` matches version and commit
- [ ] Sites launch copy and download links match version 1.0.0

## Windows computer flow
- [ ] Launch from a path containing spaces outside the repository
- [ ] Keyboard-only title -> profile -> stage -> results -> reload
- [ ] Gamepad-only title -> profile -> stage -> results
- [ ] Two-player join, identity, camera, pause, disconnect, reconnect, leave
- [ ] Profile create, delete backup, malformed-save recovery
- [ ] Windowed, fullscreen, 1280×720, 1440×900, 1920×1080
- [ ] Muted and unavailable audio device behavior

## Browser flow
- [ ] Cold and cached startup budgets
- [ ] Keyboard and gamepad title-to-results flows
- [ ] Refresh persistence and clean-profile behavior
- [ ] Focus loss/recovery and audio resume
- [ ] Service-worker update from previous cache
- [ ] No uncaught console error or failed mandatory request

## Complete product
- [ ] 30 distinct stages load and clear
- [ ] Six bosses expose every required phase
- [ ] 90 unique Wind Motes can be collected exactly once
- [ ] Every ability source equips and demonstrates its distinct action
- [ ] English and Korean text fit at every supported resolution
- [ ] Reduced motion, shake, volume, contrast, and control help verified
- [ ] Credits, licenses, privacy, support, and original identity verified

## Evidence index
Each checked row links a screenshot, video, command log, JSON report, or test report captured from the current artifact. A failure stays unchecked until its fix is rebuilt and the same row is retested.
```

- [ ] **Step 2: Use computer control to verify the packaged Windows product**

Extract the exact release ZIP into a temporary directory whose path contains spaces. Use the computer-use skill to perform every Windows checklist flow, including real keyboard and gamepad paths where hardware is available. Capture the title, profile, map, representative stage, boss, pause/settings, results, defeat, credits, and recovery screens at the three required resolutions.

Expected: each row has current-artifact evidence; any discovered defect becomes a code/test task and forces a rebuilt artifact before retest.

- [ ] **Step 3: Use browser control to verify canonical Vercel and Sites URLs**

Use the browser-control skill on a clean browser profile and a warm profile. Verify the browser checklist, inspect console and network state, test all Sites links, and capture the same representative gameplay screens plus 390 px, 768 px, and 1440 px Sites layouts.

Expected: no uncaught console errors, failed mandatory requests, stale versions, broken links, or blank loading states.

- [ ] **Step 4: Run full-catalog automated evidence beside manual QA**

Run: `uv run pytest -q --cov=windsprig --cov-branch --cov-fail-under=85`

Expected: all tests pass and branch coverage is at least 85%.

Run: `uv run python tools/validate_content.py --all --report docs/qa/evidence/content-report.json`

Expected: 6 worlds, 30 stages, 6 bosses, 90 unique motes, 0 duplicate full-layout signatures, 0 validation errors.

Run: `uv run pytest tests/e2e/test_web_product.py -q --junitxml docs/qa/evidence/browser-e2e.xml`

Expected: all browser tests pass.

- [ ] **Step 5: Commit completed QA evidence only when every blocker is closed**

```powershell
git add docs/qa
git commit -m "test: record Windsprig v1 camera-ready evidence"
```

---

### Task 12: GitHub branch, pull request, checks, tag, and immutable release

**Files:**
- Modify only if live URLs changed: `README.md`, `docs/launch/release-copy.md`, `docs/qa/v1.0.0-checklist.md`

**Interfaces:**
- Consumes: clean current branch, all local gates, completed QA, Vercel/Sites production evidence, GitHub authentication.
- Produces: reviewed/green GitHub change set, renamed original-product repository, annotated `v1.0.0` tag, immutable GitHub Release, and verified download links.

- [ ] **Step 1: Run the final local completion audit from a clean worktree**

Run: `git status --short`

Expected: no output.

Run: `uv run pytest -q --cov=windsprig --cov-branch --cov-fail-under=85`

Expected: all tests pass.

Run: `uv run python tools/validate_content.py --all`

Expected: validation summary reports the exact complete-campaign counts and zero errors.

Run: `uv run python tools/build_windows.py --output dist/release`

Expected: packaged smoke, metadata, ZIP, and checksum all pass.

Run: `uv run python tools/build_web.py --output dist/web`

Expected: web build passes and its manifest SHA equals HEAD.

Run: `uv run pytest tests/e2e/test_web_product.py -q`

Expected: browser artifact tests pass.

- [ ] **Step 2: Publish the implementation branch and open the reviewed PR**

Use the GitHub publishing workflow on branch `codex/windsprig-camera-ready`. Push only after confirming commit scope. Open a ready-for-review pull request titled `Release Windsprig: Echoes of the Gale v1.0.0` whose body links the master spec, four plans, Vercel preview, Sites preview, QA checklist, artifact checksums, and known signing status.

Expected: PR exists on the original-product repository and contains no unrelated changes.

- [ ] **Step 3: Verify required GitHub checks and review feedback**

Run: `gh pr checks --watch`

Expected: source-tests, web-artifact, and windows-artifact are green. Address every actionable review comment using the Superpowers review workflow and rerun all affected gates.

- [ ] **Step 4: Merge, rename repository, and update canonical links**

After green checks, merge through the repository's allowed strategy. Use the GitHub connector/CLI to rename the repository from its prototype name to `windsprig`, preserving redirects. Update Vercel, Sites, support, source, and README canonical links, then rerun the live link verifier.

Expected: the new GitHub repository URL returns 200; old URL redirects; all production links point to the new URL.

- [ ] **Step 5: Create and push the annotated release tag**

Run: `git tag -a v1.0.0 -m "Windsprig: Echoes of the Gale v1.0.0"`

Run: `git push origin v1.0.0`

Expected: release workflow starts for the merge commit whose SHA matches production and QA evidence.

- [ ] **Step 6: Verify the GitHub Release and every artifact**

Run: `gh release view v1.0.0 --json url,tagName,isDraft,isPrerelease,assets`

Expected: tag `v1.0.0`, `isDraft=false`, `isPrerelease=false`, and four required assets: Windows ZIP/checksum and web ZIP/checksum.

Download the assets into an empty temporary directory, recompute both SHA-256 hashes, launch the downloaded Windows ZIP through its smoke path, and serve the downloaded web ZIP for the Playwright suite.

Expected: hashes match; both downloaded artifacts pass the same smoke tests as the local artifacts.

- [ ] **Step 7: Run the final live completion audit**

Verify every row of the master spec's requirement-to-evidence matrix against current GitHub, Vercel, Sites, Windows artifact, browser runtime, tests, and QA evidence. Any unknown or indirect result keeps the release incomplete.

Expected: every row has direct current evidence and no release-blocking issue remains.

---

## Plan Self-Review Checklist

- [ ] Every distribution requirement in master-spec sections 4, 7, 8, 9, 10, 11, 13, and 14 maps to a task above.
- [ ] Browser and Windows artifacts construct the same `GameApp` with the same product screen factory and platform-service interfaces.
- [ ] Version, SHA, archive, checksum, URL, and save-location assertions use consistent names across tasks.
- [ ] Vercel is the canonical playable URL; Sites is the launch/press surface; GitHub is source and immutable artifacts.
- [ ] Computer and browser QA use rebuilt current artifacts after every fix.
- [ ] No task treats a passing narrow smoke test as evidence for the full product.
- [ ] Final tag/release occurs only after production and QA manifests match the same commit.
