from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from windsprig.content import load_campaign_catalog
from windsprig.meta.save_manager import SaveManager
from windsprig.meta.save_migrations import migration_catalog
from windsprig.meta.save_models import SaveData, SaveProfile, save_data_to_json
from windsprig.platform.native import NativeStorage
from windsprig.platform.web import PygbagBrowserBridge, WebStorage


@dataclass
class FakeLocalStorage:
    values: dict[str, str] = field(default_factory=dict)

    @property
    def length(self) -> int:
        return len(self.values)

    def getItem(self, key: str) -> str | None:
        return self.values.get(key)

    def setItem(self, key: str, value: str) -> None:
        self.values[key] = value

    def removeItem(self, key: str) -> None:
        self.values.pop(key, None)

    def key(self, index: int) -> str:
        return sorted(self.values)[index]


class FakeWindow:
    def __init__(self) -> None:
        self.localStorage = FakeLocalStorage()


def test_native_and_web_use_the_exact_same_canonical_v2_schema_without_cwd_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_dir = tmp_path / "launch"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    campaign = load_campaign_catalog(Path(__file__).parents[2] / "windsprig" / "content")
    catalog = migration_catalog(campaign)
    def now() -> datetime:
        return datetime(2026, 7, 11, 10, 30, tzinfo=UTC)
    data = SaveData(
        profiles=(
            SaveProfile(
                "profile_1",
                "Breeze",
                unlocked_nodes=frozenset({"world_1_node_1", "world_1_node_2"}),
                collected_mote_ids=frozenset({"world_1_stage_1:mote:3"}),
                best_times_ms={"world_1_stage_1": 9123},
                clear_counts={"world_1_stage_1": 2},
            ),
            SaveProfile("profile_2", "Sprig 2"),
            SaveProfile("profile_3", "Sprig 3"),
        )
    )
    native_storage = NativeStorage(tmp_path / "native" / "Windsprig")
    window = FakeWindow()
    web_storage = WebStorage(PygbagBrowserBridge(window))
    native_manager = SaveManager(native_storage, catalog, now)
    web_manager = SaveManager(web_storage, catalog, now)

    assert native_manager.save(data).ok is True
    assert web_manager.save(data).ok is True

    expected = save_data_to_json(data, indent=2)
    assert native_storage.read_text("save_data.json") == expected
    assert window.localStorage.values["windsprig:save_data.json"] == expected
    native_result = native_manager.load()
    web_result = web_manager.load()
    assert native_result.data == web_result.data == data
    assert native_result.notice is None and web_result.notice is None
    assert not (Path.cwd() / "save").exists()
