from __future__ import annotations

from kirby_clone.input import InputState
from kirby_clone.level import LevelLoader
from kirby_clone.math2d import Rect
from kirby_clone.settings import GameConfig
from kirby_clone.simulation import Simulation


def test_restart_from_checkpoint_after_death() -> None:
    config = GameConfig()
    level = LevelLoader().load_level(str(config.level_path))
    sim = Simulation(config=config, level=level, seed=9001)

    sim.checkpoint = (320.0, 256.0)
    sim.player.dead = True
    sim.player.hp = 0
    sim.lost = True

    sim.step(InputState(restart_pressed=True))
    assert sim.lost is False
    assert sim.player.dead is False
    assert sim.player.hp == sim.player.max_hp
    assert (sim.player.body.rect.x, sim.player.body.rect.y) == sim.checkpoint


def test_goal_completion_locks_world_updates() -> None:
    config = GameConfig()
    level = LevelLoader().load_level(str(config.level_path))
    sim = Simulation(config=config, level=level, seed=42)

    goal_tx, goal_ty = next(iter(level.goal_tiles))
    sim.player.body.rect = Rect(goal_tx * level.tile_size + 1, goal_ty * level.tile_size + 1, 28, 28)
    sim.step(InputState.neutral())
    assert sim.won is True

    frame_after_win = sim.frame_index
    sim.step(InputState(move_x=1, jump_pressed=True, jump_held=True))
    assert sim.frame_index == frame_after_win
