"""Fresh Chromium and reliably cleaned static-server fixtures for web probes."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, sync_playwright

_HOST = "127.0.0.1"
_PORT = 8765
_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def web_server() -> Iterator[str]:
    """Serve only the built web artifact and always reap its child process."""
    web_root = _ROOT / "dist" / "web"
    if not (web_root / "index.html").is_file():
        pytest.fail("dist/web/index.html is missing; run tools/build_web.py --probe first")

    command = [
        sys.executable,
        "-m",
        "http.server",
        str(_PORT),
        "--bind",
        _HOST,
        "--directory",
        str(web_root),
    ]
    process = subprocess.Popen(
        command,
        cwd=_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://{_HOST}:{_PORT}"
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"web server exited during startup with code {process.returncode}")
            try:
                with urlopen(url, timeout=0.25) as response:  # noqa: S310 - loopback test server
                    if response.status == 200:
                        break
            except (OSError, URLError):
                time.sleep(0.05)
        else:
            pytest.fail("web server did not become ready within 10 seconds")
        yield url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture
def page() -> Iterator[Page]:
    """Launch one empty browser profile and close every owned resource on failure."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()
