from __future__ import annotations

from kirby_clone.gameplay.components import CameraFocus, Health, PlayerSlot, Transform


class CameraSystem:
    def update(self, world, dt_ms: int) -> None:
        _ = dt_ms
        weighted_x = 0.0
        weighted_y = 0.0
        total_weight = 0.0

        for _, _, transform, focus, health in world.query(PlayerSlot, Transform, CameraFocus, Health):
            if not focus.enabled or health.dead:
                continue
            weighted_x += transform.x * focus.weight
            weighted_y += transform.y * focus.weight
            total_weight += focus.weight

        if total_weight <= 0:
            return
        world.resources["camera_target"] = (weighted_x / total_weight, weighted_y / total_weight)
