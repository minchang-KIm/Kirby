from __future__ import annotations

from pathlib import Path

from kirby_clone.content.loader import load_campaign_catalog
from kirby_clone.meta import CompletionTracker, SaveManager, SaveSchema, UnlockRules


def test_unlock_rules_progression() -> None:
    catalog = load_campaign_catalog(Path("kirby_clone/content"))
    rules = UnlockRules(catalog)
    tracker = CompletionTracker()
    unlocked_worlds = {"world_1"}

    assert rules.is_node_unlocked("world_1_node_1", tracker, unlocked_worlds)
    assert not rules.is_node_unlocked("world_1_node_2", tracker, unlocked_worlds)

    tracker.mark_stage_clear("world_1_node_1", 10000)
    assert rules.is_node_unlocked("world_1_node_2", tracker, unlocked_worlds)

    tracker.mark_stage_clear("world_1_node_2", 9000)
    tracker.mark_stage_clear("world_1_node_3", 8000)
    tracker.mark_stage_clear("world_1_node_4", 7000)
    tracker.mark_stage_clear("world_1_node_5", 6000)
    unlocked_worlds = rules.apply_stage_rewards("world_1_node_5", unlocked_worlds)
    assert "world_2" in unlocked_worlds


def test_save_schema_roundtrip(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path / "save_data.json")
    schema = SaveSchema()
    schema.profiles[0].cleared_nodes = {"world_1_node_1"}
    manager.save(schema)
    loaded = manager.load()
    assert "world_1_node_1" in loaded.profiles[0].cleared_nodes
