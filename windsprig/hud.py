from __future__ import annotations

import pygame

from .simulation import Simulation


class HudRenderer:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("consolas", 22)
        self.small_font = pygame.font.SysFont("consolas", 16)

    def draw(self, screen: pygame.Surface, sim: Simulation) -> None:
        hp = self.font.render(f"HP: {sim.player.hp}/{sim.player.max_hp}", True, (255, 255, 255))
        gems = self.font.render(f"Stars: {sim.collected_count}", True, (255, 255, 255))
        frame = self.small_font.render(f"Frame: {sim.frame_index}", True, (220, 220, 220))
        screen.blit(hp, (16, 10))
        screen.blit(gems, (16, 38))
        screen.blit(frame, (16, 66))

        if sim.paused:
            self._draw_center_overlay(screen, "Paused - Press Esc")
        elif sim.lost:
            self._draw_center_overlay(screen, "You Died - Press R")
        elif sim.won:
            self._draw_center_overlay(screen, "Stage Clear!")

    def _draw_center_overlay(self, screen: pygame.Surface, text: str) -> None:
        w, h = screen.get_size()
        box = pygame.Rect(w // 2 - 220, h // 2 - 45, 440, 90)
        pygame.draw.rect(screen, (10, 10, 10, 190), box, border_radius=12)
        pygame.draw.rect(screen, (255, 255, 255), box, 2, border_radius=12)
        msg = self.font.render(text, True, (255, 255, 255))
        screen.blit(msg, (box.centerx - msg.get_width() // 2, box.centery - msg.get_height() // 2))
