"""Deterministic fixed-step budgeting independent of render cadence."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StepBatch:
    """Bounded simulation work plus interpolation and discarded elapsed time."""

    steps: int
    alpha: float
    dropped_ms: float


class FixedStepClock:
    """Accumulate elapsed render time into bounded deterministic step batches."""

    def __init__(self, step_ms: int) -> None:
        if step_ms <= 0:
            raise ValueError("step_ms must be positive")
        self.step_ms = step_ms
        self.accumulator_ms = 0.0

    def push(self, elapsed_ms: float, max_steps: int) -> StepBatch:
        """Budget at most ``max_steps`` and discard only excess whole steps."""
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if not math.isfinite(elapsed_ms):
            raise ValueError("elapsed_ms must be finite")
        total_ms = self.accumulator_ms + max(0.0, elapsed_ms)
        budget_ms = max_steps * self.step_ms
        if total_ms >= budget_ms:
            steps = max_steps
            remainder_ms = math.fmod(total_ms, self.step_ms)
            dropped_ms = max(0.0, total_ms - remainder_ms - budget_ms)
        else:
            steps = int(total_ms // self.step_ms)
            remainder_ms = total_ms - steps * self.step_ms
            dropped_ms = 0.0
        self.accumulator_ms = remainder_ms
        return StepBatch(
            steps=steps,
            alpha=remainder_ms / self.step_ms,
            dropped_ms=dropped_ms,
        )
