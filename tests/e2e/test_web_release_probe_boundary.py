"""Permanent packaged-browser regression for the release artifact's inert probe path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import ConsoleMessage, Page, expect

_ROOT = Path(__file__).resolve().parents[2]


def test_release_artifact_ignores_probe_query_and_f9(page: Page, web_server: str) -> None:
    report = json.loads((_ROOT / "artifacts" / "web-build.json").read_text(encoding="utf-8"))
    if report["probe"] is not False:
        pytest.skip("requires a normal build from tools/build_web.py without --probe")

    errors: list[str] = []

    def record_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", record_console)
    page.goto(f"{web_server}/?foundation_probe=1", wait_until="domcontentloaded")
    canvas = page.locator("#canvas")
    expect(canvas).to_be_visible(timeout=12_000)
    page.wait_for_timeout(6_000)
    canvas.click(position={"x": 640, "y": 360})
    page.wait_for_function(
        "['Audio: ready', 'Audio: muted'].includes(document.querySelector('#audio-status').textContent)",
        timeout=5_000,
    )

    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    page.keyboard.press("KeyW")
    page.wait_for_timeout(1_000)
    page.keyboard.press("F9")
    page.wait_for_timeout(750)

    probe_keys = page.evaluate(
        "Object.keys(localStorage).filter(key => key.startsWith('windsprig:probe/'))"
    )
    assert probe_keys == []
    assert page.evaluate("localStorage.getItem('windsprig:save_data.json')") is None
    assert page.locator("#audio-status").text_content() in {"Audio: ready", "Audio: muted"}
    assert errors == []
