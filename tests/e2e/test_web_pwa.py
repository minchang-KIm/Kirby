"""Chromium evidence for install-cache identity and offline navigation."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_offline_query_navigation_falls_back_to_the_cached_root(
    page: Page,
    web_url: str,
) -> None:
    page.goto(f"{web_url}/?install=1", wait_until="domcontentloaded")
    page.evaluate("navigator.serviceWorker.ready.then(() => { window.__WINSPRIG_SW_READY__ = true; })")
    page.wait_for_function("window.__WINSPRIG_SW_READY__ === true", timeout=20_000)

    # A controlled online navigation lets the active worker observe/cache all
    # game requests before the test removes the network.
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=10_000)
    page.context.set_offline(True)
    try:
        page.goto(
            f"{web_url}/?offline-resume=1#canvas",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        expect(page.locator("#canvas")).to_be_attached()
        assert page.title() == "Windsprig: Echoes of the Gale"
    finally:
        page.context.set_offline(False)
