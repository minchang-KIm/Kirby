"""Build identities, manifests, hashes, and archives for release tooling."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

Target = Literal["web", "windows", "source"]

_TARGETS = frozenset(("web", "windows", "source"))
_FULL_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_SEMANTIC_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9]\d*)\."
    r"(?:0|[1-9]\d*)\."
    r"(?:0|[1-9]\d*)"
    r"(?:-(?:(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
_WINDOWS_DRIVE_PATTERN = re.compile(r"[A-Za-z]:")
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_COPY_BUFFER_BYTES = 1024 * 1024
_WINDOWS_REPARSE_ATTRIBUTE = 0x400


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
    canonical_files = sorted({_validate_manifest_path(item) for item in files})
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

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        # A same-directory replacement prevents readers from observing a partial manifest.
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return path


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest while reading bounded chunks."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    if _is_link_or_reparse(path):
        raise ValueError(f"hash source must not be a link or reparse point: {path}")
    if not path.exists():
        raise FileNotFoundError(f"hash source does not exist: {path}")
    if not path.is_file():
        if path.is_dir():
            raise IsADirectoryError(f"hash source is a directory: {path}")
        raise ValueError(f"hash source is not a regular file: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_COPY_BUFFER_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_reproducible_zip(source_dir: Path, destination: Path) -> Path:
    """Atomically archive regular source files with normalized ZIP metadata."""
    if not isinstance(source_dir, Path):
        raise TypeError("source_dir must be a pathlib.Path")
    if not isinstance(destination, Path):
        raise TypeError("destination must be a pathlib.Path")
    if _is_link_or_reparse(source_dir):
        raise ValueError(f"ZIP source must not be a link or reparse point: {source_dir}")
    if not source_dir.exists():
        raise FileNotFoundError(f"ZIP source does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"ZIP source is not a directory: {source_dir}")
    if _is_link_or_reparse(destination):
        raise ValueError(f"ZIP destination must not be a link or reparse point: {destination}")
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError(f"ZIP destination is a directory: {destination}")
    _reject_destination_within_source(source_dir, destination)

    members = _collect_regular_files(source_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for member_name, source_path in members:
                info = zipfile.ZipInfo(member_name, _ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, source_path.read_bytes(), compresslevel=9)
        with temporary_path.open("r+b") as completed_archive:
            os.fsync(completed_archive.fileno())
        temporary_path.chmod(0o644)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination


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
    return value


def _is_link_or_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    file_attributes = int(getattr(details, "st_file_attributes", 0))
    return stat.S_ISLNK(details.st_mode) or bool(file_attributes & _WINDOWS_REPARSE_ATTRIBUTE)


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


def _collect_regular_files(source_dir: Path) -> list[tuple[str, Path]]:
    members: list[tuple[str, Path]] = []

    def visit(directory: Path, relative_parts: tuple[str, ...]) -> None:
        with os.scandir(directory) as entries:
            ordered_entries = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered_entries:
            path = Path(entry.path)
            member_parts = (*relative_parts, entry.name)
            member_name = _validate_manifest_path(PurePosixPath(*member_parts).as_posix())
            if entry.is_symlink() or _is_link_or_reparse(path):
                raise ValueError(f"ZIP source contains a link or reparse point: {path}")
            if entry.is_dir(follow_symlinks=False):
                visit(path, member_parts)
            elif entry.is_file(follow_symlinks=False):
                members.append((member_name, path))
            else:
                raise ValueError(f"ZIP source contains a non-regular entry: {path}")

    visit(source_dir, ())
    return sorted(members, key=lambda item: item[0])
