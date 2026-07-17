"""Opt-in storage evidence for the real browser runtime feasibility gate."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar

from windsprig.platform.services import StorageService


@dataclass(slots=True)
class FoundationProbe:
    """Publish namespaced evidence only when the browser query explicitly enables it."""

    storage: StorageService
    enabled: bool
    input_edge_count: int = 0
    _boot_presented: bool = False
    _gameplay_active: bool = False
    _frame_durations_ms: list[float] = field(default_factory=list, repr=False)

    _FPS_FRAME_COUNT: ClassVar[int] = 120
    _TRANSIENT_SIGNALS: ClassVar[tuple[str, ...]] = (
        "audio",
        "boot",
        "fps",
        "gameplay",
        "input",
        "save",
        "stage",
    )

    def start_session(self) -> None:
        """Start fresh evidence while retaining the completed stage ID needed after reload."""
        if not self.enabled:
            return
        previous = self.storage.read_text("probe/session")
        try:
            session = int(previous) + 1 if previous is not None else 1
        except ValueError:
            session = 1
        for name in self._TRANSIENT_SIGNALS:
            self.storage.delete(f"probe/{name}")
        self.storage.write_text("probe/session", str(session))
        self.input_edge_count = 0
        self._boot_presented = False
        self._gameplay_active = False
        self._frame_durations_ms.clear()

    def read(self, name: str) -> str | None:
        """Read retained probe evidence without storage access when diagnostics are disabled."""
        if not self.enabled:
            return None
        return self.storage.read_text(f"probe/{name}")

    def mark(self, name: str, value: str) -> None:
        """Persist one probe signal without touching storage when diagnostics are disabled."""
        if self.enabled:
            self.storage.write_text(f"probe/{name}", value)

    def consumed_input_edge(self) -> None:
        """Record whether the designated fixed-step edge was drained exactly once."""
        if not self.enabled:
            return
        self.input_edge_count += 1
        value = "consumed_once" if self.input_edge_count == 1 else "consumed_more_than_once"
        self.mark("input", value)

    def presented_frame(self, elapsed_ms: float, *, gameplay_active: bool) -> None:
        """Mark boot, then measure only 120 consecutive real-gameplay presentations."""
        if not self.enabled:
            return
        if not self._boot_presented:
            self._boot_presented = True
            self.mark("boot", "ready")
            return
        if gameplay_active != self._gameplay_active:
            self._gameplay_active = gameplay_active
            self._frame_durations_ms.clear()
            self.storage.delete("probe/fps")
            self.mark("gameplay", "active" if gameplay_active else "inactive")
        if not gameplay_active:
            return
        if len(self._frame_durations_ms) >= self._FPS_FRAME_COUNT:
            return
        if not math.isfinite(elapsed_ms) or elapsed_ms <= 0:
            # The evidence window must contain consecutive real rendered-frame durations.
            self._frame_durations_ms.clear()
            return
        self._frame_durations_ms.append(elapsed_ms)
        if len(self._frame_durations_ms) == self._FPS_FRAME_COUNT:
            total_ms = sum(self._frame_durations_ms)
            fps = self._FPS_FRAME_COUNT * 1000.0 / total_ms
            self.mark("fps", f"{fps:.3f}")
