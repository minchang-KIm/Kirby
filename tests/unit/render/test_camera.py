"""Bounded camera and reversible logical-display mapping contracts."""

from __future__ import annotations

import math

import pytest

from windsprig.gameplay.snapshot import CameraTargetView
from windsprig.render.camera import CameraController, compute_letterbox


def _target(
    slot: int,
    x: float,
    *,
    y: float = 500.0,
    weight: float = 1.0,
    enabled: bool = True,
) -> CameraTargetView:
    return CameraTargetView(slot, slot, x, y, weight, enabled)


def test_camera_clamps_to_bounds_and_reports_only_distant_coop_slots() -> None:
    camera = CameraController((1280, 720))
    targets = (_target(1, 1800.0), _target(2, 400.0))

    view = camera.update(targets, bounds_px=(0, 0, 2400, 720), dt_ms=16, reduced_motion=False)

    assert view.catch_up_slots == (2,)
    assert 0 <= view.x <= 1120
    assert view.y == 0


def test_camera_uses_only_enabled_positive_weight_targets_in_stable_slot_order() -> None:
    targets = (
        _target(3, 4000.0, weight=0.0),
        _target(2, 900.0, weight=3.0),
        _target(4, 50.0, enabled=False),
        _target(1, 300.0, weight=1.0),
    )
    forward = CameraController((1280, 720)).update(
        targets,
        bounds_px=(0, 0, 4000, 1200),
        dt_ms=140,
        reduced_motion=False,
    )
    reversed_order = CameraController((1280, 720)).update(
        tuple(reversed(targets)),
        bounds_px=(0, 0, 4000, 1200),
        dt_ms=140,
        reduced_motion=False,
    )

    assert forward == reversed_order
    assert forward.catch_up_slots == (2,)
    assert math.isfinite(forward.x) and math.isfinite(forward.y)


def test_camera_empty_target_set_stays_finite_and_clamped_to_offset_bounds() -> None:
    view = CameraController((1280, 720)).update(
        (),
        bounds_px=(120, 80, 2000, 1000),
        dt_ms=10_000,
        reduced_motion=False,
    )

    assert (view.x, view.y, view.look_ahead_x, view.catch_up_slots) == (120.0, 80.0, 0.0, ())


def test_reduced_motion_disables_directional_lookahead_without_changing_target_bounds() -> None:
    normal = CameraController((1280, 720))
    reduced = CameraController((1280, 720))
    initial = (_target(1, 400.0),)
    moved = (_target(1, 900.0),)
    for controller in (normal, reduced):
        controller.update(initial, (0, 0, 2400, 900), 16, False)

    normal_view = normal.update(moved, (0, 0, 2400, 900), 16, False)
    reduced_view = reduced.update(moved, (0, 0, 2400, 900), 16, True)

    assert normal_view.look_ahead_x == CameraController.LOOK_AHEAD
    assert reduced_view.look_ahead_x == 0.0
    assert 0 <= normal_view.x <= 1120
    assert 0 <= reduced_view.x <= 1120


def test_letterbox_is_centered_above_and_below_logical_resolution() -> None:
    assert compute_letterbox((1920, 1080)).destination == (0, 0, 1920, 1080)
    assert compute_letterbox((1440, 900)).destination == (0, 45, 1440, 810)
    assert compute_letterbox((1024, 576), integer_scaling=True).destination == (0, 0, 1024, 576)
    assert compute_letterbox((1600, 1000), integer_scaling=True).destination == (160, 140, 1280, 720)


def test_letterbox_coordinate_mapping_is_reversible_without_rounding_traps() -> None:
    letterbox = compute_letterbox((853, 500))
    logical_point = (123.25, 456.75)

    window_point = letterbox.logical_to_window(logical_point)
    restored = letterbox.window_to_logical(window_point)

    assert restored == pytest.approx(logical_point)
    x, y, width, height = letterbox.destination
    assert letterbox.window_to_logical((x - 0.01, y)) is None
    assert letterbox.window_to_logical((x + width + 0.01, y + height / 2)) is None


@pytest.mark.parametrize(
    ("window_size", "logical_size", "integer_scaling", "exception"),
    [
        ((0, 720), (1280, 720), False, ValueError),
        ((True, 720), (1280, 720), False, TypeError),
        ((1280,), (1280, 720), False, ValueError),
        ((1280, 720), (1280, -1), False, ValueError),
        ((1280, 720), (1280, 720), 1, TypeError),
    ],
)
def test_letterbox_rejects_invalid_public_sizes(
    window_size: object,
    logical_size: object,
    integer_scaling: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        compute_letterbox(  # type: ignore[arg-type]
            window_size,
            logical_size,
            integer_scaling,
        )


@pytest.mark.parametrize(
    ("targets", "bounds", "dt_ms", "reduced_motion", "exception"),
    [
        ((_target(1, math.inf),), (0, 0, 2000, 900), 16, False, ValueError),
        ((_target(1, 10.0, weight=-1.0),), (0, 0, 2000, 900), 16, False, ValueError),
        ((_target(1, 10.0), _target(1, 20.0)), (0, 0, 2000, 900), 16, False, ValueError),
        ((_target(1, 10.0),), (0, 0, 0, 900), 16, False, ValueError),
        ((_target(1, 10.0),), (0, 0, 2000, 900), True, False, TypeError),
        ((_target(1, 10.0),), (0, 0, 2000, 900), -1, False, ValueError),
        ((_target(1, 10.0),), (0, 0, 2000, 900), 16, 1, TypeError),
    ],
)
def test_camera_rejects_nonfinite_duplicate_and_malformed_update_inputs(
    targets: object,
    bounds: object,
    dt_ms: object,
    reduced_motion: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        CameraController((1280, 720)).update(  # type: ignore[arg-type]
            targets,
            bounds,
            dt_ms,
            reduced_motion,
        )
