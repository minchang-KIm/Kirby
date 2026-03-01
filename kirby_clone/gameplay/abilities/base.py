from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AttackShape:
    dx: float
    dy: float
    width: int
    height: int
    damage: int
    knockback_x: float
    knockback_y: float
    ttl_ms: int
    tag: str


class AbilityStrategy(Protocol):
    name: str

    def on_enter(self, actor: int, world: object) -> None:
        ...

    def handle_input(self, actor: int, command: object, world: object) -> None:
        ...

    def update(self, actor: int, world: object, dt_ms: int) -> None:
        ...

    def get_attack_shapes(self, actor: int, frame_idx: int) -> list[AttackShape]:
        ...


@dataclass
class DataDrivenAbilityStrategy:
    name: str
    damage: int
    cooldown_ms: int
    range_px: int
    projectile_speed: float
    is_super: bool = False

    def on_enter(self, actor: int, world: object) -> None:
        # Strategy objects are stateless; per-actor cooldown lives in AbilityState component.
        _ = (actor, world)

    def handle_input(self, actor: int, command: object, world: object) -> None:
        if command.__class__.__name__ != "AbilityUseCommand":
            return
        world.events.publish(
            "ability_use_requested",
            {
                "actor": actor,
                "ability": self.name,
                "damage": self.damage,
                "range_px": self.range_px,
                "speed": self.projectile_speed,
                "cooldown_ms": self.cooldown_ms,
                "is_super": self.is_super,
            },
        )

    def update(self, actor: int, world: object, dt_ms: int) -> None:
        _ = (actor, world, dt_ms)

    def get_attack_shapes(self, actor: int, frame_idx: int) -> list[AttackShape]:
        _ = (actor, frame_idx)
        return [
            AttackShape(
                dx=float(self.range_px),
                dy=0.0,
                width=max(20, self.range_px // 3),
                height=18,
                damage=self.damage,
                knockback_x=self.projectile_speed * 0.2,
                knockback_y=-90.0,
                ttl_ms=280,
                tag=self.name,
            )
        ]
