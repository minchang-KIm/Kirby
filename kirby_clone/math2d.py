from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def to_int(self) -> tuple[int, int]:
        return int(self.x), int(self.y)

    def length(self) -> float:
        return math.hypot(self.x, self.y)


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def center_x(self) -> float:
        return self.x + self.w / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2.0

    def moved(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def intersects(self, other: "Rect") -> bool:
        return (
            self.left < other.right
            and self.right > other.left
            and self.top < other.bottom
            and self.bottom > other.top
        )

    def inflate(self, amount_x: float, amount_y: float) -> "Rect":
        return Rect(
            self.x - amount_x / 2.0,
            self.y - amount_y / 2.0,
            self.w + amount_x,
            self.h + amount_y,
        )

    def to_int_tuple(self, offset_x: float = 0.0, offset_y: float = 0.0) -> tuple[int, int, int, int]:
        return (
            int(round(self.x + offset_x)),
            int(round(self.y + offset_y)),
            int(round(self.w)),
            int(round(self.h)),
        )


def move_towards(value: float, target: float, max_delta: float) -> float:
    if value < target:
        return min(target, value + max_delta)
    return max(target, value - max_delta)
