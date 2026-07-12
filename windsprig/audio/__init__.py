"""Presentation-only audio cues, direction, and the retained legacy facade."""

from __future__ import annotations


class AudioManager:
    """Retain the prototype initialization facade while AudioService owns playback.

    Older study helpers still exercise this class. Production playback is routed
    through :class:`windsprig.platform.services.AudioService`, so the two legacy
    play methods deliberately have no side effects.
    """

    def __init__(self) -> None:
        import pygame

        self.enabled = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False

    def play_sfx(self, _name: str) -> None:
        """Leave legacy playback to the production AudioService boundary."""

    def play_bgm(self, _name: str) -> None:
        """Leave legacy playback to the production AudioService boundary."""


__all__ = ["AudioManager"]
