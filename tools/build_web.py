"""Build the pinned Pygbag artifact from a runtime-only deterministic staging tree."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final, TypedDict

import pygame

# Direct script execution places ``tools/`` on sys.path, while CI invokes this file by path.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.release_common import (
    BuildIdentity,
    _directory_names,
    _DirectoryHandle,
    _entry_lstat,
    _protected_directory_chain,
    _verified_child_directory,
    _verified_regular_file,
    read_build_identity,
    write_build_manifest,
)
from tools.web_runtime import (
    RUNTIME_CDN_PATH,
    load_runtime_manifest,
    stage_runtime_assets,
    verify_same_origin_runtime_index,
)
from tools.web_source_manifest import inspect_runtime_source, runtime_source_files

ROOT: Final = Path(__file__).resolve().parents[1]
PYGBAG_VERSION: Final = "0.9.3"
PYGAME_CE_VERSION: Final = "2.5.7"
PYTHON_BUILD: Final = "3.12"
COMPRESSED_LIMIT_BYTES: Final = 30 * 1024 * 1024
_NORMALIZED_MTIME: Final = 946_684_800
_PROBE_CAPABILITY_MEMBER: Final = "assets/windsprig/_build_flags.py"
_DEFAULT_OUTPUT: Final = Path("dist/web")
_ALLOWED_BUILD_TARGETS: Final = frozenset({Path("build/web-stage"), Path("dist/web")})


class _OutputMeasurements(TypedDict):
    compressed_bytes: int
    files: list[str]
    uncompressed_bytes: int


type _PathIdentity = tuple[int, int, int]
type _ArtifactVisitor = Callable[[Path, BinaryIO, os.stat_result], None]


def verify_toolchain_versions() -> None:
    """Refuse to mutate build paths unless both installed web-tool versions are exact."""
    installed_pygbag = version("pygbag")
    if installed_pygbag != PYGBAG_VERSION:
        raise SystemExit(f"pygbag version drift: expected {PYGBAG_VERSION}, found {installed_pygbag}")
    installed_pygame = version("pygame-ce")
    if installed_pygame != PYGAME_CE_VERSION:
        raise SystemExit(f"pygame-ce version drift: expected {PYGAME_CE_VERSION}, found {installed_pygame}")


def generate_favicon(path: Path) -> None:
    """Generate Windsprig's original mint-and-gold leaf icon without external assets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = pygame.Surface((64, 64), flags=pygame.SRCALPHA)
    surface.fill((16, 35, 30, 255))
    mint = (121, 224, 180, 255)
    gold = (246, 201, 93, 255)
    pygame.draw.ellipse(surface, mint, pygame.Rect(13, 8, 38, 48))
    pygame.draw.polygon(surface, (76, 176, 142, 255), ((32, 9), (32, 55), (15, 42)))
    pygame.draw.line(surface, gold, (20, 53), (44, 16), width=4)
    pygame.draw.circle(surface, mint, (32, 32), 3)
    pygame.draw.circle(surface, gold, (45, 17), 5)
    pygame.image.save(surface, path)


def _probe_capability_source(probe: bool) -> bytes:
    return (
        f'"""Generated browser artifact capabilities; do not edit."""\n\nFOUNDATION_PROBE_AVAILABLE = {probe!r}\n'
    ).encode()


def stage_sources(root: Path, stage: Path, *, probe: bool) -> None:
    """Copy the canonical browser entry, runtime assets, package, and levels."""
    stage.mkdir(parents=True, exist_ok=False)
    lexical_root = Path(root).absolute()
    for source in runtime_source_files(lexical_root):
        relative = source.relative_to(lexical_root)
        destination = stage / source.name if relative.parent == Path("web") else stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (stage / "windsprig" / "_build_flags.py").write_bytes(_probe_capability_source(probe))
    if probe and not (stage / "windsprig" / "feasibility.py").is_file():
        raise SystemExit("probe build is missing windsprig/feasibility.py")


