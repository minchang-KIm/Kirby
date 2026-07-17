"""Build identities, manifests, hashes, and archives for release tooling."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
import zipfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, cast

Target = Literal["web", "windows", "source"]

_TARGETS = frozenset(("web", "windows", "source"))
_FULL_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_SEMANTIC_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-(?:(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
_WINDOWS_DRIVE_PATTERN = re.compile(r"[A-Za-z]:")
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_COPY_BUFFER_BYTES = 1024 * 1024
_WINDOWS_REPARSE_ATTRIBUTE = 0x400
_WINDOWS_INVALID_COMPONENT_CHARACTERS = frozenset('<>:"\\|?*')
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


@dataclass(frozen=True, slots=True)
class _StatFingerprint:
    device: int
    inode: int
    kind: int
    size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class _PortablePathNode:
    original: str
    is_terminal: bool


@dataclass(slots=True)
class _DirectoryHandle:
    path: Path
    descriptor: int
    expected: os.stat_result
    opened: os.stat_result
    parent: _DirectoryHandle | None
    name: str | None
    track_changes: bool


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    """Validated source identity embedded into one release target."""

    version: str
    commit_sha: str
    target: Target

    def __post_init__(self) -> None:
        if type(self.version) is not str or _SEMANTIC_VERSION_PATTERN.fullmatch(self.version) is None:
            raise ValueError(f"version must be a semantic version, received {self.version!r}")
        if type(self.commit_sha) is not str or _FULL_SHA_PATTERN.fullmatch(self.commit_sha) is None:
            raise ValueError("commit_sha must be exactly 40 lowercase hexadecimal characters")
        _validate_target(self.target)


def read_build_identity(root: Path, target: Target) -> BuildIdentity:
    """Read a semantic project version and the repository's full HEAD commit."""
    _validate_target(target)
    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    if not root.exists():
        raise FileNotFoundError(f"release root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"release root is not a directory: {root}")

    project_path = root / "pyproject.toml"
    if not project_path.is_file():
        raise FileNotFoundError(f"release project file does not exist: {project_path}")
    try:
        payload = tomllib.loads(project_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"release project TOML is invalid: {project_path}: {error}") from error
    project = payload.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"release project is missing a [project] table: {project_path}")
    version = project.get("version")
    if type(version) is not str:
        raise ValueError(f"release project version must be a string: {project_path}")

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("git executable is unavailable while reading build identity") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "unknown git error").strip()
        raise RuntimeError(f"git rev-parse HEAD failed for {root}: {detail}") from error
    return BuildIdentity(
        version=version,
        commit_sha=completed.stdout.strip(),
        target=target,
    )


def write_build_manifest(
    path: Path,
    identity: BuildIdentity,
    files: list[str],
) -> Path:
    """Atomically write canonical release metadata with unique POSIX members."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    if not isinstance(identity, BuildIdentity):
        raise TypeError("identity must be a BuildIdentity")
    if not isinstance(files, list):
        raise TypeError("files must be a list of POSIX paths")
    canonical_files = _canonical_manifest_files(files)
    payload = {
        "commit_sha": identity.commit_sha,
        "files": canonical_files,
        "target": identity.target,
        "version": identity.version,
    }
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)

    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        destination = os.fdopen(descriptor, "wb")
        descriptor = None
        with destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        # A same-directory replacement prevents readers from observing a partial manifest.
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        _cleanup_temporary_output(
            temporary_path,
            descriptor,
            preserve_active_error=sys.exc_info()[0] is not None,
        )
    return path


def sha256_file(path: Path) -> str:
    """Hash one stable regular file from a no-follow descriptor."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    try:
        expected = path.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"hash source does not exist: {path}") from None
    if _is_link_or_reparse(path) or _stat_is_link_or_reparse(expected):
        raise ValueError(f"hash source must not be a link or reparse point: {path}")
    if not stat.S_ISREG(expected.st_mode):
        if stat.S_ISDIR(expected.st_mode):
            raise IsADirectoryError(f"hash source is a directory: {path}")
        raise ValueError(f"hash source is not a regular file: {path}")

    digest = hashlib.sha256()
    absolute_path = Path(os.path.abspath(path))
    with _protected_directory_chain(absolute_path.parent) as parent:
        with _verified_regular_file(parent, absolute_path.name, absolute_path, expected) as (source, _):
            for chunk in iter(lambda: source.read(_COPY_BUFFER_BYTES), b""):
                digest.update(chunk)
    return digest.hexdigest()


