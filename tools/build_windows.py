"""Build, smoke-test, and archive the supported Windows x64 release."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Direct script execution places ``tools/`` on sys.path; release commands invoke this file by path.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.generate_windows_icon import generate_icon
from tools.release_common import (
    BuildIdentity,
    read_build_identity,
    sha256_file,
    write_build_manifest,
    write_reproducible_zip,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging/windows.spec"
SMOKE_CONFIG = ROOT / "packaging/smoke-config.json"
ICON_SOURCE = ROOT / "assets/generated/ui/favicon.png"
ICON = ROOT / "assets/branding/windsprig.ico"


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    """Validated expectations shared by the builder and packaged diagnostic."""

    exit_code: int
    expect_screen: str
    frames: int
    save_profile: str


def _write_checksum(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_clean_release_source(root: Path) -> None:
    """Reject source that cannot be bound exactly to the recorded Git identity."""

    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        raise RuntimeError("Windows release builds require a clean Git worktree")


def release_build_environment(root: Path) -> dict[str, str]:
    """Pin process entropy and PE timestamps to the source commit."""

    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    source_date_epoch = completed.stdout.strip()
    if not source_date_epoch.isascii() or not source_date_epoch.isdecimal():
        raise RuntimeError("Git returned an invalid source commit timestamp")
    environment = os.environ.copy()
    environment.update(
        {
            "PYINSTALLER_CONFIG_DIR": str(root / "build/pyinstaller-config"),
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": source_date_epoch,
        }
    )
    return environment


def stage_windows_release(
    bundle: Path,
    root: Path,
    destination: Path,
    identity: BuildIdentity,
) -> tuple[Path, Path]:
    """Attach notices and identity, then create one deterministic archive and checksum."""

    if not all(isinstance(path, Path) for path in (bundle, root, destination)):
        raise TypeError("bundle, root, and destination must be pathlib.Path values")
    if not isinstance(identity, BuildIdentity) or identity.target != "windows":
        raise ValueError("identity must describe the windows target")
    if not bundle.is_dir():
        raise NotADirectoryError(f"Windows bundle does not exist: {bundle}")
    if not root.is_dir():
        raise NotADirectoryError(f"release root does not exist: {root}")
    for name in ("LICENSE", "CREDITS.md"):
        source = root / name
        if not source.is_file():
            raise FileNotFoundError(f"required Windows notice does not exist: {source}")
        shutil.copy2(source, bundle / name)

    files = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file()
    }
    files.add("build-info.json")
    write_build_manifest(bundle / "build-info.json", identity, sorted(files))

    destination.mkdir(parents=True, exist_ok=True)
    archive = write_reproducible_zip(
        bundle,
        destination / f"Windsprig-{identity.version}-windows-x64.zip",
    )
    checksum = archive.with_suffix(f"{archive.suffix}.sha256")
    _write_checksum(checksum, f"{sha256_file(archive)}  {archive.name}\n")
    return archive, checksum


def _load_smoke_config(path: Path) -> SmokeConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "exit_code": 0,
        "expect_screen": "title",
        "frames": 3,
        "save_profile": "Package Smoke",
    }
    if payload != expected:
        raise ValueError(f"unsupported Windows smoke configuration: {payload!r}")
    return SmokeConfig(exit_code=0, expect_screen="title", frames=3, save_profile="Package Smoke")


def _verify_smoke_save(data_root: Path, expected_profile: str) -> None:
    save_path = data_root / "save_data.json"
    try:
        payload = json.loads(save_path.read_text(encoding="utf-8"))
        display_name = payload["profiles"][0]["display_name"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("packaged smoke did not produce a valid isolated save") from exc
    if display_name != expected_profile:
        raise RuntimeError("packaged smoke save profile does not match the release contract")


def build(output: Path) -> tuple[Path, Path]:
    """Build from tracked inputs, run the packaged smoke route, and stage release files."""

    if not isinstance(output, Path):
        raise TypeError("output must be a pathlib.Path")
    require_clean_release_source(ROOT)
    generate_icon(ICON_SOURCE, ICON, check=True)
    smoke = _load_smoke_config(SMOKE_CONFIG)
    identity = read_build_identity(ROOT, "windows")
    build_environment = release_build_environment(ROOT)
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build/pyinstaller"),
            str(SPEC),
        ],
        cwd=ROOT,
        env=build_environment,
        check=True,
    )
    bundle = ROOT / "dist/Windsprig"
    executable = bundle / "Windsprig.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce the expected executable: {executable}")

    with tempfile.TemporaryDirectory(prefix="Windsprig package smoke ") as temporary_name:
        data_root = Path(temporary_name).resolve()
        environment = os.environ.copy()
        environment.update({"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"})
        completed = subprocess.run(
            [str(executable), "--smoke-test", "--data-dir", str(data_root)],
            cwd=data_root,
            env=environment,
            check=False,
            timeout=30,
        )
        if completed.returncode != smoke.exit_code:
            raise RuntimeError(f"packaged smoke exited with {completed.returncode}")
        _verify_smoke_save(data_root, smoke.save_profile)

    return stage_windows_release(bundle, ROOT, output.resolve(), identity)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/release")
    args = parser.parse_args()
    archive, checksum = build(args.output)
    print(f"windows archive: {archive}")
    print(f"sha256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
