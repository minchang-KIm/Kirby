from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Camera:
    viewport_width: int
    viewport_height: int
    world_width: int
    world_height: int
    x: float = 0.0
    y: float = 0.0
    smoothing: float = 0.16

    def update(self, target_x: float, target_y: float) -> None:
        desired_x = target_x - self.viewport_width / 2
        desired_y = target_y - self.viewport_height / 2
        desired_x = max(0.0, min(desired_x, max(0.0, self.world_width - self.viewport_width)))
        desired_y = max(0.0, min(desired_y, max(0.0, self.world_height - self.viewport_height)))
        self.x += (desired_x - self.x) * self.smoothing
        self.y += (desired_y - self.y) * self.smoothing

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        return int(round(x - self.x)), int(round(y - self.y))
