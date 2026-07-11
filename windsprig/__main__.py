"""Native startup boundary for the shared asynchronous game coordinator."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pygame

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.platform.native import create_native_services
from windsprig.screens.foundation import create_foundation_screen_factory


async def run_native(config: GameConfig | None = None) -> int:
    """Initialize native pygame services and always release them after the app loop."""
    pygame.init()
    try:
        active_config = config or GameConfig()
        services = create_native_services(active_config)
        factory = create_foundation_screen_factory(
            active_config,
            services,
            lambda: datetime.now(UTC),
        )
        services.display.create_window(active_config.resolution, active_config.fullscreen)
        return await GameApp(active_config, services, factory).run()
    finally:
        pygame.quit()


def main(config: GameConfig | None = None) -> int:
    """Run the native async entrypoint for console and legacy callers."""
    return asyncio.run(run_native(config))


if __name__ == "__main__":
    raise SystemExit(main())
