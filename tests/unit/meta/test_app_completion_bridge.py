from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from windsprig.app import GameApp


def test_prototype_runtime_count_maps_to_idempotent_catalog_motes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    app = GameApp()
    stage = app.catalog.stages["world_1_stage_1"]
    app.runtime = SimpleNamespace(
        stage=stage,
        world=SimpleNamespace(
            resources={"stage_cleared": True, "run_energy_spheres": 99},
            frame_index=10,
        ),
    )

    app._on_stage_progress()
    app.runtime = SimpleNamespace(
        stage=stage,
        world=SimpleNamespace(
            resources={"stage_cleared": True, "run_energy_spheres": 99},
            frame_index=12,
        ),
    )
    app._on_stage_progress()

    assert app.tracker.collected_mote_ids == {
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
        "world_1_stage_1:mote:3",
    }
    assert app.tracker.best_times_ms == {"world_1_stage_1": 160}
    assert app.tracker.clear_counts == {"world_1_stage_1": 2}
    assert app.save_schema.profiles[0].energy_spheres == {"world_1_stage_1": 3}

    reloaded = GameApp()
    assert reloaded.tracker.collected_mote_ids == app.tracker.collected_mote_ids
    assert reloaded.tracker.clear_counts == {"world_1_stage_1": 2}


def test_prototype_bridge_preserves_non_prefix_stable_mote_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    app = GameApp()
    app.tracker.collected_mote_ids = {"world_1_stage_1:mote:3"}

    app._flush_save()

    assert GameApp().tracker.collected_mote_ids == {"world_1_stage_1:mote:3"}
