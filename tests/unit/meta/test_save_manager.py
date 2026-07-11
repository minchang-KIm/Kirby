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


def test_reset_required_blocks_ordinary_save_until_explicit_confirmation() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = "bad backup"
    manager = SaveManager(storage, CATALOG, _now)
    loaded = manager.load()
    source_values = dict(storage.values)
    storage.events.clear()

    blocked = manager.save(_data("Implicit Reset"))

    assert loaded.notice is not None and loaded.notice.code == "reset_required"
    assert blocked.ok is False
    assert blocked.error_code == "reset_confirmation_required"
    assert storage.values == source_values
    assert not storage.events


def test_confirm_reset_verifies_all_writes_before_unlocking_ordinary_save() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = "bad backup"
    manager = SaveManager(storage, CATALOG, _now)
    assert manager.load().notice is not None
    storage.partial_writes.add("save_data.backup.json")

    failed = manager.confirm_reset(_data("Fresh Start"))
    storage.partial_writes.clear()
    blocked = manager.save(_data("Still Blocked"))

    assert failed.ok is False and failed.error_code == "storage_write_failed"
    assert blocked.ok is False
    assert blocked.error_code == "reset_confirmation_required"
    assert storage.values["save_data.backup.staging.json"] == save_data_to_json(
        _data("Fresh Start"), indent=2
    )

    retried = manager.confirm_reset(_data("Fresh Start"))

    assert retried.ok is True
    assert storage.values["save_data.json"] == save_data_to_json(
        _data("Fresh Start"), indent=2
    )
    assert storage.values["save_data.backup.json"] == save_data_to_json(
        _data("Fresh Start"), indent=2
    )
    assert manager.save(_data("Later Progress")).ok is True


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


@pytest.mark.parametrize(
    "unsupported_key",
    ["save_data.backup.json", "save_data.backup.staging.json"],
)
def test_primary_read_failure_stays_latched_when_recovery_copy_is_unsupported(
    unsupported_key: str,
) -> None:
    storage = MemoryStorage()
    unseen_raw = save_data_to_json(_data("Unseen"), indent=2)
    storage.values["save_data.json"] = unseen_raw
    storage.values[unsupported_key] = '{"save_version":3,"future_data":"keep"}'
    storage.fail_reads.add("save_data.json")
    manager = SaveManager(storage, CATALOG, _now)

    loaded = manager.load()
    storage.fail_reads.clear()
    storage.events.clear()
    blocked = manager.save(_data("Stale"))

    assert loaded.notice is not None and loaded.notice.code == "unsupported_version"
    assert blocked.ok is False and blocked.error_code == "recovery_required"
    assert storage.values["save_data.json"] == unseen_raw
    assert not storage.events


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


def test_corrupt_primary_and_canonical_backup_restore_verified_staging_fallback() -> None:
    storage = MemoryStorage()
    staged = _data("Staged Recovery")
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = "bad canonical backup"
    storage.values["save_data.backup.staging.json"] = save_data_to_json(staged, indent=2)

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "backup_restored"
    assert result.data == staged
    assert storage.values["save_data.json"] == save_data_to_json(staged, indent=2)
    assert storage.values["save_data.backup.staging.json"] == save_data_to_json(
        staged, indent=2
    )


def test_load_rechecks_primary_before_promoting_recovery_data() -> None:
    external = _data("External")
    external_raw = save_data_to_json(external, indent=2)

    class PrimaryChangesAfterBackupReadStorage(MemoryStorage):
        def read_text(self, key: str) -> str | None:
            value = super().read_text(key)
            if key == "save_data.backup.json":
                self.values["save_data.json"] = external_raw
            return value

    storage = PrimaryChangesAfterBackupReadStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = save_data_to_json(
        _data("Recovery"), indent=2
    )

    result = SaveManager(storage, CATALOG, _now).load()

    assert result.notice is not None and result.notice.code == "read_failed"
    assert result.notice.message_key == "save.primary_changed_during_recovery"
    assert storage.values["save_data.json"] == external_raw


def test_save_stages_previous_primary_then_rotates_backup_after_primary_verification() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    updated = _data("Updated")
    previous_raw = save_data_to_json(previous, indent=2)
    storage.values["save_data.json"] = previous_raw

    result = SaveManager(storage, CATALOG, _now).save(updated)

    assert result.ok is True and result.error_code is None
    assert storage.values["save_data.backup.json"] == previous_raw
    assert storage.values["save_data.json"] == save_data_to_json(updated, indent=2)
    staging_write = storage.events.index(("write", "save_data.backup.staging.json"))
    backup_write = storage.events.index(("write", "save_data.backup.json"))
    primary_write = storage.events.index(("write", "save_data.json"))
    assert staging_write < primary_write < backup_write


