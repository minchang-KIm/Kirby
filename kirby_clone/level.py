from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .physics import TileCollisionWorld


@dataclass(frozen=True)
class EnemySpawn:
    x: float
    y: float
    kind: str
    patrol_left: float
    patrol_right: float


@dataclass
class LevelData:
    tile_size: int
    width_tiles: int
    height_tiles: int
    solid_tiles: set[tuple[int, int]]
    one_way_tiles: set[tuple[int, int]]
    hazard_tiles: set[tuple[int, int]]
    checkpoint_tiles: set[tuple[int, int]]
    goal_tiles: set[tuple[int, int]]
    collectibles: set[tuple[int, int]]
    player_spawn: tuple[float, float]
    enemy_spawns: list[EnemySpawn]

    @property
    def pixel_width(self) -> int:
        return self.width_tiles * self.tile_size

    @property
    def pixel_height(self) -> int:
        return self.height_tiles * self.tile_size

    def make_collision_world(self) -> TileCollisionWorld:
        return TileCollisionWorld(
            tile_size=self.tile_size,
            width_tiles=self.width_tiles,
            height_tiles=self.height_tiles,
            solid_tiles=set(self.solid_tiles),
            one_way_tiles=set(self.one_way_tiles),
            hazard_tiles=set(self.hazard_tiles),
        )


class LevelLoader:
    def load_level(self, path: str) -> LevelData:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        tile_size = int(raw.get("tile_size", 32))
        rows: list[str] = raw["tiles"]
        if not rows:
            raise ValueError("Level must contain at least one row in 'tiles'.")

        width_tiles = max(len(row) for row in rows)
        height_tiles = len(rows)

        solid_tiles: set[tuple[int, int]] = set()
        one_way_tiles: set[tuple[int, int]] = set()
        hazard_tiles: set[tuple[int, int]] = set()
        checkpoint_tiles: set[tuple[int, int]] = set()
        goal_tiles: set[tuple[int, int]] = set()
        collectibles: set[tuple[int, int]] = set()
        enemy_spawns: list[EnemySpawn] = []
        player_spawn: tuple[float, float] | None = None

        for ty, row in enumerate(rows):
            for tx, symbol in enumerate(row):
                if symbol == "#":
                    solid_tiles.add((tx, ty))
                elif symbol == "=":
                    one_way_tiles.add((tx, ty))
                elif symbol == "^":
                    hazard_tiles.add((tx, ty))
                elif symbol == "C":
                    checkpoint_tiles.add((tx, ty))
                elif symbol == "G":
                    goal_tiles.add((tx, ty))
                elif symbol == "o":
                    collectibles.add((tx, ty))
                elif symbol == "P":
                    player_spawn = (tx * tile_size + 4.0, ty * tile_size - 8.0)
                elif symbol in {"e", "E"}:
                    center_x = tx * tile_size + 2.0
                    spawn_y = ty * tile_size - 8.0
                    spread = tile_size * (5 if symbol == "e" else 3)
                    enemy_spawns.append(
                        EnemySpawn(
                            x=center_x,
                            y=spawn_y,
                            kind="brute" if symbol == "E" else "grunt",
                            patrol_left=max(0.0, center_x - spread),
                            patrol_right=min((width_tiles - 1) * tile_size, center_x + spread),
                        )
                    )

        if player_spawn is None:
            raise ValueError("Level missing 'P' player spawn marker.")

        return LevelData(
            tile_size=tile_size,
            width_tiles=width_tiles,
            height_tiles=height_tiles,
            solid_tiles=solid_tiles,
            one_way_tiles=one_way_tiles,
            hazard_tiles=hazard_tiles,
            checkpoint_tiles=checkpoint_tiles,
            goal_tiles=goal_tiles,
            collectibles=collectibles,
            player_spawn=player_spawn,
            enemy_spawns=enemy_spawns,
        )
