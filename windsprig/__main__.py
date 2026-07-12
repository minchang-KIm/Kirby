"""Native startup and isolated package-smoke boundary."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pygame

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.platform.native import create_native_services
from windsprig.screens.foundation import create_foundation_screen_factory

_SMOKE_FRAMES = 3
_SMOKE_PROFILE = "Package Smoke"


async def run_native(
    config: GameConfig | None = None,
    *,
    smoke_test: bool = False,
    data_dir: Path | None = None,
) -> int:
    """Initialize native services, optionally render/save in isolation, and always release pygame."""

    if smoke_test and data_dir is None:
        raise ValueError("smoke_test requires an isolated data_dir")
    pygame.init()
    try:
        active_config = config or GameConfig()
        services = (
            create_native_services(active_config)
            if data_dir is None
            else create_native_services(active_config, data_dir=data_dir)
        )
        try:
            await services.audio.initialize(after_user_gesture=False)
        except Exception:
            # Native audio may degrade to muted play without blocking startup or package diagnostics.
            pass
        factory = create_foundation_screen_factory(
            active_config,
            services,
            lambda: datetime.now(UTC),
        )
        services.display.create_window(active_config.resolution, active_config.fullscreen)
        if not smoke_test:
            return await GameApp(active_config, services, factory).run()
        app = GameApp(active_config, services, factory, initial_screen_id="title")
        for _ in range(_SMOKE_FRAMES):
            await app.run_frame()
        profile = replace(app.save_data.profiles[0], display_name=_SMOKE_PROFILE)
        data = replace(
            app.save_data,
            profiles=(profile, app.save_data.profiles[1], app.save_data.profiles[2]),
        )
        return 0 if app.save_service.save(data).ok else 2
    finally:
        pygame.quit()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="Windsprig", description="Windsprig: Echoes of the Gale")
    parser.add_argument("--smoke-test", action="store_true", help="run the packaged render/save diagnostic and exit")
    parser.add_argument("--data-dir", type=Path, help="override the user-data root for package diagnostics")
    return parser.parse_args(argv)


def main(config: GameConfig | None = None, argv: Sequence[str] | None = None) -> int:
    """Run the native entrypoint while preserving programmatic configured callers."""

    args = _parse_args([] if config is not None and argv is None else argv)
    if args.data_dir is not None and not args.smoke_test:
        raise SystemExit("--data-dir is available only with --smoke-test")
    if args.smoke_test and args.data_dir is None:
        raise SystemExit("--smoke-test requires --data-dir")
    return asyncio.run(
        run_native(
            config,
            smoke_test=bool(args.smoke_test),
            data_dir=args.data_dir,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
