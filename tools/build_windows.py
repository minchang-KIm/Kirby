"""Build, smoke-test, and archive the supported Windows x64 release."""

# Local imports intentionally occur only after the isolated recipe preflight.
# ruff: noqa: E402

from __future__ import annotations

import sys

if __name__ == "__main__" and not sys.flags.isolated:
    raise SystemExit("release Windows builds require: python -I tools/build_windows.py")

import argparse
import importlib.util
import io
import json
import marshal
import os
import shutil
import subprocess
import tarfile
import tempfile
import tokenize
import types
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def _normalized_tool_code(code: types.CodeType) -> types.CodeType:
    """Erase path variance while retaining every executable code field."""

    return code.replace(
        co_filename="<tracked-tool-source>",
        co_consts=tuple(
            _normalized_tool_code(value) if isinstance(value, types.CodeType) else value for value in code.co_consts
        ),
    )


def _preflight_tool_bytecode(tools_root: Path) -> None:
    """Reject any ignored build-tool bytecode that does not equal tracked source."""

    for cache in sorted(tools_root.rglob("*.pyc"), key=lambda path: path.as_posix()):
        try:
            source = Path(importlib.util.source_from_cache(str(cache))).absolute()
            expected_cache = Path(importlib.util.cache_from_source(str(source))).absolute()
            if cache.absolute() != expected_cache or not source.is_file():
                raise ValueError
            payload = cache.read_bytes()
            if len(payload) < 17 or payload[:4] != importlib.util.MAGIC_NUMBER:
                raise ValueError
            cached_code = marshal.loads(payload[16:])
            if not isinstance(cached_code, types.CodeType):
                raise ValueError
            with tokenize.open(source) as stream:
                source_text = stream.read()
            source_code = compile(
                source_text,
                str(source),
                "exec",
                dont_inherit=True,
                optimize=sys.flags.optimize,
            )
        except (EOFError, OSError, TypeError, ValueError) as error:
            relative = cache.relative_to(tools_root.parent).as_posix()
            raise SystemExit(f"unverifiable build-tool bytecode: {relative}") from error
        if _normalized_tool_code(cached_code) != _normalized_tool_code(source_code):
            relative = cache.relative_to(tools_root.parent).as_posix()
            raise SystemExit(f"divergent build-tool bytecode: {relative}")


