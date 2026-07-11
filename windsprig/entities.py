from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TYPE_CHECKING

from .combat import HitEvent
from .math2d import Rect

if TYPE_CHECKING:
    from .input import InputState
    from .physics import TileCollisionWorld


@dataclass
class WorldState:
    collision_map: "TileCollisionWorld"
    entity_index: dict[int, "Entity"]
    rng_seed: int
    event_bus: list[dict[str, object]] = field(default_factory=list)
    frame_index: int = 0
    player_id: int = 1


class Entity(Protocol):
    entity_id: int
    team: str
    dead: bool

    def update(self, dt_ms: int, world: WorldState) -> None:
        ...

    def get_aabb(self) -> Rect:
        ...

    def on_hit(self, hit: HitEvent) -> None:
        ...

    def get_hurtbox(self) -> "HurtboxLike":
        ...

    def get_hitboxes(self, frame_index: int) -> list["HitboxLike"]:
        ...


class HitboxLike(Protocol):
    ...


class HurtboxLike(Protocol):
    ...
