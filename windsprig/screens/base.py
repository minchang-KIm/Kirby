"""Typed screen lifecycle and transition contracts for the shared app loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Protocol

import pygame

from windsprig.input.commands import InputFrame

ScreenId = Literal[
    "boot",
    "title",
    "profile",
    "hub",
    "world_map",
    "stage_intro",
    "playing",
    "paused",
    "results",
    "defeat",
    "settings",
    "controls",
    "credits",
    "recovery",
]


@dataclass(frozen=True, slots=True)
class ScreenTransition:
    """Request one screen change with a shallow immutable payload snapshot."""

    target: ScreenId
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class Screen(Protocol):
    """Receive deterministic updates and render interpolated presentation state."""

    def on_enter(self, payload: Mapping[str, object]) -> None:
        """Activate the screen with transition-owned immutable data."""
        raise NotImplementedError

    def on_exit(self) -> None:
        """Release state scoped to the current activation."""
        raise NotImplementedError

    def fixed_update(self, dt_ms: int, input_frame: InputFrame) -> ScreenTransition | None:
        """Advance exactly one fixed step and optionally request a transition."""
        raise NotImplementedError

    def render(self, canvas: pygame.Surface, alpha: float) -> None:
        """Draw one frame on the shared logical canvas without presenting it."""
        raise NotImplementedError


class ScreenFactory(Protocol):
    """Resolve stable screen IDs without owning the application loop."""

    def create(self, screen_id: ScreenId) -> Screen:
        """Return the screen implementation for ``screen_id``."""
        raise NotImplementedError
