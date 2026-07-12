from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.meta.save_models import save_data_from_json
from windsprig.platform.native import create_native_services
from windsprig.platform.services import PlatformServices, StorageCapabilities


class ToggleStorage:
    capabilities = StorageCapabilities(persistent=True, atomic_write=False, backup=True)

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_writes = False

    def read_text(self, key: str) -> str | None:
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        if self.fail_writes:
            raise OSError("storage unavailable")
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(sorted(key for key in self.values if key.startswith(prefix)))


def _services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage: ToggleStorage,
) -> PlatformServices:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return replace(create_native_services(GameConfig()), storage=storage)


def _completed_runtime(
    stage: object,
    *,
    frame_index: int,
    mote_ids: set[str],
) -> SimpleNamespace:
    return SimpleNamespace(
        stage=stage,
        result=None,
        player_entities={1: 1001},
        world=SimpleNamespace(
            resources={
                "run_energy_spheres": 99,
                "collected_mote_ids": mote_ids,
                "discovered_ability_ids": set(),
                "deaths_by_slot": {1: 0},
            },
            frame_index=frame_index,
        ),
        snapshot=lambda: SimpleNamespace(outcome=StageOutcome.COMPLETED),
    )


def test_runtime_progress_is_saved_as_immutable_v2_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    services = _services(tmp_path, monkeypatch, storage)
    app = GameApp(services=services)
    stage = app.catalog.stages["world_1_stage_1"]
    mote_ids = {
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
        "world_1_stage_1:mote:3",
    }
    app.runtime = _completed_runtime(
        stage,
        frame_index=10,
        mote_ids=mote_ids,
    )

    app._on_stage_progress()
    app.runtime = _completed_runtime(
        stage,
        frame_index=12,
        mote_ids=mote_ids,
    )
    app._on_stage_progress()

    assert app.tracker.collected_mote_ids == {
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
        "world_1_stage_1:mote:3",
    }
    assert app.tracker.best_times_ms == {"world_1_stage_1": 160}
    assert app.tracker.clear_counts == {"world_1_stage_1": 2}
    assert app.save_data.profiles[0].collected_mote_ids == frozenset(
        {
            "world_1_stage_1:mote:1",
            "world_1_stage_1:mote:2",
            "world_1_stage_1:mote:3",
        }
    )
    assert app.save_data.profiles[0].clear_counts == {"world_1_stage_1": 2}
    assert app.save_status == "saved"

    reloaded = GameApp(services=services)
    assert reloaded.tracker.collected_mote_ids == app.tracker.collected_mote_ids
    assert reloaded.tracker.clear_counts == {"world_1_stage_1": 2}
    assert reloaded.tracker.cleared_nodes == {"world_1_node_1"}


def test_v2_flush_preserves_non_prefix_stable_mote_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    services = _services(tmp_path, monkeypatch, storage)
    app = GameApp(services=services)
    app.tracker.collected_mote_ids = {"world_1_stage_1:mote:3"}

    app._flush_save()

    assert GameApp(services=services).tracker.collected_mote_ids == {
        "world_1_stage_1:mote:3"
    }


def test_completed_runtime_is_recorded_once_but_new_run_increments_replay_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    app = GameApp(services=_services(tmp_path, monkeypatch, storage))
    stage = app.catalog.stages["world_1_stage_1"]
    completed_runtime = _completed_runtime(
        stage,
        frame_index=10,
        mote_ids={"world_1_stage_1:mote:1"},
    )
    app.runtime = completed_runtime

    app._on_stage_progress()
    app._on_stage_progress()

    assert app.tracker.clear_counts == {"world_1_stage_1": 1}

    app.runtime = _completed_runtime(
        stage,
        frame_index=10,
        mote_ids={"world_1_stage_1:mote:1"},
    )
    app._on_stage_progress()

    assert app.tracker.clear_counts == {"world_1_stage_1": 2}


def test_failed_flush_keeps_updated_memory_and_requires_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    app = GameApp(services=_services(tmp_path, monkeypatch, storage))
    app.tracker.collected_mote_ids = {"world_1_stage_1:mote:3"}
    storage.fail_writes = True

    app._flush_save()

    assert app.save_status == "retry_required"
    assert app.save_write_result is not None and app.save_write_result.ok is False
    assert app.save_data.profiles[0].collected_mote_ids == frozenset(
        {"world_1_stage_1:mote:3"}
    )


def test_migrated_v1_is_rewritten_immediately_and_result_is_exposed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    storage.values["save_data.json"] = (
        '{"save_version":1,"profiles":[{"profile_name":"Legacy",'
        '"cleared_nodes":["world_1_node_1"],'
        '"energy_spheres":{"world_1_stage_1":1}}]}'
    )

    app = GameApp(services=_services(tmp_path, monkeypatch, storage))

    assert app.save_notice is not None and app.save_notice.code == "migrated_v1"
    assert app.save_write_result is not None and app.save_write_result.ok is True
    assert app.save_status == "saved"
    assert save_data_from_json(storage.values["save_data.json"]) == app.save_data


def test_migrated_v1_rewrite_failure_keeps_migrated_memory_and_never_reports_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    storage.values["save_data.json"] = (
        '{"save_version":1,"profiles":[{"profile_name":"Legacy",'
        '"energy_spheres":{"world_1_stage_1":1}}]}'
    )
    storage.fail_writes = True

    app = GameApp(services=_services(tmp_path, monkeypatch, storage))

    assert app.save_notice is not None and app.save_notice.code == "migrated_v1"
    assert app.save_write_result is not None and app.save_write_result.ok is False
    assert app.save_data.prototype_imported is True
    assert app.save_data.profiles[0].display_name == "Legacy"
    assert app.save_status == "retry_required"


def test_reset_required_app_flush_stays_locked_and_preserves_corrupt_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = "bad backup"
    app = GameApp(services=_services(tmp_path, monkeypatch, storage))
    sources = {
        "save_data.json": storage.values["save_data.json"],
        "save_data.backup.json": storage.values["save_data.backup.json"],
    }

    app._flush_save()

    assert app.save_notice is not None and app.save_notice.code == "reset_required"
    assert app.save_status == "reset_required"
    assert app.save_write_result is not None
    assert app.save_write_result.error_code == "reset_confirmation_required"
    assert storage.values["save_data.json"] == sources["save_data.json"]
    assert storage.values["save_data.backup.json"] == sources["save_data.backup.json"]


def test_app_exposes_narrow_verified_reset_confirmation_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = ToggleStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = "bad backup"
    app = GameApp(services=_services(tmp_path, monkeypatch, storage))

    result = app.confirm_save_reset()

    assert result.ok is True
    assert app.save_status == "saved"
    assert app.save_write_result == result
    assert save_data_from_json(storage.values["save_data.json"]) == app.save_data
    assert save_data_from_json(storage.values["save_data.backup.json"]) == app.save_data


def test_default_app_save_uses_platform_storage_and_creates_no_cwd_save_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = GameApp()

    app._flush_save()

    assert app.save_status == "saved"
    assert not (tmp_path / "save").exists()
