"""Fresh Chromium and reliably cleaned static-server fixtures for web probes."""

from __future__ import annotations

import time
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, sync_playwright

_HOST = "127.0.0.1"
_ROOT = Path(__file__).resolve().parents[2]


class _ArtifactHandler(SimpleHTTPRequestHandler):
    """Serve the staged artifact with the canonical revalidation policy."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        super().end_headers()

    def log_message(self, _format: str, *args: object) -> None:
        _ = args


class _ArtifactServer(ThreadingHTTPServer):
    daemon_threads = True


@pytest.fixture(scope="session")
def web_server() -> Iterator[str]:
    """Serve only the built web artifact on an owned ephemeral loopback port."""
    web_root = _ROOT / "dist" / "web"
    if not (web_root / "index.html").is_file():
        pytest.fail("dist/web/index.html is missing; run tools/build_web.py first")

    handler = partial(_ArtifactHandler, directory=str(web_root))
    server = _ArtifactServer((_HOST, 0), handler)
    port = int(server.server_address[1])
    thread = Thread(
        target=server.serve_forever,
        name=f"windsprig-artifact-server-{port}",
        daemon=True,
    )
    thread.start()
    url = f"http://{_HOST}:{port}"
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not thread.is_alive():
                pytest.fail("artifact server exited during startup")
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
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            pytest.fail("artifact server did not stop within 5 seconds")


@pytest.fixture(scope="session")
def web_url(web_server: str) -> str:
    """Expose the product-test name without breaking existing probe tests."""
    return web_server


@pytest.fixture
def page() -> Iterator[Page]:
    """Launch one empty browser profile and close every owned resource on failure."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        try:
            yield context.new_page()
        finally:
            try:
                context.close()
            finally:
                browser.close()
