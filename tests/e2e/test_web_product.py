"""Packaged-browser evidence for the normal Windsprig product flow."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from playwright.sync_api import ConsoleMessage, Page, Request, Response, expect

_ROOT = Path(__file__).resolve().parents[2]
_COLD_BOOT_BUDGET_MS = 12_000
_CACHED_BOOT_BUDGET_MS = 5_000
_STAGE_CLEAR_BUDGET_MS = 30_000
_FIRST_GAP_APPROACH_MS = 3_440
_HOVER_CROSSING_MS = 720
_BETWEEN_GAPS_MS = 3_680
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
            errors.append(f"browser_console_error: {message.text}")

    def record_request_failed(request: Request) -> None:
        failure = request.failure or "unknown failure"
        errors.append(f"browser_request_failed: {request.method} {request.url}: {failure}")

    def record_http_error(response: Response) -> None:
        if response.status >= 400:
            errors.append(f"browser_http_error: {response.status} {response.url}")

    page.on("console", record_console)
    page.on("pageerror", lambda error: errors.append(f"browser_page_error: {error}"))
    page.on("requestfailed", record_request_failed)
    page.on("response", record_http_error)
    return errors


class _FakeBrowserEvents:
    def __init__(self) -> None:
        self.handlers: dict[str, list[Callable[[object], None]]] = {}

    def on(self, name: str, handler: Callable[[object], None]) -> None:
        self.handlers.setdefault(name, []).append(handler)

    def emit(self, name: str, value: object) -> None:
        for handler in self.handlers.get(name, []):
            handler(value)


def test_browser_error_recorder_captures_console_page_request_and_http_failures() -> None:
    page = _FakeBrowserEvents()
    errors = _record_browser_errors(cast(Page, page))

    page.emit("console", SimpleNamespace(type="error", text="console boom"))
    page.emit("pageerror", RuntimeError("page boom"))
    page.emit(
        "requestfailed",
        SimpleNamespace(
            method="GET",
            url="https://example.invalid/runtime.wasm",
            failure="net::ERR_FAILED",
        ),
    )
    page.emit(
        "response",
        SimpleNamespace(status=503, url="https://example.invalid/runtime.data"),
    )

    assert errors == [
        "browser_console_error: console boom",
        "browser_page_error: page boom",
        "browser_request_failed: GET https://example.invalid/runtime.wasm: net::ERR_FAILED",
        "browser_http_error: 503 https://example.invalid/runtime.data",
    ]


def _drive_first_stage_to_clear(page: Page) -> dict[str, object]:
    """Reach the first goal through bounded visible keyboard input only."""
    deadline = time.perf_counter() + _STAGE_CLEAR_BUDGET_MS / 1_000
    last_status: dict[str, object] = {}

    def observe_clear() -> dict[str, object] | None:
        nonlocal last_status
        last_status = cast(
            dict[str, object],
            page.evaluate("() => ({...window.__WINSPRIG_TEST__})"),
        )
        if (
            last_status.get("state") == "world_map"
            and last_status.get("clearedStages") == 1
            and last_status.get("saveStatus") == "saved"
        ):
            return last_status
        return None

    try:
        page.keyboard.down("KeyD")
        # WHY: these wall-clock windows exercise the two authored four-tile gaps
        # through public move/jump/hover input. They do not inspect or mutate the
        # simulation and retain more than 200 ms of deterministic timing margin.
        page.wait_for_timeout(_FIRST_GAP_APPROACH_MS)
        page.keyboard.down("KeyW")
        page.wait_for_timeout(_HOVER_CROSSING_MS)
        page.keyboard.up("KeyW")
        page.wait_for_timeout(_BETWEEN_GAPS_MS)
        page.keyboard.down("KeyW")
        page.wait_for_timeout(_HOVER_CROSSING_MS)
        page.keyboard.up("KeyW")

        while time.perf_counter() < deadline:
            if completed := observe_clear():
                return completed
            page.wait_for_timeout(100)
    finally:
        page.keyboard.up("KeyW")
        page.keyboard.up("KeyD")
    raise AssertionError(
        f"first stage did not produce a saved clear within {_STAGE_CLEAR_BUDGET_MS} ms; last status={last_status!r}"
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
    # Enter joins the WASD device; its owned jump key is the product confirm action.
    page.keyboard.press("KeyW")
    _wait_for_state(page, "playing", timeout=5_000)

    completed = _drive_first_stage_to_clear(page)
    assert completed == {
        "activePlayers": 1,
        "clearedStages": 1,
        "saveStatus": "saved",
        "saveVersion": 2,
        "state": "world_map",
    }
    product_written_save = page.evaluate("() => localStorage.getItem('windsprig:save_data.json')")
    assert isinstance(product_written_save, str)
    assert product_written_save

    page.reload(wait_until="domcontentloaded")
    restored = _wait_for_state(page, "world_map")

    assert restored == {
        "activePlayers": 0,
        "clearedStages": 1,
        "saveStatus": "ready",
        "saveVersion": 2,
        "state": "world_map",
    }
    assert page.evaluate("localStorage.getItem('windsprig:save_data.json')") == product_written_save
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