def _is_link_or_reparse(path: Path) -> bool:
    """Detect links, Windows junctions, and any other existing reparse point."""
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction) and isjunction(path):
        return True
    try:
        state = path.lstat()
    except FileNotFoundError:
        return False
    return _stat_is_link_or_reparse(state)


def _stat_is_link_or_reparse(state: os.stat_result) -> bool:
    """Classify a no-follow stat result without resolving its path again."""
    if stat.S_ISLNK(state.st_mode):
        return True
    attributes = getattr(state, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _remove_build_target(root: Path, relative_target: Path) -> None:
    """Remove one exact build target without following any link outside the repository."""
    relative = Path(relative_target)
    if relative.is_absolute() or relative.drive or relative not in _ALLOWED_BUILD_TARGETS:
        raise ValueError(f"refusing to clean non-allowlisted relative build target: {relative}")

    lexical_root = Path(root).absolute()
    candidate = lexical_root / relative
    components = [lexical_root]
    current = lexical_root
    for part in relative.parts:
        current /= part
        components.append(current)
    for component in components:
        if _is_link_or_reparse(component):
            raise ValueError(f"refusing to clean through link or reparse point: {component}")

    if not lexical_root.is_dir():
        raise ValueError(f"repository root is not an existing directory: {lexical_root}")
    resolved_root = lexical_root.resolve(strict=True)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"refusing to clean target that resolves outside repository root: {candidate}") from error
    if resolved_candidate != resolved_root / relative:
        raise ValueError(f"refusing to clean redirected build target: {candidate}")

    if candidate.exists():
        for component in components:
            if _is_link_or_reparse(component):
                raise ValueError(f"refusing to clean through link or reparse point: {component}")
        if not candidate.is_dir():
            raise ValueError(f"refusing to clean non-directory build target: {candidate}")
        shutil.rmtree(candidate)


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether either lexical path contains the other."""
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _validate_output_path_components(output: Path) -> None:
    """Reject a destination redirected through an existing link or reparse point."""
    for component in (output, *output.parents):
        if _is_link_or_reparse(component):
            raise ValueError(f"web output must not use a link or reparse point: {component}")


def _resolve_web_output(root: Path, output: Path | None) -> Path:
    """Resolve a safe lexical destination without deleting or creating anything."""
    if output is not None and not isinstance(output, Path):
        raise TypeError("output must be a pathlib.Path or None")

    lexical_root = Path(os.path.abspath(root))
    requested = _DEFAULT_OUTPUT if output is None else output
    if requested.is_absolute():
        destination = Path(os.path.abspath(requested))
    else:
        destination = Path(os.path.abspath(lexical_root / requested))
        if not destination.is_relative_to(lexical_root):
            raise ValueError(f"relative web output must stay inside the repository: {requested}")

    source = lexical_root / "web"
    stage = lexical_root / "build" / "web-stage"
    if _paths_overlap(destination, source) or _paths_overlap(destination, stage):
        raise ValueError(f"web output must not overlap source or staging directories: {destination}")
    _validate_output_path_components(destination)

    default_output = lexical_root / _DEFAULT_OUTPUT
    if destination != default_output and destination.exists():
        raise FileExistsError(
            f"custom web output already exists; choose a new path or remove it explicitly: {destination}"
        )
    return destination


def _path_identity(state: os.stat_result) -> _PathIdentity:
    return (state.st_dev, state.st_ino, stat.S_IFMT(state.st_mode))


def _prepare_web_output(root: Path, output: Path) -> _PathIdentity:
    """Prepare one empty destination parent and retain its stable identity."""
    default_output = Path(os.path.abspath(root)) / _DEFAULT_OUTPUT
    if output == default_output:
        _remove_build_target(root, _DEFAULT_OUTPUT)
    else:
        _validate_output_path_components(output)
        if output.exists():
            raise FileExistsError(
                f"custom web output already exists; choose a new path or remove it explicitly: {output}"
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    _validate_output_path_components(output)
    parent_state = output.parent.lstat()
    if not stat.S_ISDIR(parent_state.st_mode):
        raise NotADirectoryError(f"web output parent is not a directory: {output.parent}")
    if output.exists():
        raise FileExistsError(f"web output appeared while preparing the build: {output}")
    return _path_identity(parent_state)


def _visit_regular_artifact_files(root: Path, visitor: _ArtifactVisitor) -> None:
    """Visit regular files through verified no-follow parent and child handles."""
    try:
        root_state = root.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"web artifact directory does not exist: {root}") from None
    if _is_link_or_reparse(root):
        raise ValueError(f"web artifact contains a link or reparse point: {root}")
    if not stat.S_ISDIR(root_state.st_mode):
        raise NotADirectoryError(f"web artifact is not a directory: {root}")

    def visit(directory: _DirectoryHandle) -> None:
        for name in _directory_names(directory):
            path = directory.path / name
            try:
                current = _entry_lstat(directory, name)
            except OSError as error:
                raise ValueError(f"web artifact identity changed during traversal: {path}") from error
            if _stat_is_link_or_reparse(current):
                raise ValueError(f"web artifact contains a link or reparse point: {path}")
            if stat.S_ISDIR(current.st_mode):
                with _verified_child_directory(directory, name, path, current) as child:
                    visit(child)
            elif stat.S_ISREG(current.st_mode):
                with _verified_regular_file(directory, name, path, current) as (source, opened):
                    visitor(path, source, opened)
            else:
                raise ValueError(f"web artifact contains a non-regular entry: {path}")

    with _protected_directory_chain(root, expected_final=root_state) as root_directory:
        visit(root_directory)


def _regular_artifact_files(root: Path) -> list[Path]:
    """Enumerate regular artifact files without following links or reparse points."""
    files: list[Path] = []
    _visit_regular_artifact_files(root, lambda path, _source, _state: files.append(path))
    return files


def _normalize_source_times(stage: Path) -> None:
    for path in sorted(stage.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            os.utime(path, (_NORMALIZED_MTIME, _NORMALIZED_MTIME))


def _normalize_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as source:
        entries = [(info.filename, source.read(info.filename)) for info in source.infolist()]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            # CPython/WASM inflates large PCM members on the browser main
            # thread before the app can start. WAV payloads are already the
            # canonical release representation, so storing them trades a
            # modest archive-size increase for bounded extraction latency.
            info.compress_type = (
                zipfile.ZIP_STORED if PurePosixPath(name).suffix.casefold() == ".wav" else zipfile.ZIP_DEFLATED
            )
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, data)
    path.write_bytes(buffer.getvalue())


def _normalize_tar_gz(path: Path) -> None:
    entries: list[tuple[str, bytes]] = []
    with tarfile.open(path, mode="r:gz") as source:
        for member in source.getmembers():
            extracted = source.extractfile(member)
            if member.isfile() and extracted is not None:
                entries.append((member.name, extracted.read()))
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as target:
        for name, data in sorted(entries):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            target.addfile(info, io.BytesIO(data))
    path.write_bytes(gzip.compress(tar_buffer.getvalue(), compresslevel=9, mtime=0))


def _normalize_archives(output: Path) -> None:
    for path in sorted(output.glob("*.apk")):
        _normalize_zip(path)
    for path in sorted(output.glob("*.tar.gz")):
        _normalize_tar_gz(path)


def verify_probe_artifacts(output: Path, *, probe: bool) -> None:
    """Require both Pygbag archives to carry the requested immutable probe capability."""
    expected = _probe_capability_source(probe)
    apk_archives = sorted(output.glob("*.apk"))
    tar_archives = sorted(output.glob("*.tar.gz"))
    if not apk_archives or not tar_archives:
        raise SystemExit("probe capability verification requires both Pygbag archives")
    for archive_path in [*apk_archives, *tar_archives]:
        try:
            if archive_path.suffix == ".apk":
                with zipfile.ZipFile(archive_path, "r") as archive:
                    actual = archive.read(_PROBE_CAPABILITY_MEMBER)
            else:
                with tarfile.open(archive_path, mode="r:gz") as archive:
                    member = archive.extractfile(_PROBE_CAPABILITY_MEMBER)
                    if member is None:
                        raise KeyError(_PROBE_CAPABILITY_MEMBER)
                    actual = member.read()
        except (KeyError, tarfile.TarError, zipfile.BadZipFile) as error:
            raise SystemExit(
                f"probe capability is missing from packaged source manifest: {archive_path.name}"
            ) from error
        if actual != expected:
            raise SystemExit(f"probe capability mismatch in {archive_path.name}")


def prune_unused_pygbag_archives(output: Path) -> None:
    """Remove Pygbag's duplicate tarball only when the loader uses one APK.

    Probe verification runs first against both generated containers. This
    boundary then proves the final HTML names the APK and no longer names a
    tarball before removing transfer bytes that can never be consumed.
    """

    index = output / "index.html"
    html = index.read_text(encoding="utf-8")
    apk_archives = sorted(output.glob("*.apk"))
    tar_archives = sorted(output.glob("*.tar.gz"))
    if len(apk_archives) != 1 or apk_archives[0].name not in html:
        raise SystemExit("web loader must reference exactly one Pygbag APK")
    referenced_tarballs = tuple(path.name for path in tar_archives if path.name in html)
    if referenced_tarballs:
        raise SystemExit("web loader still references duplicate Pygbag archive: " + ", ".join(referenced_tarballs))
    for path in tar_archives:
        path.unlink()


def measure_output(output: Path) -> _OutputMeasurements:
    """Return canonical transfer totals from deterministic per-file gzip measurements."""
    compressed_bytes = 0
    files: list[str] = []
    uncompressed_bytes = 0

    def measure(path: Path, source: BinaryIO, state: os.stat_result) -> None:
        nonlocal compressed_bytes, uncompressed_bytes
        payload = source.read()
        compressed_bytes += len(gzip.compress(payload, compresslevel=9, mtime=0))
        files.append(path.relative_to(output).as_posix())
        uncompressed_bytes += state.st_size

    _visit_regular_artifact_files(output, measure)
    return {
        "compressed_bytes": compressed_bytes,
        "files": files,
        "uncompressed_bytes": uncompressed_bytes,
    }


def attach_release_manifest(output: Path, identity: BuildIdentity) -> Path:
    """Attach canonical release identity to a complete regular-file web artifact."""
    if not isinstance(output, Path):
        raise TypeError("output must be a pathlib.Path")
    if not isinstance(identity, BuildIdentity):
        raise TypeError("identity must be a BuildIdentity")
    if identity.target != "web":
        raise ValueError(f"identity target must be web, received {identity.target!r}")
    _validate_output_path_components(Path(os.path.abspath(output)))
    try:
        output_state = output.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"web output does not exist: {output}") from None
    if _is_link_or_reparse(output):
        raise ValueError(f"web output must not be a link or reparse point: {output}")
    if not stat.S_ISDIR(output_state.st_mode):
        raise NotADirectoryError(f"web output is not a directory: {output}")

    manifest_path = output / "build-info.json"
    index_path = output / "index.html"
    if _is_link_or_reparse(index_path) or not index_path.is_file():
        raise FileNotFoundError(f"Pygbag did not create a regular {index_path}")

    files = [path.relative_to(output).as_posix() for path in _regular_artifact_files(output) if path != manifest_path]

    if not any(Path(member).suffix == ".apk" for member in files):
        raise FileNotFoundError(f"Pygbag application archive is missing from {output}")
    write_build_manifest(manifest_path, identity, files)
    return manifest_path


def _atomic_rename_directory(
    source: Path,
    destination: Path,
    source_parent: _DirectoryHandle,
    destination_parent: _DirectoryHandle,
) -> None:
    """Rename a directory between already protected same-filesystem parents."""
    if os.name == "nt":
        os.replace(source, destination)
        return
    if os.rename not in os.supports_dir_fd:
        raise RuntimeError("atomic web publication requires rename dir_fd support")
    os.rename(
        source.name,
        destination.name,
        src_dir_fd=source_parent.descriptor,
        dst_dir_fd=destination_parent.descriptor,
    )


def _remove_artifact_tree_no_follow(path: Path) -> None:
    """Remove a quarantined tree while unlinking every reparse entry as a leaf."""
    try:
        state = path.lstat()
    except FileNotFoundError:
        return
    if _stat_is_link_or_reparse(state):
        if stat.S_ISDIR(state.st_mode) or getattr(os.path, "isjunction", lambda _path: False)(path):
            os.rmdir(path)
        else:
            path.unlink()
        return
    if stat.S_ISDIR(state.st_mode):
        for name in sorted(os.listdir(path)):
            _remove_artifact_tree_no_follow(path / name)
        path.rmdir()
        return
    if stat.S_ISREG(state.st_mode):
        path.unlink()
        return
    raise ValueError(f"cannot safely remove non-regular artifact entry: {path}")


def _rollback_published_output(
    staged: Path,
    output: Path,
    publication_error: BaseException,
) -> None:
    """Quarantine a rejected publication and remove it without following links."""
    try:
        with _protected_directory_chain(output.parent) as published_parent:
            with _protected_directory_chain(staged.parent) as quarantine_parent:
                if staged.exists() or _is_link_or_reparse(staged):
                    raise FileExistsError(f"web publication quarantine path appeared: {staged}")
                _atomic_rename_directory(
                    output,
                    staged,
                    published_parent,
                    quarantine_parent,
                )
    except BaseException as rollback_error:
        try:
            _remove_artifact_tree_no_follow(output)
        except BaseException as cleanup_error:
            raise RuntimeError(
                f"web publication failed and unsafe output could not be removed: {output}"
            ) from cleanup_error
        publication_error.add_note(f"atomic publication rollback failed: {rollback_error!r}")
        return

    try:
        _remove_artifact_tree_no_follow(staged)
    except BaseException as cleanup_error:
        publication_error.add_note(f"quarantined web output cleanup failed: {cleanup_error!r}")


def _publish_web_output(
    staged: Path,
    output: Path,
    expected_parent_identity: _PathIdentity,
) -> Path:
    """Atomically publish one verified same-filesystem tree behind protected parents."""
    _regular_artifact_files(staged)
    _validate_output_path_components(output)
    parent_state = output.parent.lstat()
    if _path_identity(parent_state) != expected_parent_identity:
        raise ValueError(f"web output parent identity changed during build: {output.parent}")
    if output.exists() or _is_link_or_reparse(output):
        raise FileExistsError(f"web output appeared during the build: {output}")

    published = False
    try:
        # Task 1's descriptor chain denies delete sharing on Windows. On POSIX,
        # its directory descriptors target the verified parents directly.
        with _protected_directory_chain(staged.parent) as source_parent:
            with _protected_directory_chain(output.parent) as destination_parent:
                _validate_output_path_components(output)
                current_parent = output.parent.lstat()
                if _path_identity(current_parent) != expected_parent_identity:
                    raise ValueError(f"web output parent identity changed during build: {output.parent}")
                if output.exists() or _is_link_or_reparse(output):
                    raise FileExistsError(f"web output appeared during the build: {output}")

                staged_state = staged.lstat()
                if _is_link_or_reparse(staged) or not stat.S_ISDIR(staged_state.st_mode):
                    raise ValueError(f"staged web output is not a regular directory: {staged}")
                if staged_state.st_dev != current_parent.st_dev:
                    raise OSError(f"atomic web publication requires output on the build filesystem: {output}")
                _regular_artifact_files(staged)
                _atomic_rename_directory(
                    staged,
                    output,
                    source_parent,
                    destination_parent,
                )
                published = True

                _validate_output_path_components(output)
                if _path_identity(output.parent.lstat()) != expected_parent_identity:
                    raise ValueError(f"web output parent identity changed during publication: {output.parent}")
                _regular_artifact_files(output)
    except BaseException as error:
        if published:
            _rollback_published_output(staged, output, error)
        raise
    return output


def build_web(probe: bool, output: Path | None = None) -> dict[str, object]:
    """Build a pinned Pygbag artifact and emit canonical size and release metadata."""
    root = ROOT
    source = root / "web"
    stage = root / "build" / "web-stage"
    output_path = _resolve_web_output(root, output)
    verify_toolchain_versions()
    generate_favicon(source / "favicon.png")
    runtime_manifest = inspect_runtime_source(root)
    browser_runtime_manifest = load_runtime_manifest(source / "runtime-manifest.json")
    _remove_build_target(root, Path("build/web-stage"))
    output_parent_identity = _prepare_web_output(root, output_path)
    stage_sources(root, stage, probe=probe)
    _normalize_source_times(stage)

    command = [
        sys.executable,
        "-m",
        "pygbag",
        "--build",
        "--disable-sound-format-error",
        "--no_opt",
        "--ume_block",
        "0",
        "--can_close",
        "1",
        "--PYBUILD",
        PYTHON_BUILD,
        "--width",
        "1280",
        "--height",
        "720",
        "--package",
        "web.pygame.windsprig",
        "--title",
        "Windsprig: Echoes of the Gale",
        "--cdn",
        RUNTIME_CDN_PATH,
        "--template",
        str(stage / "template.tmpl"),
        "--icon",
        str(stage / "favicon.png"),
        str(stage),
    ]
    subprocess.run(command, cwd=root, check=True)
    built = stage / "build" / "web"
    if not (built / "index.html").is_file():
        raise SystemExit(f"Pygbag did not produce {built / 'index.html'}")
    browser_runtime_bytes = stage_runtime_assets(
        browser_runtime_manifest,
        root / "build" / "web-runtime-cache",
        built,
    )
    verify_same_origin_runtime_index(built / "index.html")
    _normalize_archives(built)
    verify_probe_artifacts(built, probe=probe)
    prune_unused_pygbag_archives(built)
    measurements = measure_output(built)
    identity = read_build_identity(root, "web")
    if identity.commit_sha != runtime_manifest.source_commit:
        raise SystemExit("repository HEAD changed during the web build")
    final_runtime_manifest = inspect_runtime_source(root)
    if final_runtime_manifest != runtime_manifest:
        raise SystemExit("runtime source or build recipe changed during the web build")
    report: dict[str, object] = {
        **measurements,
        "browser_runtime_bytes": browser_runtime_bytes,
        "browser_runtime_manifest_sha256": browser_runtime_manifest.sha256,
        "compressed_limit_bytes": COMPRESSED_LIMIT_BYTES,
        "probe": probe,
        "pygbag": PYGBAG_VERSION,
        "pygame_ce": PYGAME_CE_VERSION,
        "python_build": PYTHON_BUILD,
        "release_version": identity.version,
        "runtime_manifest_sha256": runtime_manifest.sha256,
        "source_commit": identity.commit_sha,
    }
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "web-build.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if measurements["compressed_bytes"] > COMPRESSED_LIMIT_BYTES:
        raise SystemExit("compressed web transfer exceeds 30 MiB")
    attach_release_manifest(built, identity)
    _publish_web_output(built, output_path, output_parent_identity)
    print(f"web output: {output_path}")
    print(f"compressed bytes: {measurements['compressed_bytes']}")
    return report


def main() -> int:
    """Parse web build flags and run the deterministic Pygbag staging flow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    build_web(probe=args.probe, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
