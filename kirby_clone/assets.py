from __future__ import annotations

import pygame


class AssetManager:
    def __init__(self, tile_size: int) -> None:
        self.tile_size = tile_size
        self.tiles: dict[str, pygame.Surface] = {}
        self.sprites: dict[str, pygame.Surface] = {}

    def load_all(self) -> None:
        self.tiles["solid"] = self._make_tile((66, 78, 96))
        self.tiles["one_way"] = self._make_tile((116, 140, 171))
        self.tiles["hazard"] = self._make_tile((219, 89, 89))
        self.tiles["checkpoint"] = self._make_tile((245, 194, 66))
        self.tiles["goal"] = self._make_tile((106, 214, 152))
        self.tiles["collectible"] = self._make_tile((252, 239, 115))

        self.sprites["player_idle"] = self._make_sprite((255, 170, 194), 28, 28)
        self.sprites["player_attack"] = self._make_sprite((255, 146, 180), 28, 28)
        self.sprites["enemy_grunt"] = self._make_sprite((130, 206, 250), 26, 26)
        self.sprites["enemy_brute"] = self._make_sprite((89, 150, 228), 30, 30)

    def _make_tile(self, color: tuple[int, int, int]) -> pygame.Surface:
        surf = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        surf.fill(color)
        pygame.draw.rect(surf, (255, 255, 255, 40), surf.get_rect(), 1)
        return surf

    def _make_sprite(self, color: tuple[int, int, int], w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill(color)
        pygame.draw.rect(surf, (25, 25, 25), surf.get_rect(), 2)
        return surf
