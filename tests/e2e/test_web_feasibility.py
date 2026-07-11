"""Release-critical browser evidence from the packaged Pygbag artifact."""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Page, expect

_ROOT = Path(__file__).resolve().parents[2]


def signal(page: Page, name: str) -> str | None:
    """Read one namespaced diagnostic written by the production storage adapter."""
    return page.evaluate("name => localStorage.getItem('windsprig:probe/' + name)", name)


def test_pygbag_boot_input_audio_stage_and_save(page: Page, web_server: str) -> None:
    errors: list[str] = []

    def record_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", record_console)

    started = time.perf_counter()
    page.goto(f"{web_server}/?foundation_probe=1", wait_until="domcontentloaded")
    page.wait_for_function(
        "localStorage.getItem('windsprig:probe/boot') === 'ready'",
        timeout=12_000,
    )
    cold_ms = int((time.perf_counter() - started) * 1000)
    canvas = page.locator("#canvas")
    expect(canvas).to_be_visible()

    canvas.click(position={"x": 640, "y": 360})
    page.wait_for_function(
        "['ready', 'muted'].includes(localStorage.getItem('windsprig:probe/audio'))",
        timeout=5_000,
    )
    audio_status = signal(page, "audio")
    audio_indicator = page.locator("#audio-status")
    expect(audio_indicator).to_be_visible()
    expect(audio_indicator).to_have_text(
        "Audio: muted" if audio_status == "muted" else "Audio: ready"
    )

    page.keyboard.press("Enter")
    # Joining suppresses that device's same-frame commands by ownership contract.
    page.wait_for_timeout(100)
    page.keyboard.press("KeyW")
    page.wait_for_function(
        "localStorage.getItem('windsprig:probe/input') === 'consumed_once'",
        timeout=5_000,
    )
    page.keyboard.press("KeyD")
    page.keyboard.press("F9")
    page.wait_for_function(
        "localStorage.getItem('windsprig:probe/stage') === 'completed'",
        timeout=5_000,
    )
    page.wait_for_function(
        "localStorage.getItem('windsprig:probe/save') === 'written'",
        timeout=5_000,
    )
    first_session = signal(page, "session")
    stage_status = signal(page, "stage")
    input_status = signal(page, "input")
    written_status = signal(page, "save")

    reload_started = time.perf_counter()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(
        """previous => {
            const prefix = 'windsprig:probe/';
            return localStorage.getItem(prefix + 'session') !== previous
                && localStorage.getItem(prefix + 'boot') === 'ready'
                && localStorage.getItem(prefix + 'save') === 'restored';
        }""",
        arg=first_session,
        timeout=5_000,
    )
    cached_ms = int((time.perf_counter() - reload_started) * 1000)
    canvas = page.locator("#canvas")
    canvas.click(position={"x": 640, "y": 360})
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    page.keyboard.press("KeyW")
    page.wait_for_function(
        "localStorage.getItem('windsprig:probe/gameplay') === 'active'",
        timeout=5_000,
    )
    page.wait_for_function(
        "Number(localStorage.getItem('windsprig:probe/fps')) >= 30",
        timeout=10_000,
    )
    fps = float(signal(page, "fps") or "0")

    report = {
        "audio": audio_status in {"ready", "muted"},
        "audio_status": audio_status,
        "boot": signal(page, "boot") == "ready",
        "cached_ms": cached_ms,
        "cold_ms": cold_ms,
        "console_errors": errors,
        "fps": fps,
        "gameplay_active": signal(page, "gameplay") == "active",
        "input": input_status == "consumed_once",
        "save_restored": signal(page, "save") == "restored",
        "save_written": written_status == "written",
        "stage_complete": stage_status == "completed",
    }
    artifacts = _ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "browser-probe.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert report["boot"] is True
    assert report["input"] is True
    assert report["gameplay_active"] is True
    assert report["audio"] is True
    assert report["stage_complete"] is True
    assert report["save_written"] is True
    assert report["save_restored"] is True
    assert cold_ms <= 12_000
    assert cached_ms <= 5_000
    assert fps >= 30.0
    assert errors == []
