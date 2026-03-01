from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameConfig:
    resolution: tuple[int, int] = (1280, 720)
    fullscreen: bool = False
    target_fps: int = 60
    fixed_dt_ms: int = 16
    gravity: float = 2500.0
    move_speed: float = 260.0
    jump_velocity: float = 760.0
    coyote_time_ms: int = 100
    jump_buffer_ms: int = 120
    player_max_hp: int = 10
    invulnerable_ms: int = 900
    tile_size: int = 32
    replay_seed: int = 1337
    level_path: Path = Path("levels/level_01.json")
    content_dir: Path = Path("kirby_clone/content")
    save_path: Path = Path("save/save_data.json")
    max_local_players: int = 4

    @property
    def fixed_dt_seconds(self) -> float:
        return self.fixed_dt_ms / 1000.0
