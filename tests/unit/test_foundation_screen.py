from __future__ import annotations

from types import SimpleNamespace

from windsprig.config import GameConfig
from windsprig.content import load_campaign_catalog
from windsprig.gameplay.abilities import create_default_registry
from windsprig.input.roster import ActiveRoster
from windsprig.meta import (
    SaveData,
    SaveLoadResult,
    SaveNotice,
    SaveWriteResult,
    migration_catalog,
)
from windsprig.screens.foundation import FoundationScreen


class RecordingSaveService:
    def __init__(self, load_results: list[SaveLoadResult]) -> None:
        self.load_results = load_results
        self.saved: list[SaveData] = []
        self.confirmed: list[SaveData] = []

    def load(self) -> SaveLoadResult:
        return self.load_results.pop(0)

    def save(self, data: SaveData) -> SaveWriteResult:
        self.saved.append(data)
        return SaveWriteResult(ok=True)

    def confirm_reset(self, data: SaveData) -> SaveWriteResult:
        self.confirmed.append(data)
        return SaveWriteResult(ok=True)


def make_foundation_screen(save_service: RecordingSaveService) -> FoundationScreen:
    config = GameConfig()
    catalog = load_campaign_catalog(config.content_dir)
    return FoundationScreen(
        config=config,
        roster=ActiveRoster(config.max_local_players),
        save_service=save_service,
        catalog=catalog,
        ability_registry=create_default_registry(config.content_dir),
        migration_catalog=migration_catalog(catalog),
    )


def test_stage_completion_never_auto_flushes_while_reset_is_unresolved() -> None:
    save_service = RecordingSaveService(
        [
            SaveLoadResult(
                SaveData(),
                SaveNotice("reset_required", "save.reset_required"),
            )
        ]
    )
    screen = make_foundation_screen(save_service)
    stage = screen.catalog.stages["world_1_stage_1"]
    screen.runtime = SimpleNamespace(
        stage=stage,
        world=SimpleNamespace(
            resources={"stage_cleared": True, "run_energy_spheres": 1},
            frame_index=10,
        ),
    )

    screen._on_stage_progress()

    assert screen.save_status == "reset_required"
    assert screen.tracker.clear_counts == {"world_1_stage_1": 1}
    assert save_service.saved == []


def test_reload_action_adopts_authoritative_data_before_saves_resume() -> None:
    authoritative = SaveData()
    save_service = RecordingSaveService(
        [
            SaveLoadResult(SaveData(), SaveNotice("read_failed", "save.read_failed")),
            SaveLoadResult(authoritative),
        ]
    )
    screen = make_foundation_screen(save_service)

    result = screen.reload_save()

    assert result.data == authoritative
    assert screen.save_data == authoritative
    assert screen.save_notice is None
    assert screen.save_status == "ready"


def test_reset_confirmation_remains_a_narrow_explicit_action() -> None:
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData(), SaveNotice("reset_required", "save.reset_required"))]
    )
    screen = make_foundation_screen(save_service)

    result = screen.confirm_save_reset()

    assert result.ok is True
    assert save_service.confirmed == [screen.save_data]
    assert screen.save_status == "saved"
