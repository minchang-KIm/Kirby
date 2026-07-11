"""Build the pinned Pygbag artifact from a runtime-only deterministic staging tree."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from importlib.metadata import version
from pathlib import Path
from typing import Final, TypedDict

import pygame

PYGBAG_VERSION: Final = "0.9.3"
PYGAME_CE_VERSION: Final = "2.5.7"
PYTHON_BUILD: Final = "3.12"
COMPRESSED_LIMIT_BYTES: Final = 30 * 1024 * 1024
PINNED_CDN: Final = f"https://pygame-web.github.io/cdn/{PYGBAG_VERSION}/"
_NORMALIZED_MTIME: Final = 946_684_800
_IGNORED_DIRS: Final = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "test", "tests"}
)
_ALLOWED_SUFFIXES: Final = frozenset(
    {".json", ".jpg", ".jpeg", ".ogg", ".otf", ".png", ".py", ".ttf", ".txt", ".webp"}
)
_SECRET_SUFFIXES: Final = frozenset({".key", ".p12", ".pem", ".pfx"})


class _OutputMeasurements(TypedDict):
    compressed_bytes: int
    files: list[str]
    uncompressed_bytes: int


def verify_toolchain_versions() -> None:
    """Refuse to mutate build paths unless both installed web-tool versions are exact."""
    installed_pygbag = version("pygbag")
    if installed_pygbag != PYGBAG_VERSION:
        raise SystemExit(
            f"pygbag version drift: expected {PYGBAG_VERSION}, found {installed_pygbag}"
        )
    installed_pygame = version("pygame-ce")
    if installed_pygame != PYGAME_CE_VERSION:
        raise SystemExit(
            f"pygame-ce version drift: expected {PYGAME_CE_VERSION}, found {installed_pygame}"
        )


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


def _is_runtime_file(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.startswith(".") or path.suffix.lower() in _SECRET_SUFFIXES:
        return False
    if any(token in lowered for token in ("credential", "secret")):
        return False
    return path.suffix.lower() in _ALLOWED_SUFFIXES


def _copy_runtime_tree(source: Path, target: Path) -> None:
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(source)
        if any(part.lower() in _IGNORED_DIRS for part in relative.parts):
            continue
        if not path.is_file() or not _is_runtime_file(path):
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def stage_sources(root: Path, stage: Path, *, probe: bool) -> None:
    """Copy only the browser entry, installable package, and level data into staging."""
    stage.mkdir(parents=True, exist_ok=False)
    web = root / "web"
    for filename in ("main.py", "template.tmpl", "favicon.png"):
        source = web / filename
        if not source.is_file():
            raise SystemExit(f"required web source is missing: {source}")
        shutil.copy2(source, stage / filename)
    _copy_runtime_tree(root / "windsprig", stage / "windsprig")
    _copy_runtime_tree(root / "levels", stage / "levels")
    if probe and not (stage / "windsprig" / "feasibility.py").is_file():
        raise SystemExit("probe build is missing windsprig/feasibility.py")


def _remove_build_path(path: Path, *, expected: Path) -> None:
    if path.resolve() != expected.resolve():
        raise ValueError(f"refusing to clean unexpected build path: {path}")
    if path.is_symlink():
        raise ValueError(f"refusing to clean symlinked build path: {path}")
    if path.exists():
        shutil.rmtree(path)


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


def measure_output(output: Path) -> _OutputMeasurements:
    """Return canonical transfer totals from deterministic per-file gzip measurements."""
    paths = sorted((path for path in output.rglob("*") if path.is_file()), key=lambda path: path.as_posix())
    files = [path.relative_to(output).as_posix() for path in paths]
    return {
        "compressed_bytes": sum(
            len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0)) for path in paths
        ),
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
    _remove_build_path(stage, expected=root / "build" / "web-stage")
    _remove_build_path(output, expected=root / "dist" / "web")
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
