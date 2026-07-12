"""Typed ability activation boundary shared by deterministic strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from windsprig.gameplay.components import AttackRequest


@dataclass(frozen=True, slots=True)
class AbilityContext:
    """Immutable actor and simulation state supplied to one activation."""

    actor_id: int
    frame_index: int
    x: float
    y: float
    facing: int
    on_ground: bool
    charge_ms: int
    combo_step: int
    meter: int


@dataclass(frozen=True, slots=True)
class AbilityExecution:
    """Frozen gameplay effects returned atomically by an ability strategy."""

    attacks: tuple[AttackRequest, ...]
    cooldown_ms: int
    next_combo_step: int
    combo_window_ms: int = 0
    armor_ms: int = 0
    meter_cost: int = 0
    restore_previous: bool = False


class AbilityStrategy(Protocol):
    """Convert a frozen activation context into deterministic gameplay effects."""

    name: str

    def activate(self, context: AbilityContext) -> AbilityExecution:
        """Return all effects for one accepted activation edge."""


class NoneAbilityStrategy:
    """Safe no-op used only for the explicit empty ability sentinel."""

    __slots__ = ()
    name = "none"

    def activate(self, context: AbilityContext) -> AbilityExecution:
        _ = context
        return AbilityExecution(attacks=(), cooldown_ms=0, next_combo_step=0)
