"""Derive bounded deterministic presentation effects from immutable events."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AccessibilitySettings


def _finite_number(name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise TypeError(f"{name} must be a number")
    result = float(cast(int | float, value))
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _stable_token(name: str, value: object) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


@dataclass(frozen=True, slots=True)
class Particle:
    """One bounded visual particle independent of gameplay simulation state."""

    kind: str
    x: float
    y: float
    vx: float
    vy: float
    life_ms: int
    color_token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _stable_token("particle kind", self.kind))
        for name in ("x", "y", "vx", "vy"):
            object.__setattr__(self, name, _finite_number(f"particle {name}", getattr(self, name)))
        object.__setattr__(self, "life_ms", _positive_int("particle life", self.life_ms))
        object.__setattr__(self, "color_token", _stable_token("particle color token", self.color_token))


@dataclass(frozen=True, slots=True)
class Shake:
    """A render-only camera shake envelope."""

    amplitude_px: int
    duration_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "amplitude_px", _positive_int("shake amplitude", self.amplitude_px))
        object.__setattr__(self, "duration_ms", _positive_int("shake duration", self.duration_ms))


@dataclass(frozen=True, slots=True)
class Flash:
    """A patterned hit flash that remains legible without motion."""

    x: float
    y: float
    radius_px: int
    pattern_token: str
    duration_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite_number("flash x", self.x))
        object.__setattr__(self, "y", _finite_number("flash y", self.y))
        object.__setattr__(self, "radius_px", _positive_int("flash radius", self.radius_px))
        object.__setattr__(self, "pattern_token", _stable_token("flash pattern token", self.pattern_token))
        object.__setattr__(self, "duration_ms", _positive_int("flash duration", self.duration_ms))


@dataclass(frozen=True, slots=True)
class EffectFrame:
    """Atomic presentation effects derived from one ordered event batch."""

    particles: tuple[Particle, ...]
    shake: Shake | None
    flash: Flash | None

    def __post_init__(self) -> None:
        if type(self.particles) is not tuple or any(not isinstance(item, Particle) for item in self.particles):
            raise TypeError("effect particles must be a tuple of Particle values")
        if self.shake is not None and not isinstance(self.shake, Shake):
            raise TypeError("effect shake must be Shake or None")
        if self.flash is not None and not isinstance(self.flash, Flash):
            raise TypeError("effect flash must be Flash or None")


@dataclass(frozen=True, slots=True)
class _EffectSpec:
    kind: str
    count: int
    amplitude: int
    duration_ms: int
    pattern: str


_EVENT_EFFECTS: Final = MappingProxyType(
    {
        "PlayerDamaged": _EffectSpec("impact", 10, 8, 120, "pattern.damage"),
        "PlayerDodged": _EffectSpec("afterimage", 8, 4, 70, "pattern.dodge"),
        "EnemyCaptured": _EffectSpec("wind_ribbon", 12, 0, 0, "pattern.capture"),
        "CaptureReleased": _EffectSpec("leaf", 6, 0, 0, "pattern.release"),
        "EnemyLaunched": _EffectSpec("streak", 14, 10, 150, "pattern.launch"),
        "AbilityEquipped": _EffectSpec("spark", 16, 0, 0, "pattern.harmonize"),
        "AbilityDropped": _EffectSpec("echo", 8, 0, 0, "pattern.echo"),
        "AttackHit": _EffectSpec("impact", 12, 8, 100, "pattern.hit"),
        "ProjectileCut": _EffectSpec("shard", 8, 4, 70, "pattern.cut"),
        "MoteCollected": _EffectSpec("mote", 18, 0, 0, "pattern.mote"),
        "CheckpointReached": _EffectSpec("leaf", 20, 0, 0, "pattern.checkpoint"),
        "PlayerDefeated": _EffectSpec("paper", 14, 4, 90, "pattern.defeat"),
        "PlayerRespawned": _EffectSpec("wind_ribbon", 16, 0, 0, "pattern.respawn"),
        "GatherCompleted": _EffectSpec("spark", 20, 5, 80, "pattern.goal"),
        "StageCompleted": _EffectSpec("confetti", 28, 6, 100, "pattern.victory"),
        "StageFailed": _EffectSpec("paper", 18, 3, 70, "pattern.defeat"),
        "BossPhaseChanged": _EffectSpec("shard", 24, 7, 110, "pattern.boss"),
    }
)


@dataclass(frozen=True, slots=True)
class _PreparedEffect:
    spec: _EffectSpec
    x: float
    y: float
    facing: int


class EffectsDirector:
    """Own presentation RNG and transform semantic events without gameplay authority."""

    MAX_PARTICLES: Final = 96

    def __init__(self, seed: int) -> None:
        if type(seed) is not int:
            raise TypeError("effects seed must be an integer")
        self._rng = random.Random(seed)

    def _prepare(self, events: Sequence[GameEvent]) -> tuple[_PreparedEffect, ...]:
        if isinstance(events, (str, bytes, bytearray)) or not isinstance(events, Sequence):
            raise TypeError("events must be a sequence of GameEvent values")
        prepared: list[_PreparedEffect] = []
        for event in events:
            if not isinstance(event, GameEvent):
                raise TypeError("events must contain only GameEvent values")
            spec = _EVENT_EFFECTS.get(event.topic)
            if spec is None:
                continue
            x = _finite_number("event payload x", event.payload.get("x", 640.0))
            y = _finite_number("event payload y", event.payload.get("y", 360.0))
            raw_facing = event.payload.get("facing", 1)
            if type(raw_facing) is not int:
                raise TypeError("event payload facing must be an integer")
            if raw_facing not in {-1, 1}:
                raise ValueError("event payload facing must be -1 or 1")
            prepared.append(_PreparedEffect(spec, x, y, raw_facing))
        return tuple(prepared)

    def handle(
        self,
        events: Sequence[GameEvent],
        settings: AccessibilitySettings,
    ) -> EffectFrame:
        """Derive one bounded frame after validating the complete event batch atomically."""

        if not isinstance(settings, AccessibilitySettings):
            raise TypeError("settings must be AccessibilitySettings")
        prepared = self._prepare(events)
        particles: list[Particle] = []
        shake: Shake | None = None
        flash: Flash | None = None
        for item in prepared:
            spec = item.spec
            count = min(spec.count, 4) if settings.reduced_motion else spec.count
            kind = "impact" if settings.reduced_motion and spec.kind == "afterimage" else spec.kind
            available = max(0, self.MAX_PARTICLES - len(particles))
            for index in range(min(count, available)):
                angle = self._rng.random() * math.tau
                speed = 35.0 + self._rng.random() * 95.0
                particles.append(
                    Particle(
                        kind,
                        item.x,
                        item.y,
                        math.cos(angle) * speed * item.facing,
                        math.sin(angle) * speed,
                        240 + index * 18,
                        spec.pattern,
                    )
                )
            flash = Flash(item.x, item.y, 28, spec.pattern, 90)
            if settings.screen_shake and not settings.reduced_motion and spec.amplitude > 0:
                shake = Shake(spec.amplitude, spec.duration_ms)
        return EffectFrame(tuple(particles), shake, flash)


def empty_effect_frame() -> EffectFrame:
    """Return the canonical immutable no-effect value."""

    return EffectFrame((), None, None)


__all__ = [
    "EffectFrame",
    "EffectsDirector",
    "Flash",
    "Particle",
    "Shake",
    "empty_effect_frame",
]
