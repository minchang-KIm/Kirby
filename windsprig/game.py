from __future__ import annotations

from .app import run_app
from .config import GameConfig


def run_game(config: GameConfig | None = None) -> int:
    return run_app(config=config)
