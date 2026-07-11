from __future__ import annotations

from pathlib import Path

from windsprig.config import GameConfig
from windsprig.content.loader import load_campaign_catalog
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.runtime import StageRuntime
from windsprig.input.commands import InputFrame


def test_stage_runtime_deterministic_snapshot() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("windsprig/content"))
    stage = catalog.stages["world_1_stage_1"]
    registry = create_default_registry(Path("windsprig/content"))
    runtime_a = StageRuntime(config, stage, registry, seed=77)
    runtime_b = StageRuntime(config, stage, registry, seed=77)

    for _ in range(20):
        runtime_a.step(InputFrame.empty())
        runtime_b.step(InputFrame.empty())

    assert runtime_a.world.world_hash() == runtime_b.world.world_hash()
