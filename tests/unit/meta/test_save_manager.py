from __future__ import annotations

from datetime import UTC, datetime

import pytest

from windsprig.meta.save_manager import SaveManager
from windsprig.meta.save_migrations import SaveMigrationCatalog
from windsprig.meta.save_models import SaveData, SaveProfile, save_data_to_json
from windsprig.platform.services import StorageCapabilities


class MemoryStorage:
    capabilities = StorageCapabilities(persistent=True, atomic_write=False, backup=True)

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_reads: set[str] = set()
        self.fail_writes: set[str] = set()
        self.fail_write_prefixes: set[str] = set()
        self.partial_writes: set[str] = set()
        self.discard_writes: set[str] = set()
        self.fail_deletes = False
        self.fail_keys = False
        self.events: list[tuple[str, str]] = []

    def read_text(self, key: str) -> str | None:
        self.events.append(("read", key))
        if key in self.fail_reads:
            raise OSError("read unavailable")
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        self.events.append(("write", key))
        if key in self.partial_writes:
            self.values[key] = value[: max(1, len(value) // 2)]
            raise OSError("non-atomic write failed")
        if key in self.fail_writes or any(key.startswith(prefix) for prefix in self.fail_write_prefixes):
            raise OSError("write unavailable")
        if key not in self.discard_writes:
            self.values[key] = value

    def delete(self, key: str) -> None:
        self.events.append(("delete", key))
        if self.fail_deletes:
            raise OSError("delete unavailable")
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        self.events.append(("keys", prefix))
        if self.fail_keys:
            raise OSError("keys unavailable")
        return tuple(sorted(key for key in self.values if key.startswith(prefix)))


CATALOG = SaveMigrationCatalog(
    mote_ids_by_stage={"world_1_stage_1": ("world_1_stage_1:mote:1",)},
    next_node_by_node={"world_1_node_1": "world_1_node_2"},
    stage_id_by_node={
        "world_1_node_1": "world_1_stage_1",
        "world_1_node_2": "world_1_stage_1",
    },
)

def _now() -> datetime:
    return datetime(2026, 7, 11, 10, 30, tzinfo=UTC)


def _data(name: str) -> SaveData:
    return SaveData(
        profiles=(
            SaveProfile("profile_1", name),
            SaveProfile("profile_2", "Sprig 2"),
            SaveProfile("profile_3", "Sprig 3"),
        )
    )


def _legacy_save() -> str:
    return (
        '{"save_version":1,"profiles":[{"profile_name":"Legacy",'
        '"cleared_nodes":["world_1_node_1"],'
        '"energy_spheres":{"world_1_stage_1":1}}]}'
    )


def test_v1_load_uses_stage_identity_catalog_and_reports_pending_rewrite() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = _legacy_save()

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "migrated_v1"
    assert result.data.prototype_imported is True
    assert result.data.profiles[0].display_name == "Legacy"
    assert result.data.profiles[0].best_times_ms == {}
    assert result.data.profiles[0].clear_counts == {"world_1_stage_1": 1}
    assert storage.values["save_data.json"] == _legacy_save()


def test_corrupt_primary_is_quarantined_and_backup_is_restored() -> None:
    storage = MemoryStorage()
    backup = _data("Known Good")
    storage.values["save_data.json"] = "{broken"
    storage.values["save_data.backup.json"] = save_data_to_json(backup)

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "backup_restored"
    assert result.notice.recovery_key == "recovery/save_data.20260711T103000Z.json"
    assert storage.values[result.notice.recovery_key] == "{broken"
    assert storage.values["save_data.json"] == save_data_to_json(backup, indent=2)
    assert result.data == backup


def test_duplicate_recovery_timestamp_uses_next_deterministic_key() -> None:
    storage = MemoryStorage()
    original_recovery = "first corrupt save"
    storage.values["recovery/save_data.20260711T103000Z.json"] = original_recovery
    storage.values["save_data.json"] = "second corrupt save"
    storage.values["save_data.backup.json"] = save_data_to_json(SaveData())

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None
    assert result.notice.recovery_key == "recovery/save_data.20260711T103000Z.1.json"
    assert storage.values["recovery/save_data.20260711T103000Z.json"] == original_recovery
    assert storage.values[result.notice.recovery_key] == "second corrupt save"


@pytest.mark.parametrize("invalid_primary", ["[]", '{"save_version":true}'])
def test_invalid_primary_and_backup_offer_safe_new_data(
    invalid_primary: str,
) -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = invalid_primary
    storage.values["save_data.backup.json"] = "not-json"

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "reset_required"
    assert result.data == SaveData()


def test_unsupported_primary_is_preserved_without_downgrade_or_reset() -> None:
    storage = MemoryStorage()
    unsupported = '{"save_version":3,"future_data":"keep me"}'
    storage.values["save_data.json"] = unsupported
    storage.values["save_data.backup.json"] = save_data_to_json(_data("Older Backup"))

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "unsupported_version"
    assert result.notice.message_key == "save.unsupported_version"
    assert result.data == SaveData()
    assert storage.values["save_data.json"] == unsupported
    assert not any(key.startswith("recovery/") for key in storage.values)


def test_primary_read_failure_is_an_explicit_notice() -> None:
    storage = MemoryStorage()
    storage.fail_reads.add("save_data.json")

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "read_failed"
    assert result.notice.message_key == "save.read_failed"
    assert result.data == SaveData()


def test_primary_read_failure_can_still_recover_a_known_good_backup() -> None:
    storage = MemoryStorage()
    backup = _data("Backup")
    storage.fail_reads.add("save_data.json")
    storage.values["save_data.backup.json"] = save_data_to_json(backup)

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "read_failed"
    assert result.notice.message_key == "save.primary_read_failed"
    assert result.data == backup
    assert ("write", "save_data.json") not in storage.events


def test_read_failed_load_blocks_stale_save_until_a_successful_reload() -> None:
    storage = MemoryStorage()
    unseen_primary = _data("Unseen Primary")
    primary_raw = save_data_to_json(unseen_primary, indent=2)
    backup_raw = save_data_to_json(_data("Older Backup"), indent=2)
    storage.values["save_data.json"] = primary_raw
    storage.values["save_data.backup.json"] = backup_raw
    storage.fail_reads.add("save_data.json")
    manager = SaveManager(storage, CATALOG, _now)
    loaded = manager.load()
    storage.fail_reads.clear()
    storage.events.clear()

    blocked = manager.save(_data("Stale Session"))

    assert loaded.notice is not None and loaded.notice.code == "read_failed"
    assert blocked.ok is False and blocked.error_code == "recovery_required"
    assert storage.values["save_data.json"] == primary_raw
    assert storage.values["save_data.backup.json"] == backup_raw
    assert not storage.events

    reloaded = manager.load()
    assert reloaded.data == unseen_primary
    assert manager.save(_data("Reconciled")).ok is True


def test_quarantine_write_failure_loads_backup_without_destroying_primary() -> None:
    storage = MemoryStorage()
    backup = _data("Backup")
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = save_data_to_json(backup)
    storage.fail_write_prefixes.add("recovery/")

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "quarantine_failed"
    assert result.notice.recovery_key is None
    assert result.data == backup
    assert storage.values["save_data.json"] == "bad primary"


def test_delete_failure_is_irrelevant_to_verified_recovery() -> None:
    storage = MemoryStorage()
    backup = _data("Backup")
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = save_data_to_json(backup)
    storage.fail_deletes = True

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "backup_restored"
    assert result.data == backup
    assert not any(operation == "delete" for operation, _ in storage.events)


def test_recovery_does_not_depend_on_key_listing() -> None:
    storage = MemoryStorage()
    backup = _data("Backup")
    recovery_key = "recovery/save_data.20260711T103000Z.json"
    storage.values[recovery_key] = "existing forensic copy"
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = save_data_to_json(backup)
    storage.fail_keys = True

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "backup_restored"
    assert result.notice.recovery_key == "recovery/save_data.20260711T103000Z.1.json"
    assert storage.values[recovery_key] == "existing forensic copy"


def test_backup_read_failure_is_an_explicit_notice_after_quarantine() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.fail_reads.add("save_data.backup.json")

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "read_failed"
    assert result.notice.message_key == "save.backup_read_failed"
    assert result.notice.recovery_key is not None
    assert result.data == SaveData()


def test_failed_non_atomic_backup_restore_keeps_backup_data_in_memory() -> None:
    storage = MemoryStorage()
    backup = _data("Backup")
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = save_data_to_json(backup)
    storage.partial_writes.add("save_data.json")

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "backup_restore_failed"
    assert result.notice.message_key == "save.backup_restore_failed"
    assert result.data == backup
    assert storage.values["save_data.backup.json"] == save_data_to_json(backup)


def test_save_preserves_previous_primary_as_backup_before_writing_new_primary() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    updated = _data("Updated")
    previous_raw = save_data_to_json(previous, indent=2)
    storage.values["save_data.json"] = previous_raw

    result = SaveManager(storage, CATALOG, _now).save(updated)

    assert result.ok is True and result.error_code is None
    assert storage.values["save_data.backup.json"] == previous_raw
    assert storage.values["save_data.json"] == save_data_to_json(updated, indent=2)
    backup_write = storage.events.index(("write", "save_data.backup.json"))
    primary_write = storage.events.index(("write", "save_data.json"))
    assert backup_write < primary_write


def test_backup_write_failure_aborts_before_primary_changes() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    previous_raw = save_data_to_json(previous, indent=2)
    storage.values["save_data.json"] = previous_raw
    storage.fail_writes.add("save_data.backup.json")

    result = SaveManager(storage, CATALOG, _now).save(_data("Updated"))

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert storage.values["save_data.json"] == previous_raw
    assert ("write", "save_data.json") not in storage.events


def test_primary_write_failure_preserves_known_good_backup_and_memory_state() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    updated = _data("Updated")
    previous_raw = save_data_to_json(previous, indent=2)
    storage.values["save_data.json"] = previous_raw
    storage.partial_writes.add("save_data.json")

    result = SaveManager(storage, CATALOG, _now).save(updated)

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert storage.values["save_data.backup.json"] == previous_raw
    assert updated.profiles[0].display_name == "Updated"


def test_primary_read_failure_during_save_returns_failure_without_writing() -> None:
    storage = MemoryStorage()
    storage.fail_reads.add("save_data.json")

    result = SaveManager(storage, CATALOG, _now).save(SaveData())

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert not any(operation == "write" for operation, _ in storage.events)


def test_silent_primary_write_loss_is_not_reported_as_saved() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    storage.values["save_data.json"] = save_data_to_json(previous, indent=2)
    storage.discard_writes.add("save_data.json")

    result = SaveManager(storage, CATALOG, _now).save(_data("Updated"))

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert storage.values["save_data.json"] == save_data_to_json(previous, indent=2)


def test_saving_over_corrupt_primary_does_not_replace_existing_good_backup() -> None:
    storage = MemoryStorage()
    backup = _data("Backup")
    updated = _data("Updated")
    backup_raw = save_data_to_json(backup, indent=2)
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = backup_raw

    result = SaveManager(storage, CATALOG, _now).save(updated)

    assert result.ok is True
    assert storage.values["save_data.backup.json"] == backup_raw
    assert storage.values["save_data.json"] == save_data_to_json(updated, indent=2)


def test_unsupported_primary_blocks_save_without_overwriting_future_data() -> None:
    storage = MemoryStorage()
    unsupported = '{"save_version":3,"future_data":"keep me"}'
    storage.values["save_data.json"] = unsupported

    result = SaveManager(storage, CATALOG, _now).save(_data("Updated"))

    assert result.ok is False and result.error_code == "unsupported_version"
    assert storage.values["save_data.json"] == unsupported
    assert not any(operation == "write" for operation, _ in storage.events)


def test_backup_read_failure_aborts_save_before_primary_changes() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    previous_raw = save_data_to_json(previous, indent=2)
    storage.values["save_data.json"] = previous_raw
    storage.values["save_data.backup.json"] = save_data_to_json(_data("Older"), indent=2)
    storage.fail_reads.add("save_data.backup.json")

    result = SaveManager(storage, CATALOG, _now).save(_data("Updated"))

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert storage.values["save_data.json"] == previous_raw
    assert not any(operation == "write" for operation, _ in storage.events)


def test_missing_primary_with_valid_backup_requires_recovery_before_new_save() -> None:
    storage = MemoryStorage()
    backup_raw = save_data_to_json(_data("Recover Me"), indent=2)
    storage.values["save_data.backup.json"] = backup_raw

    result = SaveManager(storage, CATALOG, _now).save(_data("New Session"))

    assert result.ok is False and result.error_code == "recovery_required"
    assert "save_data.json" not in storage.values
    assert storage.values["save_data.backup.json"] == backup_raw
