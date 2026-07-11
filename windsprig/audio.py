from __future__ import annotations

import pygame


class AudioManager:
    def __init__(self) -> None:
        self.enabled = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False

    def play_sfx(self, _name: str) -> None:
        # Placeholder: hook real licensed SFX assets here.
        return

    def play_bgm(self, _name: str) -> None:
        # Placeholder: hook real licensed BGM assets here.
        return
