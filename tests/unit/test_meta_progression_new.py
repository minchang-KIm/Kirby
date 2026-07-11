from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from windsprig.content.loader import load_campaign_catalog
from windsprig.meta import CompletionTracker, SaveData, SaveManager, UnlockRules, migration_catalog
from windsprig.platform.native import NativeStorage


def test_unlock_rules_progression() -> None:
    catalog = load_campaign_catalog(Path("windsprig/content"))
    rules = UnlockRules(catalog)
    tracker = CompletionTracker()
    unlocked_worlds = {"world_1"}

    assert rules.is_node_unlocked("world_1_node_1", tracker, unlocked_worlds)
    assert not rules.is_node_unlocked("world_1_node_2", tracker, unlocked_worlds)

    tracker.mark_stage_clear("world_1_node_1", "world_1_stage_1", 10000)
    assert rules.is_node_unlocked("world_1_node_2", tracker, unlocked_worlds)

    tracker.mark_stage_clear("world_1_node_2", "world_1_stage_2", 9000)
    tracker.mark_stage_clear("world_1_node_3", "world_1_stage_3", 8000)
    tracker.mark_stage_clear("world_1_node_4", "world_1_stage_4", 7000)
    tracker.mark_stage_clear("world_1_node_5", "world_1_stage_5", 6000)
    unlocked_worlds = rules.apply_stage_rewards("world_1_node_5", unlocked_worlds)
    assert "world_2" in unlocked_worlds


def test_save_v2_roundtrip_uses_storage_service(tmp_path: Path) -> None:
    catalog = load_campaign_catalog(Path("windsprig/content"))
    manager = SaveManager(
        NativeStorage(tmp_path / "Windsprig"),
        migration_catalog(catalog),
        lambda: datetime(2026, 7, 11, tzinfo=UTC),
    )
    data = SaveData()
    profile = replace(
        data.profiles[0],
        unlocked_nodes=frozenset({"world_1_node_1", "world_1_node_2"}),
    )
    updated = replace(data, profiles=(profile, data.profiles[1], data.profiles[2]))

    assert manager.save(updated).ok is True
    assert manager.load().data == updated
