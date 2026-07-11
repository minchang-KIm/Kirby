"""Cross-platform save-v2 persistence with migration and verified recovery."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NoReturn, Protocol

from windsprig.platform.services import StorageService

from .save_migrations import SaveMigrationCatalog, migrate_v1
from .save_models import SaveData, save_data_from_dict, save_data_to_json

NoticeCode = Literal[
    "migrated_v1",
    "backup_restored",
    "backup_restore_failed",
    "quarantine_failed",
    "reset_required",
    "read_failed",
    "unsupported_version",
]
SaveWriteErrorCode = Literal[
    "storage_write_failed",
    "unsupported_version",
    "recovery_required",
]


@dataclass(frozen=True, slots=True)
class SaveNotice:
    """User-facing load outcome without raw save contents or adapter details."""

    code: NoticeCode
    message_key: str
    recovery_key: str | None = None


@dataclass(frozen=True, slots=True)
class SaveLoadResult:
    """Validated in-memory data plus an optional recovery-screen notice."""

    data: SaveData
    notice: SaveNotice | None = None


@dataclass(frozen=True, slots=True)
class SaveWriteResult:
    """Report whether the requested data was verified in persistent storage."""

    ok: bool
    error_code: SaveWriteErrorCode | None = None

    def __post_init__(self) -> None:
        if self.ok == (self.error_code is not None):
            raise ValueError("ok and error_code must describe exactly one outcome")


class SaveService(Protocol):
    """Persistence boundary that converts adapter failures into typed results."""

    def load(self) -> SaveLoadResult:
        """Load validated data without raising for storage or save corruption."""

        raise NotImplementedError

    def save(self, data: SaveData) -> SaveWriteResult:
        """Persist immutable data and report success only after verification."""

        raise NotImplementedError


class _UnsupportedSaveVersion(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


class SaveManager:
    """Own save migration, backup rotation, quarantine, and verified recovery."""

    def __init__(
        self,
        storage: StorageService,
        migration_catalog: SaveMigrationCatalog,
        now_utc: Callable[[], datetime],
        key: str = "save_data.json",
    ) -> None:
        self.storage = storage
        self.migration_catalog = migration_catalog
        self.now_utc = now_utc
        self.key = key
        self.backup_key = self._sibling_key(key, ".backup")
        self._write_blocked = False

    @staticmethod
    def _sibling_key(key: str, suffix: str) -> str:
        if key.endswith(".json"):
            return f"{key[:-5]}{suffix}.json"
        return f"{key}{suffix}"

    @staticmethod
    def _recovery_stem(key: str) -> str:
        leaf = key.rsplit("/", 1)[-1]
        return leaf[:-5] if leaf.endswith(".json") else leaf

    def _decode(self, raw: str) -> tuple[SaveData, bool]:
        if not isinstance(raw, str):
            raise ValueError("save JSON must be text")
        try:
            payload = json.loads(
                raw,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("save JSON could not be decoded") from exc
        if not isinstance(payload, dict):
            raise ValueError("save root must be an object")
        version = payload.get("save_version")
        if type(version) is not int:
            raise ValueError("save_version must be an integer")
        if version == 1:
            return migrate_v1(payload, self.migration_catalog), True
        if version == 2:
            return save_data_from_dict(payload), False
        raise _UnsupportedSaveVersion(f"unsupported save version: {version}")

    def _quarantine(self, raw: str, source_key: str) -> str | None:
        try:
            stamp = self.now_utc().strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            return None
        stem = self._recovery_stem(source_key)
        index = 0
        while True:
            suffix = "" if index == 0 else f".{index}"
            candidate = f"recovery/{stem}.{stamp}{suffix}.json"
            try:
                existing = self.storage.read_text(candidate)
            except Exception:
                return None
            if existing == raw:
                return candidate
            if existing is None:
                break
            index += 1
        try:
            self.storage.write_text(candidate, raw)
            verified = self.storage.read_text(candidate)
        except Exception:
            return None
        return candidate if verified == raw else None

    def _restore_primary(self, data: SaveData) -> bool:
        raw = save_data_to_json(data, indent=2)
        try:
            self.storage.write_text(self.key, raw)
            verified = self.storage.read_text(self.key)
            decoded, migrated = self._decode(verified) if verified is not None else (None, False)
        except Exception:
            return False
        return verified == raw and migrated is False and decoded == data

    def _load_backup(
        self,
        *,
        primary_state: Literal["missing", "corrupt", "read_failed"],
        recovery_key: str | None,
    ) -> SaveLoadResult:
        try:
            backup_raw = self.storage.read_text(self.backup_key)
        except Exception:
            return SaveLoadResult(
                SaveData(),
                SaveNotice("read_failed", "save.backup_read_failed", recovery_key),
            )
        if backup_raw is None:
            if primary_state == "missing":
                return SaveLoadResult(SaveData())
            code: NoticeCode = "read_failed" if primary_state == "read_failed" else "reset_required"
            message_key = "save.read_failed" if code == "read_failed" else "save.reset_required"
            return SaveLoadResult(SaveData(), SaveNotice(code, message_key, recovery_key))
        try:
            data, _ = self._decode(backup_raw)
        except _UnsupportedSaveVersion:
            return SaveLoadResult(
                SaveData(),
                SaveNotice("unsupported_version", "save.backup_unsupported_version", recovery_key),
            )
        except Exception:
            if primary_state == "read_failed":
                return SaveLoadResult(
                    SaveData(),
                    SaveNotice("read_failed", "save.primary_read_failed", recovery_key),
                )
            return SaveLoadResult(
                SaveData(),
                SaveNotice("reset_required", "save.reset_required", recovery_key),
            )

        if primary_state == "read_failed":
            # An unreadable primary may still be valid, so recovery stays memory-only.
            return SaveLoadResult(
                data,
                SaveNotice("read_failed", "save.primary_read_failed", recovery_key),
            )
        if primary_state == "corrupt" and recovery_key is None:
            # Do not destroy the corrupt source unless its forensic copy was verified.
            return SaveLoadResult(
                data,
                SaveNotice("quarantine_failed", "save.quarantine_failed"),
            )
        if self._restore_primary(data):
            return SaveLoadResult(
                data,
                SaveNotice("backup_restored", "save.backup_restored", recovery_key),
            )
        return SaveLoadResult(
            data,
            SaveNotice("backup_restore_failed", "save.backup_restore_failed", recovery_key),
        )

    def load(self) -> SaveLoadResult:
        """Load current data, migrating v1 or recovering verified backup data."""

        # Storage and decoder failures end at this service boundary as typed UI state.
        try:
            raw = self.storage.read_text(self.key)
        except Exception:
            result = self._load_backup(primary_state="read_failed", recovery_key=None)
            return self._record_load(result)
        if raw is None:
            return self._record_load(
                self._load_backup(primary_state="missing", recovery_key=None)
            )
        try:
            data, migrated = self._decode(raw)
        except _UnsupportedSaveVersion:
            return self._record_load(
                SaveLoadResult(
                    SaveData(),
                    SaveNotice("unsupported_version", "save.unsupported_version"),
                )
            )
        except Exception:
            recovery_key = self._quarantine(raw, self.key)
            return self._record_load(
                self._load_backup(primary_state="corrupt", recovery_key=recovery_key)
            )
        if migrated:
            return self._record_load(
                SaveLoadResult(data, SaveNotice("migrated_v1", "save.migrated_v1"))
            )
        return self._record_load(SaveLoadResult(data))

    def _record_load(self, result: SaveLoadResult) -> SaveLoadResult:
        self._write_blocked = result.notice is not None and result.notice.code == "read_failed"
        return result

    def _validated_backup_before_primary(self, current: str) -> SaveWriteErrorCode | None:
        try:
            previous_backup = self.storage.read_text(self.backup_key)
        except Exception:
            return "storage_write_failed"
        if previous_backup is not None:
            try:
                self._decode(previous_backup)
            except _UnsupportedSaveVersion:
                return "unsupported_version"
            except Exception:
                if self._quarantine(previous_backup, self.backup_key) is None:
                    return "storage_write_failed"
        try:
            self.storage.write_text(self.backup_key, current)
            verified = self.storage.read_text(self.backup_key)
            if verified != current:
                return "storage_write_failed"
            self._decode(verified)
        except Exception:
            return "storage_write_failed"
        return None

    def _write_primary(self, raw: str, data: SaveData) -> bool:
        try:
            self.storage.write_text(self.key, raw)
            verified = self.storage.read_text(self.key)
            if verified != raw:
                return False
            decoded, migrated = self._decode(verified)
        except Exception:
            return False
        return migrated is False and decoded == data

    def _backup_state_allows_new_primary(
        self,
        *,
        require_recovery_for_valid: bool,
    ) -> SaveWriteErrorCode | None:
        try:
            backup_raw = self.storage.read_text(self.backup_key)
        except Exception:
            return "storage_write_failed"
        if backup_raw is None:
            return None
        try:
            self._decode(backup_raw)
        except _UnsupportedSaveVersion:
            return "unsupported_version"
        except Exception:
            if self._quarantine(backup_raw, self.backup_key) is None:
                return "storage_write_failed"
        else:
            if require_recovery_for_valid:
                return "recovery_required"
        return None

    def save(self, data: SaveData) -> SaveWriteResult:
        """Persist data while retaining a verified pre-write recovery point."""

        # Ambiguous loads require reconciliation before stale session data may replace disk state.
        if self._write_blocked:
            return SaveWriteResult(ok=False, error_code="recovery_required")
        raw = save_data_to_json(data, indent=2)
        try:
            current = self.storage.read_text(self.key)
        except Exception:
            # Reads gate writes because an unseen valid save must never be overwritten.
            return SaveWriteResult(ok=False, error_code="storage_write_failed")

        if current is None:
            backup_error = self._backup_state_allows_new_primary(
                require_recovery_for_valid=True,
            )
            if backup_error is not None:
                return SaveWriteResult(ok=False, error_code=backup_error)
        else:
            try:
                current_data, current_migrated = self._decode(current)
            except _UnsupportedSaveVersion:
                return SaveWriteResult(ok=False, error_code="unsupported_version")
            except Exception:
                if self._quarantine(current, self.key) is None:
                    return SaveWriteResult(ok=False, error_code="storage_write_failed")
                backup_error = self._backup_state_allows_new_primary(
                    require_recovery_for_valid=False,
                )
                if backup_error is not None:
                    return SaveWriteResult(ok=False, error_code=backup_error)
            else:
                if current_migrated is False and current == raw and current_data == data:
                    return SaveWriteResult(ok=True)
                # Backup first: a non-atomic primary failure must leave one verified good copy.
                backup_error = self._validated_backup_before_primary(current)
                if backup_error is not None:
                    return SaveWriteResult(ok=False, error_code=backup_error)

        if not self._write_primary(raw, data):
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        return SaveWriteResult(ok=True)
