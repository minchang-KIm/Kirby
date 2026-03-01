from __future__ import annotations


class FixedStepClock:
    def __init__(self, step_ms: int) -> None:
        self.step_ms = step_ms
        self.accumulator_ms = 0.0

    def push(self, elapsed_ms: float) -> int:
        self.accumulator_ms += elapsed_ms
        steps = 0
        while self.accumulator_ms >= self.step_ms:
            self.accumulator_ms -= self.step_ms
            steps += 1
        return steps
