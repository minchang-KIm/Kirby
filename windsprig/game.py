"""Legacy native entrypoint compatibility without a second game loop."""

from __future__ import annotations

from windsprig.config import GameConfig


def run_game(config: GameConfig | None = None) -> int:
    """Delegate legacy callers to the sole native async entrypoint."""
    from windsprig.__main__ import main

    return main() if config is None else main(config)
