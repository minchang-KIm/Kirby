"""Deterministic Korean runtime-font subset and browser staging contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont

from tools import generate_font_subset, web_source_manifest

ROOT = Path(__file__).resolve().parents[3]
SOURCE_FONT = Path("assets/fonts/NotoSansKR[wght].ttf")
RUNTIME_FONT = Path("assets/fonts/WindsprigSansKR.ttf")


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_required_codepoints_cover_release_copy_ascii_and_all_modern_hangul() -> None:
    required = generate_font_subset.required_codepoints(ROOT)
    assert set(range(0x20, 0x7F)) <= required
    assert set(range(0xAC00, 0xD7A4)) <= required
    catalog_codepoints: set[int] = set()
    for locale in ("en", "ko"):
        catalog = json.loads((ROOT / f"windsprig/content/strings.{locale}.json").read_text(encoding="utf-8"))
        catalog_codepoints.update(ord(character) for value in catalog.values() for character in value)
    assert required == set(range(0x20, 0x7F)) | set(range(0xAC00, 0xD7A4)) | catalog_codepoints
    assert {ord(character) for character in "바람싹 메아리"} <= required


def test_committed_runtime_font_is_static_complete_and_materially_smaller() -> None:
    assert generate_font_subset.check(ROOT) == ()
    assert (ROOT / RUNTIME_FONT).stat().st_size < (ROOT / SOURCE_FONT).stat().st_size // 4

    font = TTFont(ROOT / RUNTIME_FONT, lazy=False)
    try:
        cmap = font.getBestCmap()
        assert cmap is not None
        assert generate_font_subset.required_codepoints(ROOT) == set(cmap)
        assert "fvar" not in font
        assert "gvar" not in font
    finally:
        font.close()


def test_check_rejects_drift_without_writing(tmp_path: Path) -> None:
    generate_font_subset.generate(tmp_path, source_root=ROOT)
    before = _tree_hashes(tmp_path)
    runtime_font = tmp_path / RUNTIME_FONT
    runtime_font.write_bytes(runtime_font.read_bytes() + b"tamper")
    tampered = _tree_hashes(tmp_path)

    assert generate_font_subset.check(tmp_path, source_root=ROOT) == ("STALE assets/fonts/WindsprigSansKR.ttf",)
    assert _tree_hashes(tmp_path) == tampered
    assert tampered != before


def test_browser_manifest_packages_subset_but_not_full_source_font() -> None:
    relative = {path.relative_to(ROOT).as_posix() for path in web_source_manifest.runtime_source_files(ROOT)}
    assert RUNTIME_FONT.as_posix() in relative
    assert SOURCE_FONT.as_posix() not in relative
