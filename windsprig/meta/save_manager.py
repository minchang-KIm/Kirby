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
    "reset_confirmation_required",
    "reset_not_required",
]
_CopyState = Literal["missing", "valid", "corrupt", "read_failed", "unsupported"]
_RestoreState = Literal["restored", "changed", "failed"]
_WriteBlock = Literal["read_failed", "recovery_required", "reset_required"]


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

    def confirm_reset(self, data: SaveData) -> SaveWriteResult:
        """Replace unrecoverable sources only after explicit user confirmation."""

        raise NotImplementedError


class _UnsupportedSaveVersion(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _StoredCopy:
    state: _CopyState
    raw: str | None = None
    data: SaveData | None = None


@dataclass(frozen=True, slots=True)
class _Fingerprints:
    primary: str | None
    backup: str | None
    staging: str | None


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
        self.staging_key = self._sibling_key(key, ".backup.staging")
        self._write_block: _WriteBlock | None = None
        self._has_primary_fingerprint = False
        self._primary_fingerprint: str | None = None
        self._reset_fingerprints: _Fingerprints | None = None
        self._pending_reset_raw: str | None = None

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

    def _read_copy(self, key: str) -> _StoredCopy:
        try:
            raw = self.storage.read_text(key)
        except Exception:
            return _StoredCopy("read_failed")
        if raw is None:
            return _StoredCopy("missing")
        try:
            data, _ = self._decode(raw)
        except _UnsupportedSaveVersion:
            return _StoredCopy("unsupported", raw)
        except Exception:
            return _StoredCopy("corrupt", raw)
        return _StoredCopy("valid", raw, data)

    def _read_fingerprints(self) -> _Fingerprints:
        return _Fingerprints(
            primary=self.storage.read_text(self.key),
            backup=self.storage.read_text(self.backup_key),
            staging=self.storage.read_text(self.staging_key),
        )

    def _remember_primary(self, raw: str | None) -> None:
        self._has_primary_fingerprint = True
        self._primary_fingerprint = raw

    def _record_load(
        self,
        result: SaveLoadResult,
        *,
        primary_raw: str | None = None,
        fingerprint_known: bool,
        force_read_block: bool = False,
    ) -> SaveLoadResult:
        self._reset_fingerprints = None
        self._pending_reset_raw = None
        notice_code = result.notice.code if result.notice is not None else None
        if force_read_block or notice_code == "read_failed":
            self._write_block = "read_failed"
        elif notice_code in {"backup_restore_failed", "quarantine_failed"}:
            self._write_block = "recovery_required"
        else:
            self._write_block = None
        if fingerprint_known:
            self._remember_primary(primary_raw)
        else:
            self._has_primary_fingerprint = False
            self._primary_fingerprint = None
        return result

    def _record_reset_required(
        self,
        *,
        primary_raw: str | None,
        recovery_key: str | None,
    ) -> SaveLoadResult:
        try:
            fingerprints = self._read_fingerprints()
        except Exception:
            return self._record_load(
                SaveLoadResult(
                    SaveData(),
                    SaveNotice("read_failed", "save.recovery_source_read_failed", recovery_key),
                ),
                fingerprint_known=False,
            )
        if fingerprints.primary != primary_raw:
            return self._record_load(
                SaveLoadResult(
                    SaveData(),
                    SaveNotice("read_failed", "save.primary_changed_during_recovery", recovery_key),
                ),
                fingerprint_known=False,
            )
        for raw in (fingerprints.backup, fingerprints.staging):
            if raw is None:
                continue
            try:
                self._decode(raw)
            except _UnsupportedSaveVersion:
                return self._record_load(
                    SaveLoadResult(
                        SaveData(),
                        SaveNotice(
                            "unsupported_version",
                            "save.backup_unsupported_version",
                            recovery_key,
                        ),
                    ),
                    primary_raw=primary_raw,
                    fingerprint_known=True,
                )
            except Exception:
                continue
            return self._record_load(
                SaveLoadResult(
                    SaveData(),
                    SaveNotice("read_failed", "save.recovery_sources_changed", recovery_key),
                ),
                fingerprint_known=False,
            )
        self._write_block = "reset_required"
        self._reset_fingerprints = fingerprints
        self._pending_reset_raw = None
        self._remember_primary(primary_raw)
        return SaveLoadResult(
            SaveData(),
            SaveNotice("reset_required", "save.reset_required", recovery_key),
        )

    def _restore_primary(
        self,
        data: SaveData,
        *,
        expected_primary: str | None,
    ) -> tuple[_RestoreState, str | None]:
        raw = save_data_to_json(data, indent=2)
        try:
            current = self.storage.read_text(self.key)
            if current != expected_primary:
                return "changed", current
            self.storage.write_text(self.key, raw)
            verified = self.storage.read_text(self.key)
            if verified != raw:
                return "failed", verified
            decoded, migrated = self._decode(verified)
        except Exception:
            return "failed", None
        if migrated or decoded != data:
            return "failed", verified
        return "restored", verified

    def _load_backup(
        self,
        *,
        primary_state: Literal["missing", "corrupt", "read_failed"],
        primary_raw: str | None,
        recovery_key: str | None,
    ) -> SaveLoadResult:
        canonical = self._read_copy(self.backup_key)
        if canonical.state == "read_failed":
            staging = self._read_copy(self.staging_key)
            data = staging.data if staging.state == "valid" and staging.data is not None else SaveData()
            return self._record_load(
                SaveLoadResult(
                    data,
                    SaveNotice("read_failed", "save.backup_read_failed", recovery_key),
                ),
                fingerprint_known=False,
            )
        if canonical.state == "unsupported":
            return self._record_load(
                SaveLoadResult(
                    SaveData(),
                    SaveNotice(
                        "unsupported_version",
                        "save.backup_unsupported_version",
                        recovery_key,
                    ),
                ),
                primary_raw=primary_raw,
                fingerprint_known=primary_state != "read_failed",
                force_read_block=primary_state == "read_failed",
            )

        selected = canonical if canonical.state == "valid" else None
        staging = _StoredCopy("missing")
        if selected is None:
            staging = self._read_copy(self.staging_key)
            if staging.state == "read_failed":
                return self._record_load(
                    SaveLoadResult(
                        SaveData(),
                        SaveNotice("read_failed", "save.staging_read_failed", recovery_key),
                    ),
                    fingerprint_known=False,
                )
            if staging.state == "unsupported":
                return self._record_load(
                    SaveLoadResult(
                        SaveData(),
                        SaveNotice(
                            "unsupported_version",
                            "save.staging_unsupported_version",
                            recovery_key,
                        ),
                    ),
                    primary_raw=primary_raw,
                    fingerprint_known=primary_state != "read_failed",
                    force_read_block=primary_state == "read_failed",
                )
            if staging.state == "valid":
                selected = staging

        if selected is None or selected.data is None:
            if (
                primary_state == "missing"
                and canonical.state == "missing"
                and staging.state == "missing"
            ):
                return self._record_load(
                    SaveLoadResult(SaveData()),
                    primary_raw=None,
                    fingerprint_known=True,
                )
            if primary_state == "read_failed":
                return self._record_load(
                    SaveLoadResult(
                        SaveData(),
                        SaveNotice("read_failed", "save.read_failed", recovery_key),
                    ),
                    fingerprint_known=False,
                )
            return self._record_reset_required(
                primary_raw=primary_raw,
                recovery_key=recovery_key,
            )

        data = selected.data
        if primary_state == "read_failed":
            # An unreadable primary may still be valid, so recovery stays memory-only.
            return self._record_load(
                SaveLoadResult(
                    data,
                    SaveNotice("read_failed", "save.primary_read_failed", recovery_key),
                ),
                fingerprint_known=False,
            )
        if primary_state == "corrupt" and recovery_key is None:
            # Do not destroy the corrupt source unless its forensic copy was verified.
            return self._record_load(
                SaveLoadResult(
                    data,
                    SaveNotice("quarantine_failed", "save.quarantine_failed"),
                ),
                primary_raw=primary_raw,
                fingerprint_known=True,
            )

        restored, restored_raw = self._restore_primary(
            data,
            expected_primary=primary_raw,
        )
        if restored == "changed":
            return self._record_load(
                SaveLoadResult(
                    data,
                    SaveNotice(
                        "read_failed",
                        "save.primary_changed_during_recovery",
                        recovery_key,
                    ),
                ),
                fingerprint_known=False,
            )
        if restored == "restored":
            return self._record_load(
                SaveLoadResult(
                    data,
                    SaveNotice("backup_restored", "save.backup_restored", recovery_key),
                ),
                primary_raw=restored_raw,
                fingerprint_known=True,
            )
        return self._record_load(
            SaveLoadResult(
                data,
                SaveNotice("backup_restore_failed", "save.backup_restore_failed", recovery_key),
            ),
            fingerprint_known=False,
        )

    def load(self) -> SaveLoadResult:
        """Load current data, migrating v1 or recovering verified backup data."""

        # Storage and decoder failures end at this service boundary as typed UI state.
        try:
            raw = self.storage.read_text(self.key)
        except Exception:
            return self._load_backup(
                primary_state="read_failed",
                primary_raw=None,
                recovery_key=None,
            )
        if raw is None:
            return self._load_backup(
                primary_state="missing",
                primary_raw=None,
                recovery_key=None,
            )
        try:
            data, migrated = self._decode(raw)
        except _UnsupportedSaveVersion:
            return self._record_load(
                SaveLoadResult(
                    SaveData(),
                    SaveNotice("unsupported_version", "save.unsupported_version"),
                ),
                primary_raw=raw,
                fingerprint_known=True,
            )
        except Exception:
            recovery_key = self._quarantine(raw, self.key)
            return self._load_backup(
                primary_state="corrupt",
                primary_raw=raw,
                recovery_key=recovery_key,
            )
        if migrated:
            return self._record_load(
                SaveLoadResult(data, SaveNotice("migrated_v1", "save.migrated_v1")),
                primary_raw=raw,
                fingerprint_known=True,
            )
        return self._record_load(
            SaveLoadResult(data),
            primary_raw=raw,
            fingerprint_known=True,
        )

    def _latch_primary_read_failure(self) -> None:
        self._write_block = "read_failed"
        self._reset_fingerprints = None
        self._pending_reset_raw = None
        self._has_primary_fingerprint = False
        self._primary_fingerprint = None

    def _block_for_changed_primary(self) -> SaveWriteResult:
        self._write_block = "recovery_required"
        self._reset_fingerprints = None
        self._pending_reset_raw = None
        self._has_primary_fingerprint = False
        self._primary_fingerprint = None
        return SaveWriteResult(ok=False, error_code="recovery_required")

    @staticmethod
    def _copy_error(copy: _StoredCopy) -> SaveWriteErrorCode | None:
        if copy.state == "read_failed":
            return "storage_write_failed"
        if copy.state == "unsupported":
            return "unsupported_version"
        return None

    def _recheck_primary(self, expected_primary: str | None) -> SaveWriteErrorCode | None:
        try:
            current = self.storage.read_text(self.key)
        except Exception:
            self._latch_primary_read_failure()
            return "storage_write_failed"
        if current != expected_primary:
            self._block_for_changed_primary()
            return "recovery_required"
        return None

    def _write_primary(
        self,
        raw: str,
        data: SaveData,
        *,
        expected_primary: str | None,
    ) -> SaveWriteErrorCode | None:
        recheck_error = self._recheck_primary(expected_primary)
        if recheck_error is not None:
            return recheck_error
        try:
            self.storage.write_text(self.key, raw)
        except Exception:
            return "storage_write_failed"
        try:
            verified = self.storage.read_text(self.key)
        except Exception:
            self._latch_primary_read_failure()
            return "storage_write_failed"
        if verified != raw:
            self._block_for_changed_primary()
            return "storage_write_failed"
        try:
            decoded, migrated = self._decode(verified)
        except Exception:
            self._block_for_changed_primary()
            return "storage_write_failed"
        if migrated or decoded != data:
            self._block_for_changed_primary()
            return "storage_write_failed"
        self._remember_primary(raw)
        return None

    def _write_staging(
        self,
        recovery_raw: str,
    ) -> tuple[str | None, SaveWriteErrorCode | None]:
        try:
            self.storage.write_text(self.staging_key, recovery_raw)
            verified = self.storage.read_text(self.staging_key)
            if verified != recovery_raw:
                return None, "storage_write_failed"
            self._decode(verified)
        except Exception:
            return None, "storage_write_failed"
        return verified, None

    def _ensure_staging(
        self,
        recovery_raw: str,
    ) -> tuple[str | None, SaveWriteErrorCode | None]:
        staging = self._read_copy(self.staging_key)
        error = self._copy_error(staging)
        if error is not None:
            return None, error
        if staging.state != "valid" or staging.raw is None:
            return self._write_staging(recovery_raw)
        if staging.raw == recovery_raw:
            return staging.raw, None

        canonical = self._read_copy(self.backup_key)
        canonical_error = self._copy_error(canonical)
        if canonical_error is not None:
            return None, canonical_error
        if canonical.state != "valid" or canonical.raw != staging.raw:
            rotation_error = self._rotate_canonical(staging.raw)
            if rotation_error is not None:
                return None, rotation_error

        recheck_error = self._recheck_primary(recovery_raw)
        if recheck_error is not None:
            return None, recheck_error
        # Canonical now owns the older recovery point, so staging may advance.
        return self._write_staging(recovery_raw)

    def _rotate_canonical(self, recovery_raw: str) -> SaveWriteErrorCode | None:
        try:
            self.storage.write_text(self.backup_key, recovery_raw)
            verified = self.storage.read_text(self.backup_key)
            if verified != recovery_raw:
                return "storage_write_failed"
            self._decode(verified)
        except Exception:
            return "storage_write_failed"
        try:
            self.storage.delete(self.staging_key)
        except Exception:
            pass
        return None

    def _repair_same_data_backup(
        self,
        current: str,
        backup: _StoredCopy,
    ) -> SaveWriteErrorCode | None:
        recheck_error = self._recheck_primary(current)
        if recheck_error is not None:
            return recheck_error
        staging = self._read_copy(self.staging_key)
        staging_error = self._copy_error(staging)
        if staging_error is not None:
            return staging_error
        if staging.state == "valid" and staging.raw is not None:
            rotation_error = self._rotate_canonical(staging.raw)
            if rotation_error is None:
                self._remember_primary(current)
            return rotation_error
        if backup.state == "valid":
            self._remember_primary(current)
            return None
        staged_raw, error = self._ensure_staging(current)
        if error is not None or staged_raw is None:
            return error or "storage_write_failed"
        rotation_error = self._rotate_canonical(staged_raw)
        if rotation_error is None:
            self._remember_primary(current)
        return rotation_error

    def _latch_reset_for_save(self, expected_primary: str | None) -> SaveWriteResult:
        try:
            fingerprints = self._read_fingerprints()
        except Exception:
            self._latch_primary_read_failure()
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        if fingerprints.primary != expected_primary:
            return self._block_for_changed_primary()
        self._write_block = "reset_required"
        self._reset_fingerprints = fingerprints
        self._pending_reset_raw = None
        self._remember_primary(expected_primary)
        return SaveWriteResult(ok=False, error_code="reset_confirmation_required")

    def _save_missing_primary(self, raw: str, data: SaveData) -> SaveWriteResult:
        backup = self._read_copy(self.backup_key)
        backup_error = self._copy_error(backup)
        if backup_error is not None:
            return SaveWriteResult(ok=False, error_code=backup_error)
        staging = self._read_copy(self.staging_key)
        staging_error = self._copy_error(staging)
        if staging_error is not None:
            return SaveWriteResult(ok=False, error_code=staging_error)
        if backup.state == "valid" or staging.state == "valid":
            return SaveWriteResult(ok=False, error_code="recovery_required")
        if backup.state == "corrupt" or staging.state == "corrupt":
            return self._latch_reset_for_save(None)

        primary_error = self._write_primary(raw, data, expected_primary=None)
        if primary_error is not None:
            return SaveWriteResult(ok=False, error_code=primary_error)
        staged_raw, staging_error = self._ensure_staging(raw)
        if staging_error is not None or staged_raw is None:
            return SaveWriteResult(
                ok=False,
                error_code=staging_error or "storage_write_failed",
            )
        rotation_error = self._rotate_canonical(staged_raw)
        if rotation_error is not None:
            return SaveWriteResult(ok=False, error_code=rotation_error)
        return SaveWriteResult(ok=True)

    def _save_corrupt_primary(
        self,
        current: str,
        raw: str,
        data: SaveData,
    ) -> SaveWriteResult:
        if self._quarantine(current, self.key) is None:
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        backup = self._read_copy(self.backup_key)
        backup_error = self._copy_error(backup)
        if backup_error is not None:
            return SaveWriteResult(ok=False, error_code=backup_error)
        if backup.state == "valid":
            primary_error = self._write_primary(raw, data, expected_primary=current)
            return SaveWriteResult(
                ok=primary_error is None,
                error_code=primary_error,
            )

        staging = self._read_copy(self.staging_key)
        staging_error = self._copy_error(staging)
        if staging_error is not None:
            return SaveWriteResult(ok=False, error_code=staging_error)
        if staging.state != "valid" or staging.raw is None:
            return self._latch_reset_for_save(current)

        primary_error = self._write_primary(raw, data, expected_primary=current)
        if primary_error is not None:
            return SaveWriteResult(ok=False, error_code=primary_error)
        rotation_error = self._rotate_canonical(staging.raw)
        if rotation_error is not None:
            return SaveWriteResult(ok=False, error_code=rotation_error)
        return SaveWriteResult(ok=True)

    def save(self, data: SaveData) -> SaveWriteResult:
        """Persist data while retaining a verified pre-write recovery point."""

        if self._write_block == "reset_required":
            return SaveWriteResult(ok=False, error_code="reset_confirmation_required")
        if self._write_block is not None:
            return SaveWriteResult(ok=False, error_code="recovery_required")
        raw = save_data_to_json(data, indent=2)
        # Storage has no CAS; fingerprints reject changes visible to this active session.
        try:
            current = self.storage.read_text(self.key)
        except Exception:
            # Reads gate writes because an unseen valid save must never be overwritten.
            self._latch_primary_read_failure()
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        if self._has_primary_fingerprint and current != self._primary_fingerprint:
            return self._block_for_changed_primary()
        if current is None:
            return self._save_missing_primary(raw, data)

        try:
            current_data, current_migrated = self._decode(current)
        except _UnsupportedSaveVersion:
            return SaveWriteResult(ok=False, error_code="unsupported_version")
        except Exception:
            return self._save_corrupt_primary(current, raw, data)

        backup = self._read_copy(self.backup_key)
        backup_error = self._copy_error(backup)
        if backup_error is not None:
            return SaveWriteResult(ok=False, error_code=backup_error)
        if current_migrated is False and current == raw and current_data == data:
            repair_error = self._repair_same_data_backup(current, backup)
            return SaveWriteResult(
                ok=repair_error is None,
                error_code=repair_error,
            )

        staged_raw, staging_error = self._ensure_staging(current)
        if staging_error is not None or staged_raw is None:
            return SaveWriteResult(
                ok=False,
                error_code=staging_error or "storage_write_failed",
            )
        primary_error = self._write_primary(raw, data, expected_primary=current)
        if primary_error is not None:
            return SaveWriteResult(ok=False, error_code=primary_error)
        # Canonical rotation happens only after the replacement primary verifies exactly.
        rotation_error = self._rotate_canonical(staged_raw)
        if rotation_error is not None:
            return SaveWriteResult(ok=False, error_code=rotation_error)
        return SaveWriteResult(ok=True)

    def _capture_reset_fingerprints(self, changed_key: str) -> None:
        previous = self._reset_fingerprints
        if previous is None:
            return
        try:
            observed = self._read_fingerprints()
        except Exception:
            return
        unchanged = (
            (changed_key == self.key or observed.primary == previous.primary)
            and (changed_key == self.backup_key or observed.backup == previous.backup)
            and (changed_key == self.staging_key or observed.staging == previous.staging)
        )
        if unchanged:
            self._reset_fingerprints = observed

    def _confirm_write(
        self,
        key: str,
        raw: str,
        data: SaveData,
        *,
        expected_raw: str | None,
    ) -> SaveWriteErrorCode | None:
        try:
            current = self.storage.read_text(key)
            if current != expected_raw:
                return "recovery_required"
            self.storage.write_text(key, raw)
            verified = self.storage.read_text(key)
            if verified != raw:
                return "storage_write_failed"
            decoded, migrated = self._decode(verified)
        except Exception:
            return "storage_write_failed"
        if migrated or decoded != data:
            return "storage_write_failed"
        return None

    def confirm_reset(self, data: SaveData) -> SaveWriteResult:
        """Persist an explicitly confirmed reset and unlock only after verification."""

        fingerprints = self._reset_fingerprints
        if self._write_block != "reset_required" or fingerprints is None:
            return SaveWriteResult(ok=False, error_code="reset_not_required")
        raw = save_data_to_json(data, indent=2)
        if self._pending_reset_raw is not None and self._pending_reset_raw != raw:
            return SaveWriteResult(ok=False, error_code="recovery_required")
        try:
            current_fingerprints = self._read_fingerprints()
        except Exception:
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        if current_fingerprints != fingerprints:
            return SaveWriteResult(ok=False, error_code="recovery_required")

        if current_fingerprints.primary != raw:
            primary_error = self._confirm_write(
                self.key,
                raw,
                data,
                expected_raw=current_fingerprints.primary,
            )
            if primary_error is not None:
                if primary_error == "storage_write_failed":
                    self._capture_reset_fingerprints(self.key)
                return SaveWriteResult(ok=False, error_code=primary_error)
            self._pending_reset_raw = raw
            self._reset_fingerprints = _Fingerprints(
                primary=raw,
                backup=current_fingerprints.backup,
                staging=current_fingerprints.staging,
            )
        else:
            self._pending_reset_raw = raw

        fingerprints = self._reset_fingerprints
        if fingerprints is None:
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        if fingerprints.staging != raw:
            staging_error = self._confirm_write(
                self.staging_key,
                raw,
                data,
                expected_raw=fingerprints.staging,
            )
            if staging_error is not None:
                if staging_error == "storage_write_failed":
                    self._capture_reset_fingerprints(self.staging_key)
                return SaveWriteResult(ok=False, error_code=staging_error)
            self._reset_fingerprints = _Fingerprints(
                primary=fingerprints.primary,
                backup=fingerprints.backup,
                staging=raw,
            )

        fingerprints = self._reset_fingerprints
        if fingerprints is None:
            return SaveWriteResult(ok=False, error_code="storage_write_failed")
        if fingerprints.backup != raw:
            backup_error = self._confirm_write(
                self.backup_key,
                raw,
                data,
                expected_raw=fingerprints.backup,
            )
            if backup_error is not None:
                if backup_error == "storage_write_failed":
                    self._capture_reset_fingerprints(self.backup_key)
                return SaveWriteResult(ok=False, error_code=backup_error)

        try:
            self.storage.delete(self.staging_key)
        except Exception:
            pass
        self._write_block = None
        self._reset_fingerprints = None
        self._pending_reset_raw = None
        self._remember_primary(raw)
        return SaveWriteResult(ok=True)
