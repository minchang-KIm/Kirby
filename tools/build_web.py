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
from importlib.metadata import version
from pathlib import Path
from typing import Final, TypedDict

import pygame

from tools.web_source_manifest import inspect_runtime_source, runtime_source_files

PYGBAG_VERSION: Final = "0.9.3"
PYGAME_CE_VERSION: Final = "2.5.7"
PYTHON_BUILD: Final = "3.12"
COMPRESSED_LIMIT_BYTES: Final = 30 * 1024 * 1024
PINNED_CDN: Final = f"https://pygame-web.github.io/cdn/{PYGBAG_VERSION}/"
_NORMALIZED_MTIME: Final = 946_684_800
_PROBE_CAPABILITY_MEMBER: Final = "assets/windsprig/_build_flags.py"
_ALLOWED_BUILD_TARGETS: Final = frozenset({Path("build/web-stage"), Path("dist/web")})


class _OutputMeasurements(TypedDict):
    compressed_bytes: int
    files: list[str]
    uncompressed_bytes: int


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
    """Copy only the browser entry, installable package, and level data into staging."""
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
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
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
            info.compress_type = zipfile.ZIP_DEFLATED
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


def measure_output(output: Path) -> _OutputMeasurements:
    """Return canonical transfer totals from deterministic per-file gzip measurements."""
    paths = sorted((path for path in output.rglob("*") if path.is_file()), key=lambda path: path.as_posix())
    files = [path.relative_to(output).as_posix() for path in paths]
    return {
        "compressed_bytes": sum(len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0)) for path in paths),
        "files": files,
        "uncompressed_bytes": sum(path.stat().st_size for path in paths),
    }


def build_web(probe: bool) -> dict[str, object]:
    """Build ``dist/web`` with pinned Pygbag and emit a canonical size/version report."""
    root = Path(__file__).resolve().parents[1]
    source = root / "web"
    stage = root / "build" / "web-stage"
    output = root / "dist" / "web"
    verify_toolchain_versions()
    generate_favicon(source / "favicon.png")
    runtime_manifest = inspect_runtime_source(root)
    _remove_build_target(root, Path("build/web-stage"))
    _remove_build_target(root, Path("dist/web"))
    stage_sources(root, stage, probe=probe)
    _normalize_source_times(stage)

    command = [
        sys.executable,
        "-m",
        "pygbag",
        "--build",
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
        PINNED_CDN,
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
    _normalize_archives(built)
    verify_probe_artifacts(built, probe=probe)
    shutil.copytree(built, output)

    measurements = measure_output(output)
    report: dict[str, object] = {
        **measurements,
        "compressed_limit_bytes": COMPRESSED_LIMIT_BYTES,
        "probe": probe,
        "pygbag": PYGBAG_VERSION,
        "pygame_ce": PYGAME_CE_VERSION,
        "python_build": PYTHON_BUILD,
        "release_version": "1.0.0",
        "runtime_manifest_sha256": runtime_manifest.sha256,
        "source_commit": runtime_manifest.source_commit,
    }
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "web-build.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if measurements["compressed_bytes"] > COMPRESSED_LIMIT_BYTES:
        raise SystemExit("compressed web transfer exceeds 30 MiB")
    print(f"web output: {output}")
    print(f"compressed bytes: {measurements['compressed_bytes']}")
    return report


def main() -> int:
    """Parse the single probe flag and run the deterministic web build."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    build_web(probe=args.probe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
