"""Deterministic audio-service fake used by presentation contract tests."""

from __future__ import annotations

from windsprig.platform.services import AudioBus, AudioStatus


class FakeAudioService:
    """Record calls while allowing individual cue failures to be injected."""

    def __init__(
        self,
        *,
        failed_cues: frozenset[str] = frozenset(),
        raised_cues: frozenset[str] = frozenset(),
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.volume_calls: list[tuple[str, float]] = []
        self.mute_calls: list[bool] = []
        self.failed_cues = failed_cues
        self.raised_cues = raised_cues
        self.pause_count = 0
        self.resume_count = 0
        self._status = AudioStatus(ready=True, muted=False)

    @property
    def status(self) -> AudioStatus:
        return self._status

    async def initialize(self, after_user_gesture: bool = False) -> AudioStatus:
        del after_user_gesture
        return self._status

    def play_cue(self, cue_id: str, bus: AudioBus = "sfx") -> bool:
        self.calls.append((cue_id, bus))
        if cue_id in self.raised_cues:
            raise RuntimeError("injected audio failure")
        return cue_id not in self.failed_cues

    def pause(self) -> None:
        self.pause_count += 1
        self._status = AudioStatus(ready=True, muted=True, error_code="focus_lost")

    def resume(self) -> None:
        self.resume_count += 1
        self._status = AudioStatus(ready=True, muted=False)

    def set_bus_volume(self, bus: AudioBus, value: float) -> None:
        self.volume_calls.append((bus, value))

    def set_muted(self, muted: bool) -> None:
        self.mute_calls.append(muted)
        self._status = AudioStatus(ready=True, muted=muted)
