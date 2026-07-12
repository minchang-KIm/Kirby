"""Coordinate allowlisted phase music and SFX without touching simulation state."""

from __future__ import annotations

import math
from collections.abc import Sequence

from windsprig.audio.catalog import BOSS_PHASES, MUSIC_CUE_IDS
from windsprig.audio.cues import cue_for_event
from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AudioSettings
from windsprig.platform.services import AudioService, AudioStatus


def _validated_settings(settings: AudioSettings) -> tuple[float, float, float, bool]:
    if type(settings) is not AudioSettings:
        raise TypeError("settings must be an exact AudioSettings")
    volumes: list[float] = []
    for name in ("master_volume", "music_volume", "sfx_volume"):
        value = getattr(settings, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a finite number between zero and one")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(f"{name} must be a finite number between zero and one")
        volumes.append(number)
    if type(settings.muted) is not bool:
        raise TypeError("muted must be a boolean")
    return volumes[0], volumes[1], volumes[2], settings.muted


def _boss_music_cue(event: GameEvent) -> str | None:
    boss_id = event.payload.get("boss_id")
    phase_id = event.payload.get("phase_id")
    phase_index = event.payload.get("phase_index")
    if type(boss_id) is not str or type(phase_id) is not str or type(phase_index) is not int:
        return None
    phase_ids = BOSS_PHASES.get(boss_id)
    if phase_ids is None or not 1 <= phase_index <= len(phase_ids):
        return None
    if phase_ids[phase_index - 1] != phase_id:
        return None
    return f"music.boss.{boss_id}.p{phase_index}"


class MusicDirector:
    """Own presentation audio selection while preserving input event order."""

    def __init__(self, audio: AudioService) -> None:
        self.audio = audio
        self.current_music: str | None = None

    @property
    def status(self) -> AudioStatus:
        """Expose the platform's immutable ready/muted lifecycle status."""

        return self.audio.status

    def start(self, cue_id: str) -> bool:
        """Start one exact music cue, updating state only after playback succeeds."""

        if type(cue_id) is not str:
            raise TypeError("music cue ID must be a string")
        if cue_id not in MUSIC_CUE_IDS:
            raise ValueError(f"music cue ID must be a known music cue: {cue_id}")
        if cue_id == self.current_music:
            return True
        try:
            played = self.audio.play_cue(cue_id, "music")
        except Exception:
            # Audio loss is an explicitly recoverable platform capability.
            return False
        if played:
            self.current_music = cue_id
        return played

    def handle(self, events: Sequence[GameEvent]) -> tuple[str, ...]:
        """Play valid events in order and isolate one runtime audio failure."""

        played: list[str] = []
        for event in events:
            if type(event) is not GameEvent:
                continue
            if event.topic == "BossPhaseChanged":
                cue_id = _boss_music_cue(event)
                if cue_id is None or cue_id == self.current_music:
                    continue
                if self.start(cue_id):
                    played.append(cue_id)
                continue
            cue_id = cue_for_event(event)
            if cue_id is None:
                continue
            try:
                if self.audio.play_cue(cue_id, "sfx"):
                    played.append(cue_id)
            except Exception:
                # A broken optional sound must not suppress later semantic events.
                continue
        return tuple(played)

    def apply_settings(self, settings: AudioSettings) -> None:
        """Validate first, then apply exact master-times-bus volumes and mute."""

        master, music, sfx, muted = _validated_settings(settings)
        effective_master = 0.0 if muted else master
        self.audio.set_bus_volume("music", effective_master * music)
        self.audio.set_bus_volume("sfx", effective_master * sfx)
        self.audio.set_muted(muted)

    def pause(self) -> None:
        """Delegate focus-loss suspension to the platform service."""

        self.audio.pause()

    def resume(self) -> None:
        """Delegate focus restoration to the platform service."""

        self.audio.resume()


__all__ = ["MusicDirector"]
