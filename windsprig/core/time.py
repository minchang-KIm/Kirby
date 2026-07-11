"""Deterministic fixed-step budgeting independent of render cadence."""

from __future__ import annotations

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
        self.accumulator_ms += max(0.0, elapsed_ms)
        available_steps = int(self.accumulator_ms // self.step_ms)
        steps = min(available_steps, max_steps)
        dropped_steps = max(0, available_steps - max_steps)
        dropped_ms = float(dropped_steps * self.step_ms)
        self.accumulator_ms -= dropped_ms + steps * self.step_ms
        return StepBatch(
            steps=steps,
            alpha=self.accumulator_ms / self.step_ms,
            dropped_ms=dropped_ms,
        )
