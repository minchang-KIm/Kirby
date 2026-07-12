"""Packaged-browser evidence for the normal Windsprig product flow."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

from playwright.sync_api import ConsoleMessage, Page, expect

from windsprig.meta.save_models import SaveData, save_data_to_json

_ROOT = Path(__file__).resolve().parents[2]
_COLD_BOOT_BUDGET_MS = 12_000
_CACHED_BOOT_BUDGET_MS = 5_000
_COMPRESSED_TRANSFER_LIMIT = 30 * 1024 * 1024
_STATUS_KEYS = ["activePlayers", "clearedStages", "saveStatus", "saveVersion", "state"]


def _wait_for_state(page: Page, state: str, *, timeout: int = _COLD_BOOT_BUDGET_MS) -> dict[str, object]:
    page.wait_for_function(
        "expected => window.__WINSPRIG_TEST__?.state === expected",
        arg=state,
        timeout=timeout,
    )
    return cast(dict[str, object], page.evaluate("() => ({...window.__WINSPRIG_TEST__})"))


def _record_browser_errors(page: Page) -> list[str]:
    errors: list[str] = []

    def record_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(f"console: {message.text}")

    page.on("console", record_console)
    page.on("pageerror", lambda error: errors.append(f"page: {error}"))
    return errors


def _one_clear_save() -> str:
    data = SaveData()
    first = replace(
        data.profiles[0],
        clear_counts={"world_1_stage_1": 1},
        best_times_ms={"world_1_stage_1": 3_200},
    )
    return save_data_to_json(
        replace(data, profiles=(first, data.profiles[1], data.profiles[2])),
        indent=2,
    )


def test_web_boot_input_canvas_and_save_reload(page: Page, web_url: str) -> None:
    errors = _record_browser_errors(page)
    started = time.perf_counter()

    page.goto(f"{web_url}/?e2e=1", wait_until="domcontentloaded")
    status = _wait_for_state(page, "world_map")
    cold_boot_ms = int((time.perf_counter() - started) * 1_000)

    assert cold_boot_ms <= _COLD_BOOT_BUDGET_MS
    assert status == {
        "activePlayers": 0,
        "clearedStages": 0,
        "saveStatus": "ready",
        "saveVersion": 2,
        "state": "world_map",
    }
    bridge_contract = page.evaluate(
        """() => {
            const status = window.__WINSPRIG_TEST__;
            const before = status.state;
            status.state = 'mutated';
            return {
                frozen: Object.isFrozen(status),
                keys: Object.keys(status).sort(),
                primitiveOnly: Object.values(status).every(
                    value => ['string', 'number', 'boolean'].includes(typeof value)
                ),
                rejectedMutation: status.state === before,
            };
        }"""
    )
    assert bridge_contract == {
        "frozen": True,
        "keys": _STATUS_KEYS,
        "primitiveOnly": True,
        "rejectedMutation": True,
    }

    canvas = page.locator("#canvas")
    expect(canvas).to_be_visible()
    screenshot = canvas.screenshot()
    assert screenshot.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(screenshot) > 1_000

    canvas.click(position={"x": 640, "y": 360})
    page.keyboard.press("Enter")
    page.wait_for_function(
        "window.__WINSPRIG_TEST__?.activePlayers === 1",
        timeout=5_000,
    )
    page.keyboard.press("Enter")
    _wait_for_state(page, "playing", timeout=5_000)

    saved = _one_clear_save()
    page.evaluate(
        "raw => localStorage.setItem('windsprig:save_data.json', raw)",
        saved,
    )
    page.reload(wait_until="domcontentloaded")
    restored = _wait_for_state(page, "world_map")

    assert restored == {
        "activePlayers": 0,
        "clearedStages": 1,
        "saveStatus": "ready",
        "saveVersion": 2,
        "state": "world_map",
    }
    assert page.evaluate("localStorage.getItem('windsprig:save_data.json')") == saved
    build_report = json.loads((_ROOT / "artifacts" / "web-build.json").read_text(encoding="utf-8"))
    assert build_report["probe"] is False
    assert build_report["compressed_bytes"] <= _COMPRESSED_TRANSFER_LIMIT
    assert errors == []


def test_cached_boot_meets_five_second_budget(page: Page, web_url: str) -> None:
    errors = _record_browser_errors(page)
    page.goto(f"{web_url}/?e2e=1", wait_until="domcontentloaded")
    _wait_for_state(page, "world_map")

    started = time.perf_counter()
    page.reload(wait_until="domcontentloaded")
    _wait_for_state(page, "world_map", timeout=_CACHED_BOOT_BUDGET_MS)
    cached_boot_ms = int((time.perf_counter() - started) * 1_000)

    assert cached_boot_ms <= _CACHED_BOOT_BUDGET_MS
    assert errors == []
