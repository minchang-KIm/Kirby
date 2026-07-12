"""Release-helper contracts shared by every packaged artifact."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import subprocess
import zipfile
import zlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import BinaryIO, NoReturn, cast

import pytest

import tools.release_common as release_common
from tools.release_common import (
    BuildIdentity,
    Target,
    read_build_identity,
    sha256_file,
    write_build_manifest,
    write_reproducible_zip,
)


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _committed_project(tmp_path: Path, *, version: str = "1.0.0") -> tuple[Path, str]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "release-test"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    _git(root, "init", "--quiet")
    _git(root, "add", "pyproject.toml")
    _git(
        root,
        "-c",
        "user.name=Windsprig Tests",
        "-c",
        "user.email=windsprig-tests@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "test fixture",
    )
    return root, _git(root, "rev-parse", "HEAD")


def test_build_identity_is_frozen_slotted_and_accepts_semantic_versions() -> None:
    identity = BuildIdentity(
        version="1.2.3-rc.1+build.5",
        commit_sha="a" * 40,
        target="source",
    )

    assert not hasattr(identity, "__dict__")
    with pytest.raises(FrozenInstanceError):
        identity.version = "2.0.0"  # type: ignore[misc]


@pytest.mark.parametrize(
    "version",
    [
        "",
        "1",
        "1.0",
        "01.0.0",
        "1.0.0.0",
        "v1.0.0",
        "1.0.0-",
        "1\u0660.0.0",
        "1.0.0-1\u0660",
        "1\uff11.0.0",
        "1.0.0-1\uff11",
    ],
)
def test_build_identity_rejects_invalid_semantic_version(version: str) -> None:
    with pytest.raises(ValueError, match="version"):
        BuildIdentity(version=version, commit_sha="a" * 40, target="web")


@pytest.mark.parametrize(
    "commit_sha",
    ["a" * 39, "A" * 40, "g" * 40, "not-a-sha"],
)
def test_build_identity_requires_a_full_lowercase_git_sha(commit_sha: str) -> None:
    with pytest.raises(ValueError, match="commit_sha"):
        BuildIdentity(version="1.0.0", commit_sha=commit_sha, target="web")


def test_build_identity_rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="target"):
        BuildIdentity(
            version="1.0.0",
            commit_sha="a" * 40,
            target=cast(Target, "linux"),
        )


def test_read_build_identity_reads_version_and_full_sha_from_real_repo(tmp_path: Path) -> None:
    root, commit_sha = _committed_project(tmp_path)

    identity = read_build_identity(root, "windows")

    assert identity == BuildIdentity("1.0.0", commit_sha, "windows")


def test_read_build_identity_reports_missing_project_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="pyproject.toml"):
        read_build_identity(tmp_path, "web")


def test_read_build_identity_reports_missing_root_before_project_lookup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="release root does not exist"):
        read_build_identity(tmp_path / "missing-root", "web")


def test_read_build_identity_rejects_a_nondirectory_root(tmp_path: Path) -> None:
    root = tmp_path / "not-a-directory"
    root.write_text("content", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="release root"):
        read_build_identity(root, "web")


def test_read_build_identity_reports_invalid_project_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")

    with pytest.raises(ValueError, match="project TOML is invalid"):
        read_build_identity(tmp_path, "web")


@pytest.mark.parametrize(
    "project_source, message",
    [
        ('version = "1.0.0"\n', "missing a \\[project\\] table"),
        ('[project]\nname = "release-test"\nversion = 100\n', "version must be a string"),
    ],
)
def test_read_build_identity_reports_missing_or_nonstr_project_version(
    tmp_path: Path,
    project_source: str,
    message: str,
) -> None:
    (tmp_path / "pyproject.toml").write_text(project_source, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_build_identity(tmp_path, "web")


def test_read_build_identity_reports_repository_without_a_commit(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "release-test"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    _git(tmp_path, "init", "--quiet")

    with pytest.raises(RuntimeError, match="git rev-parse HEAD failed"):
        read_build_identity(tmp_path, "source")


def test_manifest_has_canonical_bytes_sorted_unique_posix_paths_and_final_newline(
    tmp_path: Path,
) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="b" * 40, target="web")
    destination = tmp_path / "nested" / "build-info.json"

    result = write_build_manifest(
        destination,
        identity,
        files=["index.html", "assets/ui/icon.png", "index.html"],
    )

    expected = (
        "{\n"
        f'  "commit_sha": "{"b" * 40}",\n'
        '  "files": [\n'
        '    "assets/ui/icon.png",\n'
        '    "index.html"\n'
        "  ],\n"
        '  "target": "web",\n'
        '  "version": "1.0.0"\n'
        "}\n"
    )
    assert result == destination
    assert destination.read_bytes() == expected.encode("utf-8")
    assert json.loads(expected)["files"] == ["assets/ui/icon.png", "index.html"]
    assert sorted(path.name for path in destination.parent.iterdir()) == ["build-info.json"]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        ".",
        "/absolute",
        "C:/drive.txt",
        "C:drive.txt",
        "../secret",
        "a/../secret",
        "./index.html",
        "a//b",
        "a\\b",
        "bad\x7fname",
    ],
)
def test_manifest_rejects_noncanonical_or_unsafe_member_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="c" * 40, target="source")

    with pytest.raises(ValueError, match="manifest file path"):
        write_build_manifest(tmp_path / "build-info.json", identity, [unsafe_path])


def test_manifest_rejects_nonstring_and_control_character_paths(tmp_path: Path) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="d" * 40, target="source")

    with pytest.raises(ValueError, match="manifest file path"):
        write_build_manifest(
            tmp_path / "build-info.json",
            identity,
            [cast(str, 7)],
        )
    with pytest.raises(ValueError, match="manifest file path"):
        write_build_manifest(tmp_path / "build-info.json", identity, ["bad\x00name"])


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "bad<name.txt",
        "bad>name.txt",
        'bad"name.txt',
        "bad:name.txt",
        "bad|name.txt",
        "bad?name.txt",
        "bad*name.txt",
        "CON",
        "con.txt",
        "dir/AuX.json",
        "COM1.log",
        "lpt9",
        "NUL.tar.gz",
        "trailing-dot.",
        "trailing-space ",
        "directory./file.txt",
        "directory /file.txt",
    ],
)
def test_manifest_rejects_windows_invalid_portable_components(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="d" * 40, target="source")

    with pytest.raises(ValueError, match="manifest file path"):
        write_build_manifest(tmp_path / "build-info.json", identity, [unsafe_path])


@pytest.mark.parametrize(
    "files",
    [
        ["A.txt", "a.txt"],
        ["Assets/one.txt", "assets/two.txt"],
        ["caf\u00e9.txt", "cafe\u0301.txt"],
    ],
)
def test_manifest_rejects_portable_case_and_unicode_collisions(
    tmp_path: Path,
    files: list[str],
) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="d" * 40, target="source")

    with pytest.raises(ValueError, match="portable path collision"):
        write_build_manifest(tmp_path / "build-info.json", identity, files)


def test_read_build_identity_rejects_nonpath_root() -> None:
    with pytest.raises(TypeError, match="root"):
        read_build_identity(cast(Path, "not-a-path"), "web")


def test_manifest_writer_rejects_wrong_boundary_types(tmp_path: Path) -> None:
    identity = BuildIdentity(version="1.0.0", commit_sha="e" * 40, target="source")

    with pytest.raises(TypeError, match="path"):
        write_build_manifest(cast(Path, "build-info.json"), identity, [])
    with pytest.raises(TypeError, match="identity"):
        write_build_manifest(tmp_path / "build-info.json", cast(BuildIdentity, object()), [])
    with pytest.raises(TypeError, match="files"):
        write_build_manifest(tmp_path / "build-info.json", identity, cast(list[str], ()))


def test_hash_and_archive_helpers_reject_nonpath_inputs(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="path"):
        sha256_file(cast(Path, "payload.bin"))
    with pytest.raises(TypeError, match="source_dir"):
        write_reproducible_zip(cast(Path, "source"), tmp_path / "archive.zip")
    with pytest.raises(TypeError, match="destination"):
        write_reproducible_zip(tmp_path, cast(Path, "archive.zip"))


def test_sha256_file_matches_hashlib_for_a_multichunk_file(tmp_path: Path) -> None:
    source = tmp_path / "payload.bin"
    payload = (b"Windsprig-release-block\n" * 60_000) + b"tail"
    source.write_bytes(payload)

    assert sha256_file(source) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_rejects_missing_directory_and_symlink_inputs(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="hash source"):
        sha256_file(tmp_path / "missing.bin")
    with pytest.raises(IsADirectoryError, match="hash source"):
        sha256_file(tmp_path)

    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("this host does not permit test symlinks")
    with pytest.raises(ValueError, match="link or reparse"):
        sha256_file(link)


def test_sha256_file_rejects_same_size_path_replacement_after_link_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "payload.bin"
    replacement = tmp_path / "replacement.bin"
    source.write_bytes(b"trusted!")
    replacement.write_bytes(b"outside!")
    original_link_check = release_common._is_link_or_reparse
    swapped = False

    def replace_after_link_check(path: Path) -> bool:
        nonlocal swapped
        result = original_link_check(path)
        if path == source and not swapped:
            os.replace(replacement, source)
            swapped = True
        return result

    monkeypatch.setattr(release_common, "_is_link_or_reparse", replace_after_link_check)

    with pytest.raises(ValueError, match="changed while reading|identity changed"):
        sha256_file(source)

    assert swapped


def test_sha256_file_rejects_same_size_mid_read_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"A" * (release_common._COPY_BUFFER_BYTES * 2 + 17))
    original_sha256 = hashlib.sha256
    mutated = False

    with source.open("r+b") as writer:

        class MutatingDigest:
            def __init__(self) -> None:
                self._digest = original_sha256()

            def update(self, chunk: bytes) -> None:
                nonlocal mutated
                self._digest.update(chunk)
                if not mutated:
                    details = os.fstat(writer.fileno())
                    writer.seek(0)
                    writer.write(b"B" * details.st_size)
                    writer.flush()
                    os.fsync(writer.fileno())
                    os.utime(
                        source,
                        ns=(details.st_atime_ns, details.st_mtime_ns + 2_000_000_000),
                    )
                    mutated = True

            def hexdigest(self) -> str:
                return self._digest.hexdigest()

        monkeypatch.setattr(hashlib, "sha256", MutatingDigest)

        with pytest.raises(ValueError, match="changed while reading"):
            sha256_file(source)

    assert mutated


def test_reproducible_zip_is_recursive_sorted_and_metadata_normalized(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    empty = source / "empty-directory"
    nested.mkdir(parents=True)
    empty.mkdir()
    (source / "z.txt").write_bytes(b"z" * 8_192)
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    (nested / "payload.bin").write_bytes(bytes(range(256)) * 20)
    destination = tmp_path / "release" / "windsprig.zip"

    result = write_reproducible_zip(source, destination)

    assert result == destination
    with zipfile.ZipFile(result) as archive:
        assert archive.namelist() == ["a.txt", "nested/payload.bin", "z.txt"]
        assert archive.read("a.txt") == b"alpha"
        assert archive.read("nested/payload.bin") == bytes(range(256)) * 20
        for item in archive.infolist():
            assert item.date_time == (1980, 1, 1, 0, 0, 0)
            assert item.compress_type == zipfile.ZIP_DEFLATED
            assert item.create_system == 3
            assert (item.external_attr >> 16) & 0o777 == 0o644
            assert item.extra == b""
        assert archive.getinfo("z.txt").compress_size < archive.getinfo("z.txt").file_size
    assert sorted(path.name for path in destination.parent.iterdir()) == ["windsprig.zip"]


def test_reproducible_zip_is_byte_stable_across_mtimes_and_same_output_rebuild(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first_file = source / "first.txt"
    second_file = source / "second.txt"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("second", encoding="utf-8")
    destination = tmp_path / "windsprig.zip"

    write_reproducible_zip(source, destination)
    first_bytes = destination.read_bytes()
    os.utime(first_file, (1_000_000_000, 1_000_000_000))
    os.utime(second_file, (2_000_000_000, 2_000_000_000))
    write_reproducible_zip(source, destination)

    assert destination.read_bytes() == first_bytes


def test_reproducible_zip_allows_empty_source_and_excludes_empty_directories(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "only-empty" / "nested").mkdir(parents=True)

    archive_path = write_reproducible_zip(source, tmp_path / "empty.zip")

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == []


def test_reproducible_zip_rejects_missing_and_nondirectory_sources(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="ZIP source"):
        write_reproducible_zip(tmp_path / "missing", tmp_path / "missing.zip")

    source_file = tmp_path / "file.txt"
    source_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(NotADirectoryError, match="ZIP source"):
        write_reproducible_zip(source_file, tmp_path / "file.zip")


def test_reproducible_zip_rejects_destination_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "content.txt").write_text("content", encoding="utf-8")
    destination = source / "release.zip"
    destination.write_bytes(b"existing output")

    with pytest.raises(ValueError, match="outside ZIP source"):
        write_reproducible_zip(source, destination)

    assert destination.read_bytes() == b"existing output"


def test_reproducible_zip_rejects_symlinked_source_members(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = source / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("this host does not permit test symlinks")

    with pytest.raises(ValueError, match="link or reparse"):
        write_reproducible_zip(source, tmp_path / "unsafe.zip")


def test_reproducible_zip_rejects_member_replaced_after_link_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    member = source / "payload.bin"
    replacement = tmp_path / "replacement.bin"
    member.write_bytes(b"trusted!")
    replacement.write_bytes(b"outside!")
    original_link_check = release_common._is_link_or_reparse
    swapped = False

    def replace_after_link_check(path: Path) -> bool:
        nonlocal swapped
        result = original_link_check(path)
        if path == member and not swapped:
            os.replace(replacement, member)
            swapped = True
        return result

    monkeypatch.setattr(release_common, "_is_link_or_reparse", replace_after_link_check)
    destination = tmp_path / "release.zip"

    with pytest.raises(ValueError, match="changed while reading|identity changed"):
        write_reproducible_zip(source, destination)

    assert swapped
    assert not destination.exists()


def test_reproducible_zip_rejects_child_directory_swapped_to_junction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction regression")
    source = tmp_path / "source"
    child = source / "nested"
    child.mkdir(parents=True)
    (child / "trusted.txt").write_text("trusted", encoding="utf-8")
    held_child = tmp_path / "held-nested"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    original_link_check = release_common._is_link_or_reparse
    swapped = False

    def replace_after_link_check(path: Path) -> bool:
        nonlocal swapped
        result = original_link_check(path)
        if path == child and not swapped:
            child.rename(held_child)
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(child), str(outside)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                held_child.rename(child)
                pytest.skip("this host does not permit test junctions")
            swapped = True
        return result

    monkeypatch.setattr(release_common, "_is_link_or_reparse", replace_after_link_check)
    destination = tmp_path / "release.zip"
    try:
        with pytest.raises(ValueError, match="link or reparse|changed while reading|identity changed"):
            write_reproducible_zip(source, destination)
        assert swapped
        assert not destination.exists()
    finally:
        if swapped:
            os.rmdir(child)
            held_child.rename(child)


def test_reproducible_zip_rejects_existing_directory_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "destination"
    destination.mkdir()

    with pytest.raises(IsADirectoryError, match="ZIP destination"):
        write_reproducible_zip(source, destination)


def test_reproducible_zip_rejects_unicode_normalized_member_collision(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "caf\u00e9.txt").write_text("composed", encoding="utf-8")
    (source / "cafe\u0301.txt").write_text("decomposed", encoding="utf-8")

    with pytest.raises(ValueError, match="portable path collision"):
        write_reproducible_zip(source, tmp_path / "collision.zip")


def test_reproducible_zip_rejects_unicode_normalized_directory_collision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "Caf\u00e9").mkdir(parents=True)
    (source / "cafe\u0301").mkdir()
    (source / "Caf\u00e9" / "one.txt").write_text("one", encoding="utf-8")
    (source / "cafe\u0301" / "two.txt").write_text("two", encoding="utf-8")

    with pytest.raises(ValueError, match="portable path collision"):
        write_reproducible_zip(source, tmp_path / "collision.zip")


def test_reproducible_zip_rejects_nfkc_windows_reserved_component(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "\uff23\uff2f\uff2e.txt").write_text("reserved", encoding="utf-8")

    with pytest.raises(ValueError, match="portable across supported hosts"):
        write_reproducible_zip(source, tmp_path / "reserved.zip")


@pytest.mark.parametrize("file_type", [stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR])
def test_reproducible_zip_rejects_existing_nonregular_destination_from_lstat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_type: int,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "content.txt").write_text("content", encoding="utf-8")
    destination = tmp_path / "release.zip"
    destination.write_bytes(b"existing archive")
    original_lstat = Path.lstat

    def special_lstat(path: Path) -> os.stat_result:
        details = original_lstat(path)
        if path == destination:
            values = list(details)
            values[0] = file_type | 0o600
            return os.stat_result(values)
        return details

    monkeypatch.setattr(Path, "lstat", special_lstat)

    with pytest.raises(ValueError, match="regular file"):
        write_reproducible_zip(source, destination)

    assert destination.read_bytes() == b"existing archive"


@pytest.mark.skipif(os.name == "nt", reason="POSIX FIFO destination")
def test_reproducible_zip_rejects_existing_fifo_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "release.zip"
    os.mkfifo(destination)  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="regular file"):
        write_reproducible_zip(source, destination)

    assert stat.S_ISFIFO(destination.lstat().st_mode)


@pytest.mark.skipif(os.name == "nt", reason="POSIX Unix-socket destination")
def test_reproducible_zip_rejects_existing_socket_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "release.zip"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:  # type: ignore[attr-defined]
        listener.bind(str(destination))

        with pytest.raises(ValueError, match="regular file"):
            write_reproducible_zip(source, destination)

        assert stat.S_ISSOCK(destination.lstat().st_mode)


def test_manifest_preserves_existing_output_and_cleans_temp_after_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "build-info.json"
    destination.write_bytes(b"existing manifest")
    identity = BuildIdentity(version="1.0.0", commit_sha="e" * 40, target="source")
    original_fdopen = os.fdopen

    class FailingWrite:
        def __init__(self, stream: BinaryIO) -> None:
            self._stream = stream

        def __enter__(self) -> FailingWrite:
            return self

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: object | None,
        ) -> None:
            self._stream.close()

        def write(self, payload: bytes) -> NoReturn:
            _ = payload
            raise OSError("injected temporary write failure")

    def failing_fdopen(descriptor: int, mode: str) -> FailingWrite:
        return FailingWrite(cast(BinaryIO, original_fdopen(descriptor, mode)))

    monkeypatch.setattr(os, "fdopen", failing_fdopen)

    with pytest.raises(OSError, match="temporary write failure"):
        write_build_manifest(destination, identity, ["content.txt"])

    assert destination.read_bytes() == b"existing manifest"
    assert list(tmp_path.glob(".build-info.json.*.tmp")) == []


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_manifest_preserves_existing_output_and_cleans_temp_after_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    destination = tmp_path / "build-info.json"
    destination.write_bytes(b"existing manifest")
    identity = BuildIdentity(version="1.0.0", commit_sha="e" * 40, target="source")

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise OSError(f"injected {failure_point} failure")

    monkeypatch.setattr(os, failure_point, fail)

    with pytest.raises(OSError, match=rf"{failure_point} failure"):
        write_build_manifest(destination, identity, ["content.txt"])

    assert destination.read_bytes() == b"existing manifest"
    assert list(tmp_path.glob(".build-info.json.*.tmp")) == []


@pytest.mark.parametrize("failure_point", ["compression", "fsync", "replace"])
def test_archive_preserves_existing_output_and_cleans_temp_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "content.txt").write_text("content" * 1_000, encoding="utf-8")
    destination = tmp_path / "release.zip"
    destination.write_bytes(b"existing archive")

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise OSError(f"injected {failure_point} failure")

    if failure_point == "compression":
        monkeypatch.setattr(zlib, "compressobj", fail)
    else:
        monkeypatch.setattr(os, failure_point, fail)

    with pytest.raises(OSError, match=rf"{failure_point} failure"):
        write_reproducible_zip(source, destination)

    assert destination.read_bytes() == b"existing archive"
    assert list(tmp_path.glob(".release.zip.*.tmp")) == []


def test_archive_preserves_existing_output_after_midstream_compression_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "content.txt").write_text("content" * 1_000, encoding="utf-8")
    destination = tmp_path / "release.zip"
    destination.write_bytes(b"existing archive")
    original_compressobj = zlib.compressobj

    class FailingCompressor:
        def __init__(self, level: int, method: int, wbits: int) -> None:
            self._compressor = original_compressobj(level, method, wbits)

        def compress(self, payload: bytes) -> NoReturn:
            _ = payload
            raise OSError("injected midstream compression failure")

        def flush(self, mode: int = zlib.Z_FINISH) -> bytes:
            return self._compressor.flush(mode)

    def failing_compressobj(
        level: int = -1,
        method: int = zlib.DEFLATED,
        wbits: int = zlib.MAX_WBITS,
    ) -> FailingCompressor:
        return FailingCompressor(level, method, wbits)

    monkeypatch.setattr(zlib, "compressobj", failing_compressobj)

    with pytest.raises(OSError, match="midstream compression failure"):
        write_reproducible_zip(source, destination)

    assert destination.read_bytes() == b"existing archive"
    assert list(tmp_path.glob(".release.zip.*.tmp")) == []
