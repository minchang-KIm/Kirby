"""Windows package, metadata, smoke, and archive release contracts."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools.build_windows import (
    release_build_environment,
    require_clean_release_source,
    stage_windows_release,
)
from tools.release_common import BuildIdentity, sha256_file
from windsprig.config import GameConfig
from windsprig.platform.native import NativeStorage, create_native_services

ROOT = Path(__file__).resolve().parents[2]


def test_stage_windows_release_contains_notices_metadata_and_hash(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "Windsprig.exe").write_bytes(b"exe")
    root = tmp_path / "root"
    root.mkdir()
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "CREDITS.md").write_text("Credits\n", encoding="utf-8")
    destination = tmp_path / "release"
    identity = BuildIdentity("1.0.0", "c" * 40, "windows")

    archive, checksum = stage_windows_release(bundle, root, destination, identity)

    assert archive.name == "Windsprig-1.0.0-windows-x64.zip"
    assert checksum.name == f"{archive.name}.sha256"
    assert checksum.read_text(encoding="ascii") == f"{sha256_file(archive)}  {archive.name}\n"
    manifest = json.loads((bundle / "build-info.json").read_text(encoding="utf-8"))
    assert manifest == {
        "commit_sha": "c" * 40,
        "files": ["CREDITS.md", "LICENSE", "Windsprig.exe", "build-info.json"],
        "target": "windows",
        "version": "1.0.0",
    }
    with zipfile.ZipFile(archive) as package:
        assert package.namelist() == manifest["files"]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in package.infolist())


def test_stage_windows_release_is_byte_stable_for_same_bundle(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "CREDITS.md").write_text("Credits\n", encoding="utf-8")
    identity = BuildIdentity("1.0.0", "d" * 40, "windows")
    hashes: list[str] = []
    for index in range(2):
        bundle = tmp_path / f"bundle-{index}"
        bundle.mkdir()
        (bundle / "Windsprig.exe").write_bytes(b"stable-exe")
        archive, _checksum = stage_windows_release(bundle, root, tmp_path / f"out-{index}", identity)
        hashes.append(sha256_file(archive))

    assert hashes[0] == hashes[1]


def test_windows_builder_rejects_modified_and_untracked_source(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Windsprig Test",
            "-c",
            "user.email=windsprig@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )

    require_clean_release_source(tmp_path)
    (tmp_path / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean Git worktree"):
        require_clean_release_source(tmp_path)
    (tmp_path / "untracked.txt").unlink()
    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean Git worktree"):
        require_clean_release_source(tmp_path)


def test_windows_builder_pins_hash_order_timestamp_and_local_cache() -> None:
    environment = release_build_environment(ROOT)
    commit_time = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert environment["PYTHONHASHSEED"] == "0"
    assert environment["SOURCE_DATE_EPOCH"] == commit_time
    assert environment["PYINSTALLER_CONFIG_DIR"] == str(ROOT / "build/pyinstaller-config")


def test_native_module_help_lists_isolated_smoke_arguments() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "windsprig", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--smoke-test" in result.stdout
    assert "--data-dir" in result.stdout


def test_native_smoke_refuses_to_touch_default_user_storage(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["LOCALAPPDATA"] = str(tmp_path / "user-data")
    result = subprocess.run(
        [sys.executable, "-m", "windsprig", "--smoke-test"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requires --data-dir" in result.stderr
    assert not (tmp_path / "user-data").exists()


def test_native_services_honor_resolved_isolated_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The explicit diagnostic root must win even when the user-data environment points elsewhere.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user-root"))
    requested = tmp_path / "portable" / ".." / "smoke data"

    services = create_native_services(GameConfig(), data_dir=requested)

    assert isinstance(services.storage, NativeStorage)
    assert services.storage.root == requested.resolve()
    assert services.storage.root.is_dir()


def test_windows_spec_and_metadata_are_product_bound() -> None:
    spec = (ROOT / "packaging/windows.spec").read_text(encoding="utf-8")
    version = (ROOT / "packaging/version_info.txt").read_text(encoding="utf-8")
    smoke = json.loads((ROOT / "packaging/smoke-config.json").read_text(encoding="utf-8"))

    assert "windsprig/__main__.py" in spec.replace("\\", "/")
    assert "assets" in spec and "windsprig/content" in spec
    assert "CREDITS.md" in spec and "LICENSE" in spec
    assert 'name="Windsprig"' in spec
    assert 'console=False' in spec
    assert all(token in version for token in ("Windsprig: Echoes of the Gale", "1.0.0.0", "Snowball_tree"))
    assert smoke == {"exit_code": 0, "expect_screen": "title", "frames": 3, "save_profile": "Package Smoke"}


def test_windows_spec_is_a_tracked_release_input() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "packaging/windows.spec"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, "a clean checkout would omit the supported Windows spec"


def test_windows_icon_is_a_canonical_embedded_copy_of_the_product_favicon() -> None:
    icon = (ROOT / "assets/branding/windsprig.ico").read_bytes()
    favicon = (ROOT / "assets/generated/ui/favicon.png").read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", icon)
    width, height, colors, entry_reserved, planes, bits, size, offset = struct.unpack_from("<BBBBHHII", icon, 6)

    assert (reserved, image_type, count) == (0, 1, 1)
    assert (width, height, colors, entry_reserved, planes, bits) == (192, 192, 0, 0, 1, 32)
    assert offset == 22
    assert size == len(favicon)
    assert icon[offset:] == favicon
    ledger = (ROOT / "assets/LICENSES.md").read_text(encoding="utf-8")
    assert "assets/branding/windsprig.ico" in ledger
    assert "tools/generate_windows_icon.py" in ledger


def test_windows_builder_invokes_current_python_and_packaged_smoke() -> None:
    builder = (ROOT / "tools/build_windows.py").read_text(encoding="utf-8")

    assert "sys.executable" in builder
    assert '"-m", "PyInstaller"' in builder
    assert '"--smoke-test"' in builder
    assert '"--data-dir"' in builder
    assert "TemporaryDirectory" in builder
