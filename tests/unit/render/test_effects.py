"""Deterministic accessibility-aware event effect contracts."""

from __future__ import annotations

import math

import pytest

from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AccessibilitySettings
from windsprig.render.effects import EffectsDirector


def _settings(*, shake: bool = True, reduced_motion: bool = False) -> AccessibilitySettings:
    return AccessibilitySettings(
        screen_shake=shake,
        reduced_motion=reduced_motion,
        draw_toggle=False,
        guard_toggle=False,
    )


def test_reduced_motion_preserves_hit_readability_without_shake_or_afterimages() -> None:
    frame = EffectsDirector(seed=19).handle(
        (GameEvent("AttackHit", {"x": 320.0, "y": 240.0, "facing": -1}),),
        _settings(shake=False, reduced_motion=True),
    )

    assert frame.shake is None
    assert frame.flash is not None
    assert 1 <= len(frame.particles) <= 4
    assert all(particle.kind != "afterimage" for particle in frame.particles)


def test_effects_are_seeded_capped_and_preserve_input_event_order() -> None:
    events = (
        GameEvent("AttackHit", {"x": 10.0, "y": 20.0, "facing": 1}),
        GameEvent("MoteCollected", {"x": 30.0, "y": 40.0}),
        *(GameEvent("StageCompleted", {"x": 50.0, "y": 60.0}) for _ in range(8)),
    )

    first = EffectsDirector(seed=77).handle(events, _settings())
    second = EffectsDirector(seed=77).handle(events, _settings())

    assert first == second
    assert len(first.particles) <= EffectsDirector.MAX_PARTICLES
    kinds = tuple(particle.kind for particle in first.particles)
    first_mote = kinds.index("mote")
    assert all(kind == "impact" for kind in kinds[:first_mote])
    assert all(particle.life_ms > 0 for particle in first.particles)


def test_motion_effects_exist_only_when_both_accessibility_switches_allow_them() -> None:
    event = GameEvent("PlayerDodged", {"x": 120.0, "y": 80.0, "facing": 1})

    enabled = EffectsDirector(seed=3).handle((event,), _settings())
    shake_disabled = EffectsDirector(seed=3).handle((event,), _settings(shake=False))
    reduced = EffectsDirector(seed=3).handle((event,), _settings(reduced_motion=True))

    assert any(particle.kind == "afterimage" for particle in enabled.particles)
    assert enabled.shake is not None
    assert shake_disabled.shake is None
    assert reduced.shake is None
    assert all(particle.kind != "afterimage" for particle in reduced.particles)
    assert reduced.flash is not None


@pytest.mark.parametrize("value", [True, "12", math.inf, -math.inf, math.nan])
def test_effects_reject_malformed_event_coordinates_before_numeric_conversion(value: object) -> None:
    event = GameEvent("AttackHit", {"x": value, "y": 20.0, "facing": 1})

    with pytest.raises((TypeError, ValueError), match="x"):
        EffectsDirector(seed=1).handle((event,), _settings())


@pytest.mark.parametrize("facing", [True, 0, 2, 1.0, "left"])
def test_effects_reject_unsupported_facing_tokens(facing: object) -> None:
    event = GameEvent("AttackHit", {"x": 10.0, "y": 20.0, "facing": facing})

    with pytest.raises((TypeError, ValueError), match="facing"):
        EffectsDirector(seed=1).handle((event,), _settings())


def test_effects_reject_invalid_public_inputs_without_consuming_rng() -> None:
    director = EffectsDirector(seed=9)
    valid_event = GameEvent("AttackHit", {"x": 1.0, "y": 2.0, "facing": 1})
    control = EffectsDirector(seed=9)

    with pytest.raises(TypeError, match="GameEvent"):
        director.handle((object(),), _settings())  # type: ignore[arg-type]

    assert director.handle((valid_event,), _settings()) == control.handle((valid_event,), _settings())
    with pytest.raises(TypeError, match="seed"):
        EffectsDirector(seed=True)