def test_partial_staging_write_preserves_primary_and_canonical_backup() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    older = _data("Older")
    previous_raw = save_data_to_json(previous, indent=2)
    older_raw = save_data_to_json(older, indent=2)
    storage.values["save_data.json"] = previous_raw
    storage.values["save_data.backup.json"] = older_raw
    storage.partial_writes.add("save_data.backup.staging.json")

    result = SaveManager(storage, CATALOG, _now).save(_data("Updated"))

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert storage.values["save_data.json"] == previous_raw
    assert storage.values["save_data.backup.json"] == older_raw
    assert ("write", "save_data.json") not in storage.events


def test_primary_write_failure_preserves_known_good_backup_and_memory_state() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    older = _data("Older")
    updated = _data("Updated")
    previous_raw = save_data_to_json(previous, indent=2)
    older_raw = save_data_to_json(older, indent=2)
    storage.values["save_data.json"] = previous_raw
    storage.values["save_data.backup.json"] = older_raw
    storage.partial_writes.add("save_data.json")

    result = SaveManager(storage, CATALOG, _now).save(updated)

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert storage.values["save_data.backup.staging.json"] == previous_raw
    assert storage.values["save_data.backup.json"] == older_raw
    assert updated.profiles[0].display_name == "Updated"


def test_post_commit_backup_rotation_failure_is_repaired_by_same_data_retry() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    older = _data("Older")
    updated = _data("Updated")
    previous_raw = save_data_to_json(previous, indent=2)
    older_raw = save_data_to_json(older, indent=2)
    updated_raw = save_data_to_json(updated, indent=2)
    storage.values["save_data.json"] = previous_raw
    storage.values["save_data.backup.json"] = older_raw
    storage.partial_writes.add("save_data.backup.json")
    manager = SaveManager(storage, CATALOG, _now)

    failed = manager.save(updated)

    assert failed.ok is False and failed.error_code == "storage_write_failed"
    assert storage.values["save_data.json"] == updated_raw
    assert storage.values["save_data.backup.json"] not in {older_raw, previous_raw}
    assert storage.values["save_data.backup.staging.json"] == previous_raw

    storage.partial_writes.clear()
    retried = manager.save(updated)

    assert retried.ok is True
    assert storage.values["save_data.json"] == updated_raw
    assert storage.values["save_data.backup.json"] == previous_raw
    assert "save_data.backup.staging.json" not in storage.values


@pytest.mark.parametrize("backup_raw", [None, "bad backup"])
def test_same_data_save_repairs_missing_or_corrupt_canonical_backup(
    backup_raw: str | None,
) -> None:
    storage = MemoryStorage()
    data = _data("Current")
    raw = save_data_to_json(data, indent=2)
    storage.values["save_data.json"] = raw
    if backup_raw is not None:
        storage.values["save_data.backup.json"] = backup_raw

    result = SaveManager(storage, CATALOG, _now).save(data)

    assert result.ok is True
    assert storage.values["save_data.json"] == raw
    assert storage.values["save_data.backup.json"] == raw
    assert "save_data.backup.staging.json" not in storage.values


def test_same_data_repair_records_fingerprint_before_later_save() -> None:
    storage = MemoryStorage()
    current = _data("Current")
    external = _data("External")
    current_raw = save_data_to_json(current, indent=2)
    external_raw = save_data_to_json(external, indent=2)
    storage.values["save_data.json"] = current_raw
    storage.fail_deletes = True
    manager = SaveManager(storage, CATALOG, _now)
    assert manager.save(current).ok is True
    storage.values["save_data.json"] = external_raw
    storage.events.clear()

    blocked = manager.save(_data("Stale"))

    assert blocked.ok is False and blocked.error_code == "recovery_required"
    assert storage.values["save_data.json"] == external_raw
    assert storage.values["save_data.backup.staging.json"] == current_raw
    assert not any(operation == "write" for operation, _ in storage.events)


def test_existing_valid_staging_copy_is_never_overwritten() -> None:
    storage = MemoryStorage()
    previous = _data("Previous")
    staged = _data("Earlier Recovery")
    staged_raw = save_data_to_json(staged, indent=2)
    storage.values["save_data.json"] = save_data_to_json(previous, indent=2)
    storage.values["save_data.backup.staging.json"] = staged_raw
    storage.fail_deletes = True

    result = SaveManager(storage, CATALOG, _now).save(_data("Updated"))

    assert result.ok is True
    assert storage.values["save_data.backup.staging.json"] == staged_raw
    assert storage.events.count(("write", "save_data.backup.staging.json")) == 0