def _preflight_build_recipe(root: Path) -> None:
    """Bind every executable build helper before its first local import."""

    lexical_root = Path(root).absolute()
    tools_root = lexical_root / "tools"
    if not tools_root.is_dir() or tools_root.is_symlink():
        raise SystemExit("build-tool preflight requires a regular tools directory")
    _preflight_tool_bytecode(tools_root)
    try:
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                "pyproject.toml",
                "uv.lock",
                "tools",
            ],
            cwd=lexical_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        tracked = frozenset(
            value
            for value in subprocess.run(
                ["git", "ls-files", "-z", "--", "pyproject.toml", "uv.lock", "tools"],
                cwd=lexical_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.split("\0")
            if value
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemExit("build-tool provenance preflight failed") from error
    if status:
        raise SystemExit("build recipe source is dirty before local imports")
    physical = {
        path.relative_to(lexical_root).as_posix()
        for path in tools_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    physical.update({"pyproject.toml", "uv.lock"})
    missing = tuple(sorted(physical - tracked))
    if missing:
        raise SystemExit("build recipe source is not tracked before local imports: " + ", ".join(missing))
    sys.dont_write_bytecode = True


if __name__ == "__main__":
    _preflight_build_recipe(ROOT)

if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from tools.generate_windows_icon import generate_icon
from tools.release_common import (
    BuildIdentity,
    read_build_identity,
    sha256_file,
    write_build_manifest,
    write_reproducible_zip,
)

SMOKE_CONFIG = ROOT / "packaging/smoke-config.json"
ICON_SOURCE = ROOT / "assets/generated/ui/favicon.png"
ICON = ROOT / "assets/branding/windsprig.ico"
_STAGED_EXACT_FILES = frozenset(
    {
        "CREDITS.md",
        "LICENSE",
        "packaging/version_info.txt",
        "packaging/windows.spec",
    }
)
_STAGED_ROOTS = frozenset({"assets", "windsprig"})
_ASSET_SUFFIXES = frozenset({".ico", ".json", ".md", ".png", ".ttf", ".txt", ".wav"})
_PACKAGE_SUFFIXES = frozenset({".json", ".py"})


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
    """Reject tracked or non-ignored source that does not equal the recorded Git identity."""

    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.stdout:
        raise RuntimeError("Windows release builds require a clean Git worktree")


def release_build_environment(root: Path) -> dict[str, str]:
    """Pin process entropy and scrub ambient Python/PyInstaller behavior."""

    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    source_date_epoch = completed.stdout.strip()
    if not source_date_epoch.isascii() or not source_date_epoch.isdecimal():
        raise RuntimeError("Git returned an invalid source commit timestamp")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("PYTHON")
        and not key.upper().startswith("PYINSTALLER_")
        and key.upper() != "SOURCE_DATE_EPOCH"
    }
    environment.update(
        {
            "PYINSTALLER_CONFIG_DIR": str(root / "build/pyinstaller-config"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONOPTIMIZE": "0",
            "PYTHONUTF8": "1",
            "SOURCE_DATE_EPOCH": source_date_epoch,
        }
    )
    return environment


def _stage_member_path(name: str, *, is_dir: bool = False) -> PurePosixPath:
    candidate = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or candidate.is_absolute()
        or candidate.as_posix() != name
        or any(part in {"", ".", "..", "__pycache__"} or part.startswith(".") for part in candidate.parts)
    ):
        raise ValueError(f"Git release member is not canonical: {name!r}")
    relative = candidate.as_posix()
    if relative in {"assets", "packaging", "windsprig"}:
        return candidate
    if relative in _STAGED_EXACT_FILES:
        return candidate
    root = candidate.parts[0]
    if root not in _STAGED_ROOTS:
        raise ValueError(f"unexpected Git release member: {relative}")
    if len(candidate.parts) == 1:
        return candidate
    if is_dir:
        return candidate
    suffix = Path(candidate.name).suffix.lower()
    allowed = _ASSET_SUFFIXES if root == "assets" else _PACKAGE_SUFFIXES
    if suffix not in allowed:
        raise ValueError(f"unsupported Git release member type: {relative}")
    return candidate


def _portable_stage_key(path: PurePosixPath) -> str:
    return "/".join(unicodedata.normalize("NFKC", part).casefold() for part in path.parts)


def stage_windows_source(root: Path, destination: Path) -> tuple[str, ...]:
    """Materialize the immutable tracked runtime tree directly from the HEAD object."""

    if not isinstance(root, Path) or not isinstance(destination, Path):
        raise TypeError("root and destination must be pathlib.Path values")
    if destination.exists():
        raise FileExistsError(f"Windows source stage already exists: {destination}")
    completed = subprocess.run(
        [
            "git",
            "archive",
            "--format=tar",
            "HEAD",
            "--",
            "assets",
            "windsprig",
            "CREDITS.md",
            "LICENSE",
            "packaging/version_info.txt",
            "packaging/windows.spec",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=60,
    )
    destination.mkdir(parents=True, exist_ok=False)
    files: list[str] = []
    registered: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive:
            path = _stage_member_path(member.name.rstrip("/"), is_dir=member.isdir())
            relative = path.as_posix()
            portable = _portable_stage_key(path)
            previous = registered.setdefault(portable, relative)
            if previous != relative:
                raise ValueError(f"portable Windows source collision: {previous!r} and {relative!r}")
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isreg():
                raise ValueError(f"Windows source member must be a regular file: {relative}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Windows source member has no payload: {relative}")
            payload = source.read()
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
            target.chmod(0o644)
            files.append(relative)
    required = _STAGED_EXACT_FILES | {"windsprig/__main__.py", "assets/branding/windsprig.ico"}
    missing = sorted(required - set(files))
    if missing:
        raise ValueError(f"Windows source stage is missing required tracked files: {missing}")
    return tuple(sorted(files))


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
    files = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
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
    expected = {"exit_code": 0, "expect_screen": "title", "frames": 3, "save_profile": "Package Smoke"}
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
    """Build only committed inputs, run packaged smoke, and stage release files."""

    if not isinstance(output, Path):
        raise TypeError("output must be a pathlib.Path")
    require_clean_release_source(ROOT)
    generate_icon(ICON_SOURCE, ICON, check=True)
    smoke = _load_smoke_config(SMOKE_CONFIG)
    identity = read_build_identity(ROOT, "windows")
    build_environment = release_build_environment(ROOT)
    build_root = ROOT / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=build_root, prefix="windows-stage-") as temporary_name:
        stage = Path(temporary_name) / "source"
        stage_windows_source(ROOT, stage)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--distpath",
                str(ROOT / "dist"),
                "--workpath",
                str(ROOT / "build/pyinstaller"),
                str(stage / "packaging/windows.spec"),
            ],
            cwd=stage,
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
