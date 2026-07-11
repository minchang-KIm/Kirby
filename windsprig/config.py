from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GameConfig:
    """Validated simulation, presentation, and release tuning values."""

    resolution: tuple[int, int] = (1280, 720)
    fullscreen: bool = False
    target_fps: int = 60
    fixed_dt_ms: int = 16
    max_catch_up_steps: int = 5
    max_frame_elapsed_ms: int = 250
    gravity: float = 2500.0
    move_speed: float = 260.0
    jump_velocity: float = 760.0
    coyote_time_ms: int = 100
    jump_buffer_ms: int = 120
    hover_duration_ms: int = 850
    hover_gravity_scale: float = 0.28
    guard_damage_multiplier: float = 0.40
    guard_knockback_multiplier: float = 0.35
    guard_speed_multiplier: float = 0.40
    dodge_duration_ms: int = 160
    dodge_invulnerable_ms: int = 128
    dodge_cooldown_ms: int = 520
    dodge_speed: float = 620.0
    draw_base_range_px: float = 78.0
    draw_range_growth_px_per_ms: float = 0.20
    draw_max_bonus_range_px: float = 80.0
    respawn_delay_ms: int = 1800
    respawn_invulnerable_ms: int = 1200
    gather_countdown_ms: int = 3000
    player_max_hp: int = 10
    invulnerable_ms: int = 900
    tile_size: int = 32
    replay_seed: int = 1337
    level_path: Path = Path("levels/level_01.json")
    content_dir: Path = Path(__file__).resolve().parent / "content"
    max_local_players: int = 4
    release_version: str = "1.0.0"
    commit_sha: str = "development"

    def __post_init__(self) -> None:
        if self.resolution != (1280, 720):
            raise ValueError("The logical resolution must remain 1280x720.")
        if self.fixed_dt_ms != 16:
            raise ValueError("The deterministic simulation step must remain 16 ms.")
        if self.max_catch_up_steps < 1:
            raise ValueError("max_catch_up_steps must be positive.")

    @property
    def fixed_dt_seconds(self) -> float:
        """Return the fixed simulation step in seconds for physics integrations."""
        return self.fixed_dt_ms / 1000.0
