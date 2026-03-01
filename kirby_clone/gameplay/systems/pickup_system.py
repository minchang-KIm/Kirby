from __future__ import annotations

from kirby_clone.gameplay.components import Collectible, Collider, Health, Team, Transform
from kirby_clone.math2d import Rect


class PickupSystem:
    def update(self, world, dt_ms: int) -> None:
        _ = dt_ms
        players = [
            row
            for row in world.query(Team, Transform, Collider, Health)
            if row[1].name == "player" and not row[4].dead
        ]
        to_destroy: set[int] = set()
        for collectible_id, collectible, ctf, ccol in world.query(Collectible, Transform, Collider):
            if collectible.collected:
                continue
            crect = Rect(ctf.x, ctf.y, ccol.width, ccol.height)
            for _, _, ptf, pcol, _ in players:
                prect = Rect(ptf.x, ptf.y, pcol.width, pcol.height)
                if prect.intersects(crect):
                    collectible.collected = True
                    world.resources["run_energy_spheres"] = world.resources.get("run_energy_spheres", 0) + collectible.value
                    world.events.publish("collectible_picked", {"kind": collectible.kind, "value": collectible.value})
                    to_destroy.add(collectible_id)
                    break
        for entity_id in to_destroy:
            world.destroy_entity(entity_id)
