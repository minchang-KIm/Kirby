from __future__ import annotations

from dataclasses import dataclass

from .math2d import Rect, Vec2


@dataclass(frozen=True)
class Hitbox:
    owner_id: int
    owner_team: str
    rect: Rect
    damage: int
    knockback: Vec2
    start_frame: int
    end_frame: int

    def is_active(self, frame_index: int) -> bool:
        return self.start_frame <= frame_index <= self.end_frame


@dataclass(frozen=True)
class Hurtbox:
    owner_id: int
    owner_team: str
    rect: Rect


@dataclass(frozen=True)
class HitEvent:
    attacker_id: int
    target_id: int
    damage: int
    knockback: Vec2
    frame_index: int


class CombatResolver:
    """Frame-based combat resolver with simple i-frame tracking."""

    def __init__(self, i_frame_frames: int = 54) -> None:
        self.i_frame_frames = i_frame_frames
        self._invulnerable_until: dict[int, int] = {}

    def clear(self) -> None:
        self._invulnerable_until.clear()

    def step(self, frame_index: int, attackers: list[Hitbox], hurtboxes: list[Hurtbox]) -> list[HitEvent]:
        events: list[HitEvent] = []
        for hitbox in attackers:
            if not hitbox.is_active(frame_index):
                continue
            for hurtbox in hurtboxes:
                if hurtbox.owner_id == hitbox.owner_id:
                    continue
                if hurtbox.owner_team == hitbox.owner_team:
                    continue
                if self._invulnerable_until.get(hurtbox.owner_id, -1) >= frame_index:
                    continue
                if not hitbox.rect.intersects(hurtbox.rect):
                    continue

                events.append(
                    HitEvent(
                        attacker_id=hitbox.owner_id,
                        target_id=hurtbox.owner_id,
                        damage=hitbox.damage,
                        knockback=hitbox.knockback,
                        frame_index=frame_index,
                    )
                )
                self._invulnerable_until[hurtbox.owner_id] = frame_index + self.i_frame_frames
        return events
