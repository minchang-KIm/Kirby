"""Focused contracts for the opt-in browser feasibility probe."""

from __future__ import annotations

from windsprig.feasibility import FoundationProbe


class MemoryStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.operations: list[tuple[str, str]] = []

    def read_text(self, key: str) -> str | None:
        self.operations.append(("read", key))
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        self.operations.append(("write", key))
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.operations.append(("delete", key))
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(key for key in sorted(self.values) if key.startswith(prefix))


def test_probe_publishes_only_when_enabled() -> None:
    storage = MemoryStorage()
    disabled = FoundationProbe(storage, enabled=False)
    disabled.mark("boot", "ready")
    assert storage.values == {}

    enabled = FoundationProbe(storage, enabled=True)
    enabled.mark("boot", "ready")
    assert storage.values["probe/boot"] == "ready"


def test_probe_session_resets_transient_evidence_but_preserves_completed_stage_identity() -> None:
    storage = MemoryStorage()
    storage.values.update(
        {
            "probe/session": "4",
            "probe/boot": "ready",
            "probe/input": "consumed_once",
            "probe/stage_id": "stage-verdant-1",
        }
    )

    probe = FoundationProbe(storage, enabled=True)
    probe.start_session()

    assert storage.values["probe/session"] == "5"
    assert "probe/boot" not in storage.values
    assert "probe/input" not in storage.values
    assert storage.values["probe/stage_id"] == "stage-verdant-1"
    assert probe.read("stage_id") == "stage-verdant-1"


def test_disabled_probe_session_and_reads_do_not_touch_storage() -> None:
    storage = MemoryStorage()
    storage.values["probe/session"] = "8"

    probe = FoundationProbe(storage, enabled=False)
    probe.start_session()

    assert probe.read("session") is None
    assert storage.values == {"probe/session": "8"}
    assert storage.operations == []


def test_probe_reports_if_a_designated_input_edge_is_consumed_more_than_once() -> None:
    storage = MemoryStorage()
    probe = FoundationProbe(storage, enabled=True)

    probe.consumed_input_edge()
    assert storage.values["probe/input"] == "consumed_once"

    probe.consumed_input_edge()
    assert storage.values["probe/input"] == "consumed_more_than_once"


def test_probe_measures_fps_from_120_rendered_frame_durations_after_boot() -> None:
    storage = MemoryStorage()
    probe = FoundationProbe(storage, enabled=True)

    probe.presented_frame(999.0)
    assert storage.values["probe/boot"] == "ready"
    assert "probe/fps" not in storage.values

    for _ in range(119):
        probe.presented_frame(20.0)
    assert "probe/fps" not in storage.values

    probe.presented_frame(20.0)
    assert float(storage.values["probe/fps"]) == 50.0
