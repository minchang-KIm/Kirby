from __future__ import annotations

import pytest

from windsprig.core.time import FixedStepClock


def test_clock_reports_zero_step_and_interpolation() -> None:
    clock = FixedStepClock(step_ms=16)

    batch = clock.push(8, max_steps=5)

    assert batch.steps == 0
    assert batch.alpha == 0.5
    assert batch.dropped_ms == 0


def test_clock_drops_only_whole_excess_steps_and_keeps_fractional_time() -> None:
    clock = FixedStepClock(step_ms=16)

    batch = clock.push(200, max_steps=5)

    assert batch.steps == 5
    assert batch.dropped_ms == 112
    assert batch.alpha == 0.5


def test_clock_treats_negative_elapsed_time_as_no_progress() -> None:
    clock = FixedStepClock(step_ms=16)

    assert clock.push(-8, max_steps=5).steps == 0
    assert clock.push(16, max_steps=5).steps == 1


@pytest.mark.parametrize("step_ms", [0, -1])
def test_clock_rejects_non_positive_step(step_ms: int) -> None:
    with pytest.raises(ValueError, match="step_ms must be positive"):
        FixedStepClock(step_ms=step_ms)


def test_clock_rejects_non_positive_catch_up_budget() -> None:
    clock = FixedStepClock(step_ms=16)

    with pytest.raises(ValueError, match="max_steps must be positive"):
        clock.push(16, max_steps=0)