def test_primary_read_failure_during_save_returns_failure_without_writing() -> None:
    storage = MemoryStorage()
    storage.values["save_data.json"] = save_data_to_json(_data("Existing"), indent=2)
    storage.fail_reads.add("save_data.json")
    manager = SaveManager(storage, CATALOG, _now)

    result = manager.save(SaveData())

    assert result.ok is False and result.error_code == "storage_write_failed"
    assert not any(operation == "write" for operation, _ in storage.events)

    storage.fail_reads.clear()
    storage.events.clear()
    blocked = manager.save(_data("Stale"))

    assert blocked.ok is False and blocked.error_code == "recovery_required"
    assert not storage.events

    assert manager.load().data == _data("Existing")
    assert manager.save(_data("Reconciled")).ok is True


def test_loaded_primary_fingerprint_blocks_stale_manager_overwrite() -> None:
    storage = MemoryStorage()
    initial = _data("Initial")
    external = _data("External")
    storage.values["save_data.json"] = save_data_to_json(initial, indent=2)
    manager = SaveManager(storage, CATALOG, _now)
    assert manager.load().data == initial
    external_raw = save_data_to_json(external, indent=2)
    storage.values["save_data.json"] = external_raw
    storage.events.clear()

    blocked = manager.save(_data("Stale Manager"))

    assert blocked.ok is False and blocked.error_code == "recovery_required"
    assert storage.values["save_data.json"] == external_raw
    assert not any(operation == "write" for operation, _ in storage.events)

    assert manager.load().data == external
    assert manager.save(_data("Reconciled")).ok is True


def test_same_data_repair_primary_read_failure_latches_reload_requirement() -> None:
    class FailSecondPrimaryReadStorage(MemoryStorage):
        def __init__(self) -> None:
            super().__init__()
            self.primary_reads = 0

        def read_text(self, key: str) -> str | None:
            if key == "save_data.json":
                self.primary_reads += 1
                if self.primary_reads == 2:
                    raise OSError("primary recheck unavailable")
            return super().read_text(key)

    storage = FailSecondPrimaryReadStorage()
    data = _data("Current")
    raw = save_data_to_json(data, indent=2)
    storage.values["save_data.json"] = raw
    storage.values["save_data.backup.json"] = raw
    manager = SaveManager(storage, CATALOG, _now)

    failed = manager.save(data)

    assert failed.ok is False and failed.error_code == "storage_write_failed"
    storage.events.clear()
    assert manager.save(_data("Stale")).error_code == "recovery_required"
    assert not storage.events


def test_reset_guard_primary_read_failure_also_latches_reload_requirement() -> None:
    class FailSecondPrimaryReadStorage(MemoryStorage):
        def __init__(self) -> None:
            super().__init__()
            self.primary_reads = 0

        def read_text(self, key: str) -> str | None:
            if key == "save_data.json":
                self.primary_reads += 1
                if self.primary_reads == 2:
                    raise OSError("reset guard read unavailable")
            return super().read_text(key)

    storage = FailSecondPrimaryReadStorage()
    storage.values["save_data.json"] = "bad primary"
    manager = SaveManager(storage, CATALOG, _now)

    failed = manager.save(_data("Fresh Start"))

    assert failed.ok is False and failed.error_code == "storage_write_failed"
    storage.events.clear()
    assert manager.save(_data("Stale")).error_code == "recovery_required"
    assert not storage.events


def test_confirm_reset_rechecks_each_source_before_overwriting_it() -> None:
    external = _data("External")
    external_raw = save_data_to_json(external, indent=2)

    class ConcurrentBackupStorage(MemoryStorage):
        def write_text(self, key: str, value: str) -> None:
            super().write_text(key, value)
            if key == "save_data.backup.staging.json":
                self.values["save_data.backup.json"] = external_raw

    storage = ConcurrentBackupStorage()
    storage.values["save_data.json"] = "bad primary"
    storage.values["save_data.backup.json"] = "bad backup"
    manager = SaveManager(storage, CATALOG, _now)
    assert manager.load().notice is not None

    result = manager.confirm_reset(_data("Fresh Start"))

    assert result.ok is False and result.error_code == "recovery_required"
    assert storage.values["save_data.backup.json"] == external_raw
    assert manager.save(_data("Still Blocked")).error_code == (
        "reset_confirmation_required"
    )


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
