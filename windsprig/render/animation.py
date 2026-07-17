"""Immutable render-cadence animation clips, cursors, and lookup bank."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

_TOKEN_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*\Z")


def _token(name: str, value: object) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if _TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a non-empty lowercase stable token")
    return value


def _strict_non_negative_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class AnimationClip:
    """Define one validated immutable clip in atlas-frame order."""

    clip_id: str
    frame_ids: tuple[int, ...]
    frame_ms: tuple[int, ...]
    loop: bool
    markers: tuple[tuple[int, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "clip_id", _token("clip ID", self.clip_id))
        if type(self.frame_ids) is not tuple or not self.frame_ids:
            raise ValueError("animation frame IDs must be a non-empty tuple")
        if any(type(frame_id) is not int for frame_id in self.frame_ids):
            raise TypeError("animation frame IDs must be integers")
        if any(frame_id < 0 for frame_id in self.frame_ids):
            raise ValueError("animation frame IDs must be non-negative")
        if len(self.frame_ids) != len(set(self.frame_ids)):
            raise ValueError("animation frame IDs must be unique")
        if type(self.frame_ms) is not tuple:
            raise TypeError("animation frame durations must be a tuple")
        if len(self.frame_ms) != len(self.frame_ids):
            raise ValueError("animation frames and durations must have equal length")
        if any(type(duration) is not int for duration in self.frame_ms):
            raise TypeError("animation frame durations must be integers")
        if any(duration <= 0 for duration in self.frame_ms):
            raise ValueError("animation frame durations must be positive")
        if type(self.loop) is not bool:
            raise TypeError("animation loop must be a boolean")
        if type(self.markers) is not tuple:
            raise TypeError("animation markers must be a tuple")
        normalized: list[tuple[int, str]] = []
        identities: set[tuple[int, str]] = set()
        marker_names: set[str] = set()
        for marker in self.markers:
            if type(marker) is not tuple or len(marker) != 2:
                raise TypeError("animation markers must be frame/token tuples")
            frame_index, marker_name = marker
            if type(frame_index) is not int:
                raise TypeError("animation marker frame index must be an integer")
            if not 0 <= frame_index < len(self.frame_ids):
                raise ValueError("animation marker frame index is out of bounds")
            stable_name = _token("animation marker", marker_name)
            identity = (frame_index, stable_name)
            if identity in identities or stable_name in marker_names:
                raise ValueError("animation marker identities must be unique")
            identities.add(identity)
            marker_names.add(stable_name)
            normalized.append(identity)
        object.__setattr__(self, "markers", tuple(normalized))


@dataclass(frozen=True, slots=True)
class AnimationCursor:
    """Advance one clip strictly from explicit render deltas."""

    clip: AnimationClip
    frame_index: int
    elapsed_in_frame_ms: int
    finished: bool

    def __post_init__(self) -> None:
        if not isinstance(self.clip, AnimationClip):
            raise TypeError("animation cursor clip must be an AnimationClip")
        frame_index = _strict_non_negative_int("animation frame index", self.frame_index)
        if frame_index >= len(self.clip.frame_ids):
            raise ValueError("animation cursor frame index is out of bounds")
        elapsed = _strict_non_negative_int("animation elapsed time", self.elapsed_in_frame_ms)
        if elapsed >= self.clip.frame_ms[frame_index] and not self.finished:
            raise ValueError("unfinished animation cursor elapsed time exceeds its frame")
        if type(self.finished) is not bool:
            raise TypeError("animation cursor finished must be a boolean")
        if self.finished and (self.clip.loop or frame_index != len(self.clip.frame_ids) - 1 or elapsed != 0):
            raise ValueError("only a terminal non-loop animation cursor may be finished")

    @classmethod
    def start(cls, clip: AnimationClip) -> AnimationCursor:
        """Create a cursor before the first frame has consumed render time."""

        if not isinstance(clip, AnimationClip):
            raise TypeError("clip must be an AnimationClip")
        return cls(clip, 0, 0, False)

    @property
    def frame_id(self) -> int:
        """Return the current atlas frame identity."""

        return self.clip.frame_ids[self.frame_index]

    def advance(self, dt_ms: int) -> tuple[AnimationCursor, tuple[str, ...]]:
        """Advance once and emit every crossed marker exactly once."""

        delta = _strict_non_negative_int("render delta", dt_ms)
        if delta == 0 or self.finished:
            return self, ()

        index = self.frame_index
        elapsed = self.elapsed_in_frame_ms + delta
        finished = False
        markers: list[str] = []
        markers_by_frame: dict[int, tuple[str, ...]] = {}
        for marker_index, marker_name in self.clip.markers:
            markers_by_frame.setdefault(marker_index, ())
            markers_by_frame[marker_index] += (marker_name,)

        while elapsed >= self.clip.frame_ms[index]:
            elapsed -= self.clip.frame_ms[index]
            next_index = index + 1
            if next_index == len(self.clip.frame_ids):
                if self.clip.loop:
                    next_index = 0
                else:
                    # Terminal clips own their last frame for its full duration, then freeze.
                    elapsed = 0
                    finished = True
                    break
            index = next_index
            markers.extend(markers_by_frame.get(index, ()))

        return replace(
            self,
            frame_index=index,
            elapsed_in_frame_ms=elapsed,
            finished=finished,
        ), tuple(markers)


@dataclass(frozen=True, slots=True)
class AnimationBank:
    """Own a canonical immutable clip map with an explicit idle fallback."""

    clips: Mapping[str, AnimationClip]
    fallback_clip_id: str = "idle"

    def __post_init__(self) -> None:
        if not isinstance(self.clips, Mapping):
            raise TypeError("animation clips must be a mapping")
        copied: dict[str, AnimationClip] = {}
        for raw_key, clip in self.clips.items():
            key = _token("animation clip key", raw_key)
            if not isinstance(clip, AnimationClip):
                raise TypeError(f"animation clip {key} must be an AnimationClip")
            if key in copied:
                raise ValueError(f"duplicate animation clip key: {key}")
            copied[key] = clip
        fallback = _token("animation fallback clip ID", self.fallback_clip_id)
        if fallback not in copied:
            raise ValueError("animation fallback clip must exist in the bank")
        object.__setattr__(self, "clips", MappingProxyType(dict(sorted(copied.items()))))
        object.__setattr__(self, "fallback_clip_id", fallback)

    def clip_for(self, actor_state: str) -> AnimationClip:
        """Resolve a canonical actor state, falling back to the documented idle clip."""

        if type(actor_state) is not str:
            raise TypeError("actor state must be a string")
        key = actor_state.strip().lower().replace(" ", "_")
        if _TOKEN_PATTERN.fullmatch(key) is None:
            raise ValueError("actor state must be a non-empty stable token")
        return self.clips.get(key, self.clips[self.fallback_clip_id])


def build_default_animation_bank() -> AnimationBank:
    """Return the canonical 56-frame Sprig animation map used by all actor cursors."""

    clips = {
        "idle": AnimationClip("idle", (0, 1, 2, 3), (160, 160, 160, 160), True),
        "run": AnimationClip("run", (4, 5, 6, 7, 8, 9), (90, 90, 90, 90, 90, 90), True),
        "jump": AnimationClip("jump", (10, 11), (110, 140), False),
        "fall": AnimationClip("fall", (12, 13), (140, 140), True),
        "hover": AnimationClip("hover", (14, 15, 16, 17), (120, 120, 120, 120), True),
        "draw": AnimationClip("draw", (18, 19, 20, 21), (90, 90, 90, 90), True),
        "captured": AnimationClip("captured", (22, 23, 24, 25), (110, 110, 110, 110), True),
        "harmonize": AnimationClip(
            "harmonize",
            (26, 27, 28, 29, 30, 31),
            (80, 80, 80, 80, 80, 110),
            False,
            ((3, "equip"),),
        ),
        "attack": AnimationClip(
            "attack",
            (32, 33, 34, 35, 36, 37),
            (70, 70, 70, 70, 70, 100),
            False,
            ((2, "swing"),),
        ),
        "guard": AnimationClip("guard", (38, 39), (140, 140), True),
        "dodge": AnimationClip("dodge", (40, 41, 42, 43), (60, 60, 60, 90), False),
        "hurt": AnimationClip("hurt", (44, 45), (90, 120), False),
        "defeated": AnimationClip("defeated", (46, 47, 48, 49), (160, 160, 160, 240), False),
        "victory": AnimationClip("victory", (50, 51, 52, 53, 54, 55), (120, 120, 120, 120, 120, 160), True),
    }
    # Gameplay's terminal state is named Dead; both tokens intentionally share one clip value.
    clips["dead"] = clips["defeated"]
    return AnimationBank(clips)


__all__ = ["AnimationBank", "AnimationClip", "AnimationCursor", "build_default_animation_bank"]