def write_reproducible_zip(source_dir: Path, destination: Path) -> Path:
    """Atomically archive stable regular files with normalized ZIP metadata."""
    if not isinstance(source_dir, Path):
        raise TypeError("source_dir must be a pathlib.Path")
    if not isinstance(destination, Path):
        raise TypeError("destination must be a pathlib.Path")
    try:
        expected_source = source_dir.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"ZIP source does not exist: {source_dir}") from None
    if _is_link_or_reparse(source_dir) or _stat_is_link_or_reparse(expected_source):
        raise ValueError(f"ZIP source must not be a link or reparse point: {source_dir}")
    if not stat.S_ISDIR(expected_source.st_mode):
        raise NotADirectoryError(f"ZIP source is not a directory: {source_dir}")
    _validate_zip_destination(destination)
    _reject_destination_within_source(source_dir, destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    _preflight_zip_compression()
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        os.close(descriptor)
        descriptor = None
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            absolute_source = Path(os.path.abspath(source_dir))
            with _protected_directory_chain(
                absolute_source,
                expected_final=expected_source,
            ) as protected_source:
                _archive_directory(archive, protected_source, (), {})
        with temporary_path.open("r+b") as completed_archive:
            os.fsync(completed_archive.fileno())
        temporary_path.chmod(0o644)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        _cleanup_temporary_output(
            temporary_path,
            descriptor,
            preserve_active_error=sys.exc_info()[0] is not None,
        )
    return destination


def _cleanup_temporary_output(
    temporary_path: Path | None,
    descriptor: int | None,
    *,
    preserve_active_error: bool,
) -> None:
    cleanup_errors: list[OSError] = []
    if descriptor is not None:
        try:
            os.close(descriptor)
        except OSError as error:
            cleanup_errors.append(error)
    if temporary_path is not None:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as error:
            cleanup_errors.append(error)
    if cleanup_errors and not preserve_active_error:
        raise cleanup_errors[0]


def _validate_target(target: object) -> Target:
    if type(target) is not str or target not in _TARGETS:
        raise ValueError(f"target must be one of {sorted(_TARGETS)}, received {target!r}")
    return cast(Target, target)


def _validate_manifest_path(value: object) -> str:
    if type(value) is not str:
        raise ValueError(f"manifest file path must be a string, received {value!r}")
    candidate = PurePosixPath(value)
    if (
        not value
        or not candidate.parts
        or "\\" in value
        or candidate.is_absolute()
        or _WINDOWS_DRIVE_PATTERN.match(value) is not None
        or candidate.as_posix() != value
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"manifest file path must be canonical and relative: {value!r}")
    for component in candidate.parts:
        _validate_portable_component(component, value)
    return value


def _validate_portable_component(component: str, path: str) -> None:
    reserved_basename = unicodedata.normalize("NFKC", component.split(".", 1)[0]).casefold()
    if (
        component.endswith((".", " "))
        or any(character in _WINDOWS_INVALID_COMPONENT_CHARACTERS for character in component)
        or reserved_basename in _WINDOWS_RESERVED_BASENAMES
    ):
        raise ValueError(f"manifest file path must be portable across supported hosts: {path!r}")


def _portable_component_key(component: str) -> str:
    """Return the documented NFKC-plus-casefold portable component key."""
    return unicodedata.normalize("NFKC", component).casefold()


def _register_portable_path(
    path: str,
    registered: dict[str, _PortablePathNode],
    *,
    terminal: bool,
) -> None:
    parts = PurePosixPath(path).parts
    for length in range(1, len(parts) + 1):
        portable_key = "/".join(_portable_component_key(part) for part in parts[:length])
        original = "/".join(parts[:length])
        is_terminal = terminal and length == len(parts)
        previous = registered.get(portable_key)
        if previous is None:
            registered[portable_key] = _PortablePathNode(original, is_terminal)
        elif previous.original != original or previous.is_terminal != is_terminal:
            raise ValueError(
                f"portable path collision: {previous.original!r} conflicts with {original!r}"
            )


def _canonical_manifest_files(files: list[str]) -> list[str]:
    canonical: set[str] = set()
    registered: dict[str, _PortablePathNode] = {}
    for item in files:
        path = _validate_manifest_path(item)
        _register_portable_path(path, registered, terminal=True)
        canonical.add(path)
    return sorted(canonical)


def _stat_fingerprint(details: os.stat_result) -> _StatFingerprint:
    return _StatFingerprint(
        device=details.st_dev,
        inode=details.st_ino,
        kind=stat.S_IFMT(details.st_mode),
        size=details.st_size,
        modified_ns=details.st_mtime_ns,
    )


def _stat_is_link_or_reparse(details: os.stat_result) -> bool:
    file_attributes = int(getattr(details, "st_file_attributes", 0) or 0)
    return stat.S_ISLNK(details.st_mode) or bool(file_attributes & _WINDOWS_REPARSE_ATTRIBUTE)


def _require_opened_kind(
    details: os.stat_result,
    path: Path,
    *,
    directory: bool,
) -> None:
    if _stat_is_link_or_reparse(details):
        raise ValueError(f"release source must not be a link or reparse point: {path}")
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_kind(details.st_mode):
        expected_name = "directory" if directory else "regular file"
        raise ValueError(f"release source must remain a {expected_name}: {path}")


def _assert_same_state(
    expected: os.stat_result,
    actual: os.stat_result,
    path: Path,
) -> None:
    expected_fingerprint = _stat_fingerprint(expected)
    actual_fingerprint = _stat_fingerprint(actual)
    if (
        expected_fingerprint.device,
        expected_fingerprint.inode,
        expected_fingerprint.kind,
    ) != (
        actual_fingerprint.device,
        actual_fingerprint.inode,
        actual_fingerprint.kind,
    ):
        raise ValueError(f"release source identity changed while reading: {path}")
    if (
        expected_fingerprint.size,
        expected_fingerprint.modified_ns,
    ) != (
        actual_fingerprint.size,
        actual_fingerprint.modified_ns,
    ):
        raise ValueError(f"release source changed while reading: {path}")


def _assert_same_identity(
    expected: os.stat_result,
    actual: os.stat_result,
    path: Path,
) -> None:
    expected_fingerprint = _stat_fingerprint(expected)
    actual_fingerprint = _stat_fingerprint(actual)
    if (
        expected_fingerprint.device,
        expected_fingerprint.inode,
        expected_fingerprint.kind,
    ) != (
        actual_fingerprint.device,
        actual_fingerprint.inode,
        actual_fingerprint.kind,
    ):
        raise ValueError(f"release source identity changed while reading: {path}")


def _open_windows_descriptor(path: Path, *, directory: bool) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    generic_read = 0x80000000
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    file_flag_sequential_scan = 0x08000000

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    desired_access = file_read_attributes if directory else generic_read
    flags = file_flag_open_reparse_point | (
        file_flag_backup_semantics if directory else file_flag_sequential_scan
    )
    handle = create_file(
        str(path),
        desired_access,
        file_share_read | file_share_write,
        None,
        open_existing,
        flags,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close_handle(handle)
        raise
    try:
        os.set_inheritable(descriptor, False)
    except BaseException:
        # open_osfhandle transferred HANDLE ownership to this CRT descriptor.
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    return descriptor


def _open_descriptor(
    path: Path,
    *,
    directory: bool,
    parent: _DirectoryHandle | None = None,
    name: str | None = None,
) -> int:
    if os.name == "nt":
        return _open_windows_descriptor(path, directory=directory)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError("release source validation requires O_NOFOLLOW")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if directory_flag is None:
            raise RuntimeError("release source validation requires O_DIRECTORY")
        flags |= directory_flag
    if parent is None:
        return os.open(path, flags)
    if name is None:
        raise AssertionError("a relative descriptor open requires a member name")
    return os.open(name, flags, dir_fd=parent.descriptor)


def _entry_lstat(directory: _DirectoryHandle, name: str) -> os.stat_result:
    if os.name == "nt":
        return (directory.path / name).lstat()
    return os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)


def _open_verified_descriptor(
    path: Path,
    expected: os.stat_result,
    *,
    directory: bool,
    parent: _DirectoryHandle | None = None,
    name: str | None = None,
) -> tuple[int, os.stat_result]:
    try:
        descriptor = _open_descriptor(
            path,
            directory=directory,
            parent=parent,
            name=name,
        )
    except OSError as error:
        try:
            current = path.lstat() if parent is None or name is None else _entry_lstat(parent, name)
        except OSError as current_error:
            raise ValueError(f"release source identity changed while reading: {path}") from current_error
        if _stat_is_link_or_reparse(current):
            raise ValueError(f"release source must not be a link or reparse point: {path}") from error
        _assert_same_state(expected, current, path)
        raise
    try:
        opened = os.fstat(descriptor)
        _require_opened_kind(opened, path, directory=directory)
        _assert_same_state(expected, opened, path)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, opened


def _verify_directory(directory: _DirectoryHandle) -> None:
    after = os.fstat(directory.descriptor)
    _require_opened_kind(after, directory.path, directory=True)
    if directory.track_changes:
        _assert_same_state(directory.opened, after, directory.path)
    else:
        _assert_same_identity(directory.opened, after, directory.path)
    if directory.parent is None or directory.name is None:
        current = directory.path.lstat()
    else:
        current = _entry_lstat(directory.parent, directory.name)
    if directory.track_changes:
        _assert_same_state(directory.expected, current, directory.path)
    else:
        _assert_same_identity(directory.expected, current, directory.path)


@contextmanager
def _protected_directory_chain(
    path: Path,
    *,
    expected_final: os.stat_result | None = None,
    create: bool = False,
) -> Iterator[_DirectoryHandle]:
    absolute_path = Path(os.path.abspath(path))
    anchor = Path(absolute_path.anchor)
    records: list[_DirectoryHandle] = []
    try:
        expected_anchor = expected_final if absolute_path == anchor and expected_final is not None else anchor.lstat()
        if _is_link_or_reparse(anchor) or _stat_is_link_or_reparse(expected_anchor):
            raise ValueError(f"release source must not contain a link or reparse point: {anchor}")
        descriptor, opened = _open_verified_descriptor(anchor, expected_anchor, directory=True)
        current = _DirectoryHandle(
            anchor,
            descriptor,
            expected_anchor,
            opened,
            None,
            None,
            absolute_path == anchor and expected_final is not None,
        )
        records.append(current)

        for component in absolute_path.parts[1:]:
            component_path = current.path / component
            if component_path == absolute_path and expected_final is not None:
                expected = expected_final
            else:
                try:
                    expected = _entry_lstat(current, component)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        if os.name == "nt":
                            component_path.mkdir()
                        else:
                            os.mkdir(component, dir_fd=current.descriptor)
                    except FileExistsError:
                        pass
                    expected = _entry_lstat(current, component)
            if _is_link_or_reparse(component_path) or _stat_is_link_or_reparse(expected):
                raise ValueError(
                    f"release source must not contain a link or reparse point: {component_path}"
                )
            descriptor, opened = _open_verified_descriptor(
                component_path,
                expected,
                directory=True,
                parent=current,
                name=component,
            )
            current = _DirectoryHandle(
                component_path,
                descriptor,
                expected,
                opened,
                current,
                component,
                component_path == absolute_path and expected_final is not None,
            )
            records.append(current)

        yield current
        for record in reversed(records):
            _verify_directory(record)
    finally:
        for record in reversed(records):
            os.close(record.descriptor)


@contextmanager
def _verified_child_directory(
    parent: _DirectoryHandle,
    name: str,
    path: Path,
    expected: os.stat_result,
) -> Iterator[_DirectoryHandle]:
    descriptor, opened = _open_verified_descriptor(
        path,
        expected,
        directory=True,
        parent=parent,
        name=name,
    )
    child = _DirectoryHandle(path, descriptor, expected, opened, parent, name, True)
    try:
        yield child
        _verify_directory(child)
    finally:
        os.close(descriptor)


@contextmanager
def _verified_regular_file(
    parent: _DirectoryHandle,
    name: str,
    path: Path,
    expected: os.stat_result,
) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    descriptor, opened = _open_verified_descriptor(
        path,
        expected,
        directory=False,
        parent=parent,
        name=name,
    )
    source = os.fdopen(descriptor, "rb")
    try:
        yield source, opened
        after = os.fstat(source.fileno())
        _require_opened_kind(after, path, directory=False)
        _assert_same_state(opened, after, path)
        current = _entry_lstat(parent, name)
        _assert_same_state(expected, current, path)
    finally:
        source.close()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    return _stat_is_link_or_reparse(details)


def _validate_zip_destination(destination: Path) -> None:
    try:
        details = destination.lstat()
    except FileNotFoundError:
        return
    if _stat_is_link_or_reparse(details):
        raise ValueError(f"ZIP destination must not be a link or reparse point: {destination}")
    if stat.S_ISDIR(details.st_mode):
        raise IsADirectoryError(f"ZIP destination is a directory: {destination}")
    if not stat.S_ISREG(details.st_mode):
        raise ValueError(f"ZIP destination must be a regular file: {destination}")


def _preflight_zip_compression() -> None:
    compressor = zlib.compressobj(
        9,
        zlib.DEFLATED,
        -15,
    )
    compressor.flush()


def _reject_destination_within_source(source_dir: Path, destination: Path) -> None:
    source_lexical = Path(os.path.abspath(source_dir))
    destination_lexical = Path(os.path.abspath(destination))
    source_resolved = source_dir.resolve(strict=True)
    destination_resolved = destination.resolve(strict=False)
    if (
        destination_lexical.is_relative_to(source_lexical)
        or destination_resolved.is_relative_to(source_resolved)
    ):
        raise ValueError(
            f"ZIP destination must be outside ZIP source: {destination} is inside {source_dir}"
        )


def _directory_names(directory: _DirectoryHandle) -> list[str]:
    names = os.listdir(directory.path if os.name == "nt" else directory.descriptor)
    return sorted(names)


def _archive_directory(
    archive: zipfile.ZipFile,
    directory: _DirectoryHandle,
    relative_parts: tuple[str, ...],
    registered: dict[str, _PortablePathNode],
) -> None:
    for name in _directory_names(directory):
        path = directory.path / name
        expected = _entry_lstat(directory, name)
        member_parts = (*relative_parts, name)
        member_name = _validate_manifest_path(PurePosixPath(*member_parts).as_posix())
        _register_portable_path(
            member_name,
            registered,
            terminal=stat.S_ISREG(expected.st_mode),
        )
        if _is_link_or_reparse(path) or _stat_is_link_or_reparse(expected):
            raise ValueError(f"ZIP source contains a link or reparse point: {path}")
        if stat.S_ISDIR(expected.st_mode):
            with _verified_child_directory(directory, name, path, expected) as child:
                _archive_directory(archive, child, member_parts, registered)
        elif stat.S_ISREG(expected.st_mode):
            with _verified_regular_file(directory, name, path, expected) as (source, opened):
                info = zipfile.ZipInfo(member_name, _ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.file_size = opened.st_size
                # Python 3.12 exposes this setting only through ZipInfo's compatibility slot.
                object.__setattr__(info, "_compresslevel", 9)
                with archive.open(info, mode="w") as member:
                    for chunk in iter(lambda: source.read(_COPY_BUFFER_BYTES), b""):
                        member.write(chunk)
        else:
            raise ValueError(f"ZIP source contains a non-regular entry: {path}")
