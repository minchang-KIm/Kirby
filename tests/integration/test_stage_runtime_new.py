from __future__ import annotations

from pathlib import Path

from kirby_clone.content.loader import load_campaign_catalog
from kirby_clone.gameplay.abilities import create_default_registry
from kirby_clone.gameplay.runtime import StageRuntime
from kirby_clone.input.commands import InputFrame
from kirby_clone.settings import GameConfig


def test_stage_runtime_deterministic_snapshot() -> None:
    config = GameConfig()
    catalog = load_campaign_catalog(Path("kirby_clone/content"))
    stage = catalog.stages["world_1_stage_1"]
    registry = create_default_registry(Path("kirby_clone/content"))
    runtime_a = StageRuntime(config, stage, registry, seed=77)
    runtime_b = StageRuntime(config, stage, registry, seed=77)

    for _ in range(20):
        runtime_a.step(InputFrame.empty())
        runtime_b.step(InputFrame.empty())

    assert runtime_a.world.world_hash() == runtime_b.world.world_hash()
