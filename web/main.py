"""Pygbag entry point for the same async Windsprig application runtime."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pygame

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.platform.web import create_web_services
from windsprig.screens.foundation import create_foundation_screen_factory


async def main() -> None:
    """Initialize browser adapters and run the shared coordinator without process shutdown."""
    pygame.init()
    config = GameConfig()
    services = create_web_services(config)
    factory = create_foundation_screen_factory(config, services, lambda: datetime.now(UTC))
    services.display.create_window(config.resolution, fullscreen=False)
    await GameApp(config, services, factory).run()


asyncio.run(main())
