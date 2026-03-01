from __future__ import annotations

from kirby_clone.combat import CombatResolver, Hitbox, Hurtbox
from kirby_clone.math2d import Rect, Vec2


def test_hit_registered_once_during_iframe_window() -> None:
    resolver = CombatResolver(i_frame_frames=3)
    hitbox = Hitbox(
        owner_id=1,
        owner_team="player",
        rect=Rect(0, 0, 10, 10),
        damage=1,
        knockback=Vec2(10, -10),
        start_frame=0,
        end_frame=20,
    )
    hurtbox = Hurtbox(owner_id=2, owner_team="enemy", rect=Rect(0, 0, 10, 10))

    frame0 = resolver.step(0, [hitbox], [hurtbox])
    frame1 = resolver.step(1, [hitbox], [hurtbox])
    frame4 = resolver.step(4, [hitbox], [hurtbox])

    assert len(frame0) == 1
    assert frame0[0].target_id == 2
    assert frame1 == []
    assert len(frame4) == 1


def test_friendly_fire_is_ignored() -> None:
    resolver = CombatResolver()
    hitbox = Hitbox(
        owner_id=1,
        owner_team="enemy",
        rect=Rect(0, 0, 10, 10),
        damage=1,
        knockback=Vec2(0, 0),
        start_frame=0,
        end_frame=0,
    )
    hurtbox = Hurtbox(owner_id=2, owner_team="enemy", rect=Rect(0, 0, 10, 10))
    events = resolver.step(0, [hitbox], [hurtbox])
    assert events == []
