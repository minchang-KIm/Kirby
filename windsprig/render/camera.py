"""Bounded presentation camera and reversible logical-canvas letterboxing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast

from windsprig.gameplay.snapshot import CameraTargetView

type Number = int | float
type Point = tuple[float, float]


def _size(name: str, value: object) -> tuple[int, int]:
    if type(value) is not tuple or len(value) != 2:
        raise ValueError(f"{name} must be a two-item tuple")
    width, height = value
    if type(width) is not int or type(height) is not int:
        raise TypeError(f"{name} values must be integers")
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} values must be positive")
    return width, height


def _finite(name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise TypeError(f"{name} must be a number")
    result = float(cast(Number, value))
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _point(name: str, value: object) -> Point:
    if type(value) is not tuple or len(value) != 2:
        raise ValueError(f"{name} must be a two-item tuple")
    return _finite(f"{name} x", value[0]), _finite(f"{name} y", value[1])


def _bounds(value: object) -> tuple[float, float, float, float]:
    if type(value) is not tuple or len(value) != 4:
        raise ValueError("camera bounds must be a four-item tuple")
    x, y, width, height = (_finite("camera bound", item) for item in value)
    if width <= 0 or height <= 0:
        raise ValueError("camera bound dimensions must be positive")
    return x, y, width, height


@dataclass(frozen=True, slots=True)
class Letterbox:
    """Exact destination rectangle plus reversible logical coordinate mapping."""

    destination: tuple[int, int, int, int]
    scale: float
    logical_size: tuple[int, int] = (1280, 720)

    def __post_init__(self) -> None:
        if type(self.destination) is not tuple or len(self.destination) != 4:
            raise ValueError("letterbox destination must be a four-item tuple")
        if any(type(value) is not int for value in self.destination):
            raise TypeError("letterbox destination values must be integers")
        _, _, width, height = self.destination
        if width <= 0 or height <= 0:
            raise ValueError("letterbox destination dimensions must be positive")
        object.__setattr__(self, "scale", _finite("letterbox scale", self.scale))
        if self.scale <= 0:
            raise ValueError("letterbox scale must be positive")
        object.__setattr__(self, "logical_size", _size("logical size", self.logical_size))

    def logical_to_window(self, point: tuple[Number, Number]) -> Point:
        """Map an in-canvas logical point without integer rounding."""

        logical_x, logical_y = _point("logical point", point)
        logical_width, logical_height = self.logical_size
        if not 0.0 <= logical_x <= logical_width or not 0.0 <= logical_y <= logical_height:
            raise ValueError("logical point lies outside the logical canvas")
        x, y, width, height = self.destination
        return (
            x + logical_x * width / logical_width,
            y + logical_y * height / logical_height,
        )

    def window_to_logical(self, point: tuple[Number, Number]) -> Point | None:
        """Map a window point or return ``None`` when it lies in a letterbox bar."""

        window_x, window_y = _point("window point", point)
        x, y, width, height = self.destination
        if not x <= window_x <= x + width or not y <= window_y <= y + height:
            return None
        logical_width, logical_height = self.logical_size
        return (
            (window_x - x) * logical_width / width,
            (window_y - y) * logical_height / height,
        )


@dataclass(frozen=True, slots=True)
class CameraView:
    """Finite bounded camera state consumed only by presentation code."""

    x: float
    y: float
    look_ahead_x: float
    shake_x: float
    shake_y: float
    catch_up_slots: tuple[int, ...]

    def __post_init__(self) -> None:
        for name in ("x", "y", "look_ahead_x", "shake_x", "shake_y"):
            object.__setattr__(self, name, _finite(f"camera {name}", getattr(self, name)))
        if type(self.catch_up_slots) is not tuple:
            raise TypeError("camera catch-up slots must be a tuple")
        if any(type(slot) is not int or not 1 <= slot <= 4 for slot in self.catch_up_slots):
            raise ValueError("camera catch-up slots must contain player slots 1 through 4")
        if tuple(sorted(set(self.catch_up_slots))) != self.catch_up_slots:
            raise ValueError("camera catch-up slots must be unique canonical slot order")


def compute_letterbox(
    window_size: tuple[int, int],
    logical_size: tuple[int, int] = (1280, 720),
    integer_scaling: bool = False,
) -> Letterbox:
    """Center a positive logical canvas for both upscaling and downscaling."""

    window_width, window_height = _size("window size", window_size)
    logical_width, logical_height = _size("logical size", logical_size)
    if type(integer_scaling) is not bool:
        raise TypeError("integer scaling must be a boolean")
    scale = min(window_width / logical_width, window_height / logical_height)
    if integer_scaling and scale >= 1.0:
        scale = float(max(1, math.floor(scale)))
    width = max(1, round(logical_width * scale))
    height = max(1, round(logical_height * scale))
    destination = (
        (window_width - width) // 2,
        (window_height - height) // 2,
        width,
        height,
    )
    return Letterbox(destination, scale, (logical_width, logical_height))


class CameraController:
    """Track immutable targets with bounded exponential damping and slot-stable co-op cues."""

    SAFE_WIDTH: Final = 760.0
    LOOK_AHEAD: Final = 128.0
    DAMP_MS: Final = 140.0

    def __init__(self, logical_size: tuple[int, int]) -> None:
        self.width, self.height = _size("logical size", logical_size)
        self.x = 0.0
        self.y = 0.0
        self._previous_center_x: float | None = None

    def _validated_targets(self, targets: Sequence[CameraTargetView]) -> tuple[CameraTargetView, ...]:
        if isinstance(targets, (str, bytes, bytearray)) or not isinstance(targets, Sequence):
            raise TypeError("camera targets must be a sequence")
        validated: list[CameraTargetView] = []
        slots: set[int] = set()
        entity_ids: set[int] = set()
        for target in targets:
            if not isinstance(target, CameraTargetView):
                raise TypeError("camera targets must contain CameraTargetView values")
            if type(target.entity_id) is not int or target.entity_id <= 0:
                raise ValueError("camera target entity IDs must be positive integers")
            if type(target.slot) is not int or not 1 <= target.slot <= 4:
                raise ValueError("camera target slots must be integers in [1, 4]")
            if target.slot in slots or target.entity_id in entity_ids:
                raise ValueError("camera target slots and entity IDs must be unique")
            _finite("camera target x", target.x)
            _finite("camera target y", target.y)
            weight = _finite("camera target weight", target.weight)
            if weight < 0:
                raise ValueError("camera target weight must be non-negative")
            if type(target.enabled) is not bool:
                raise TypeError("camera target enabled must be a boolean")
            slots.add(target.slot)
            entity_ids.add(target.entity_id)
            validated.append(target)
        return tuple(sorted(validated, key=lambda item: (item.slot, item.entity_id)))

    def update(
        self,
        targets: Sequence[CameraTargetView],
        bounds_px: tuple[Number, Number, Number, Number],
        dt_ms: int,
        reduced_motion: bool,
    ) -> CameraView:
        """Advance one finite camera update without changing gameplay-owned targets."""

        ordered = self._validated_targets(targets)
        bound_x, bound_y, bound_width, bound_height = _bounds(bounds_px)
        if type(dt_ms) is not int:
            raise TypeError("camera delta must be an integer")
        if dt_ms < 0:
            raise ValueError("camera delta must be non-negative")
        if type(reduced_motion) is not bool:
            raise TypeError("reduced motion must be a boolean")

        maximum_x = bound_x + max(0.0, bound_width - self.width)
        maximum_y = bound_y + max(0.0, bound_height - self.height)
        self.x = min(maximum_x, max(bound_x, self.x))
        self.y = min(maximum_y, max(bound_y, self.y))
        active = tuple(target for target in ordered if target.enabled and target.weight > 0.0)
        if not active:
            return CameraView(self.x, self.y, 0.0, 0.0, 0.0, ())

        total_weight = sum(target.weight for target in active)
        center_x = sum(target.x * target.weight for target in active) / total_weight
        center_y = sum(target.y * target.weight for target in active) / total_weight
        velocity_x = 0.0 if self._previous_center_x is None else (center_x - self._previous_center_x) / max(1, dt_ms)
        self._previous_center_x = center_x
        look_ahead = 0.0 if reduced_motion else max(-self.LOOK_AHEAD, min(self.LOOK_AHEAD, velocity_x * 90.0))

        safe_half_width = self.SAFE_WIDTH / 2.0
        # Every participant is classified against the same weighted group frame;
        # slot order is identity stability, not implicit camera leadership.
        catch_up_slots = tuple(target.slot for target in active if abs(target.x - center_x) > safe_half_width)
        desired_x = min(maximum_x, max(bound_x, center_x + look_ahead - self.width / 2.0))
        desired_y = min(maximum_y, max(bound_y, center_y - self.height / 2.0))
        damping = 1.0 - math.exp(-dt_ms / self.DAMP_MS)
        self.x += (desired_x - self.x) * damping
        self.y += (desired_y - self.y) * damping
        self.x = min(maximum_x, max(bound_x, self.x))
        self.y = min(maximum_y, max(bound_y, self.y))
        return CameraView(self.x, self.y, look_ahead, 0.0, 0.0, catch_up_slots)


__all__ = ["CameraController", "CameraView", "Letterbox", "compute_letterbox"]
