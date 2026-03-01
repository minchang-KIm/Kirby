from __future__ import annotations

from kirby_clone.gameplay.components import AbilityState, Health, PlayerSlot


class HudSystem:
    def update(self, world, dt_ms: int) -> None:
        _ = dt_ms
        players: list[dict[str, object]] = []
        for _, slot, health, ability in world.query(PlayerSlot, Health, AbilityState):
            players.append(
                {
                    "slot": slot.slot,
                    "hp": health.current,
                    "max_hp": health.maximum,
                    "lives": slot.lives,
                    "ability": ability.current,
                }
            )
        world.resources["hud"] = {
            "players": sorted(players, key=lambda item: int(item["slot"])),
            "energy_spheres": world.resources.get("run_energy_spheres", 0),
            "stage_cleared": bool(world.resources.get("stage_cleared", False)),
        }
