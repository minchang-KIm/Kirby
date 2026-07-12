"""Import-safe actionable content validation CLI contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.catalog import write_minimal_bundle, write_release_bundle
from tools import validate_content


def _write_supporting_catalogs(content: Path) -> None:
    (content / "assets.json").write_text(
        json.dumps(
            {
                "art": {},
                "audio": {},
                "font": {
                    "path": "fonts/NotoSansKR.ttf",
                    "license": "fonts/OFL-NotoSansKR.txt",
                    "mandatory": True,
                },
                "provenance_files": [],
            }
        ),
        encoding="utf-8",
    )
    (content / "strings.en.json").write_text(
        json.dumps(
            {
                "world.demo.name": "Demo",
                "world.demo.identity": "A proving ground",
                "stage.demo_01.name": "Demo",
                "stage.demo_01.intro": "Begin",
                "boss.demo.name": "Demo Boss",
                "reward.gallery.demo": "Demo Gallery",
            }
        ),
        encoding="utf-8",
    )
    (content / "strings.ko.json").write_text(
        json.dumps(
            {
                "world.demo.name": "데모",
                "world.demo.identity": "시험장",
                "stage.demo_01.name": "데모",
                "stage.demo_01.intro": "시작",
                "boss.demo.name": "데모 보스",
                "reward.gallery.demo": "데모 갤러리",
            }
        ),
        encoding="utf-8",
    )


def test_cli_distinguishes_schema_failure_with_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = validate_content.main(["--content", str(tmp_path), "--assets", str(tmp_path)])

    assert result == 2
    assert capsys.readouterr().out == (
        f"SCHEMA campaign: file not found: {tmp_path / 'campaign.json'}\nFAILED: content schema could not be loaded\n"
    )


def test_cli_reports_semantic_issues_with_exit_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = write_minimal_bundle(tmp_path / "content")
    _write_supporting_catalogs(content)

    result = validate_content.main(["--content", str(content), "--assets", str(tmp_path / "assets"), "--all"])

    assert result == 1
    output = capsys.readouterr().out
    assert "ERROR world_count campaign.worlds: expected 6, received 1\n" in output
    assert output.endswith(" validation errors\n")


def test_cli_reports_complete_release_success_with_exit_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content, asset_root = write_release_bundle(tmp_path)

    result = validate_content.main(["--content", str(content), "--assets", str(asset_root), "--all"])

    assert result == 0
    assert capsys.readouterr().out == (
        "OK: 6 worlds, 30 stages, 6 bosses, 90 motes, 2 locales, 28 music cues, 29 sfx cues, 0 duplicate layouts\n"
    )
