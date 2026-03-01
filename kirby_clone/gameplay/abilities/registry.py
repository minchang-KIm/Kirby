from __future__ import annotations

import json
from pathlib import Path

from .base import AbilityStrategy, DataDrivenAbilityStrategy


class AbilityRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, AbilityStrategy] = {}

    def register(self, strategy: AbilityStrategy) -> None:
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> AbilityStrategy:
        return self._strategies.get(name, self._strategies["none"])

    def names(self) -> list[str]:
        return sorted(self._strategies.keys())

    def load_data_file(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload["abilities"]:
            self.register(
                DataDrivenAbilityStrategy(
                    name=item["name"],
                    damage=int(item["damage"]),
                    cooldown_ms=int(item["cooldown_ms"]),
                    range_px=int(item["range_px"]),
                    projectile_speed=float(item["projectile_speed"]),
                    is_super=bool(item.get("is_super", False)),
                )
            )


def create_default_registry(content_dir: Path) -> AbilityRegistry:
    registry = AbilityRegistry()
    registry.register(
        DataDrivenAbilityStrategy(
            name="none",
            damage=1,
            cooldown_ms=260,
            range_px=32,
            projectile_speed=280.0,
        )
    )
    registry.load_data_file(content_dir / "abilities.json")
    return registry
