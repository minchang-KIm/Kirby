from __future__ import annotations

import math

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


def test_huge_finite_elapsed_keeps_interpolation_within_one_step() -> None:
    clock = FixedStepClock(step_ms=16)
    elapsed_ms = float.fromhex("0x1.f06f6fe38784bp+57")

    batch = clock.push(elapsed_ms, max_steps=5)

    assert batch.steps == 5
    assert batch.alpha == 0.0
    assert 0.0 <= batch.alpha < 1.0
    assert math.isfinite(batch.dropped_ms)


@pytest.mark.parametrize("elapsed_ms", [math.inf, -math.inf, math.nan])
def test_non_finite_elapsed_is_rejected_without_poisoning_accumulator(elapsed_ms: float) -> None:
    clock = FixedStepClock(step_ms=16)
    assert clock.push(8, max_steps=5).alpha == 0.5

    with pytest.raises(ValueError, match="elapsed_ms must be finite"):
        clock.push(elapsed_ms, max_steps=5)

    recovered = clock.push(8, max_steps=5)
    assert recovered.steps == 1
    assert recovered.alpha == 0.0
