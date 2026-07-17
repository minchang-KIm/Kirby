from __future__ import annotations

from windsprig.core.ecs import World
from windsprig.gameplay.components import CameraFocus, Health, PlayerSlot, Transform
from windsprig.input.roster import ActivePlayer


class CameraSystem:
    """Maintain a deterministic aggregate of eligible active camera targets."""

    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        weighted_x = 0.0
        weighted_y = 0.0
        total_weight = 0.0

        active_players = world.resources.get("active_players", ())
        if isinstance(active_players, tuple):
            active_slots = {
                player.slot
                for player in active_players
                if isinstance(player, ActivePlayer)
            }
        else:
            active_slots = set()

        for _, slot, transform, focus, health in world.query(
            PlayerSlot,
            Transform,
            CameraFocus,
            Health,
        ):
            if (
                slot.slot not in active_slots
                or not focus.enabled
                or focus.weight <= 0
                or health.dead
            ):
                continue
            weighted_x += transform.x * focus.weight
            weighted_y += transform.y * focus.weight
            total_weight += focus.weight

        if total_weight <= 0:
            world.resources["camera_target"] = None
            return
        world.resources["camera_target"] = (weighted_x / total_weight, weighted_y / total_weight)
