"""Deterministic, no-follow, rollback-safe release-audio generation contracts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import generate_audio
from windsprig.content.loader import load_asset_manifest

ROOT = Path(__file__).resolve().parents[3]
_REAL_SUBPROCESS_RUN = subprocess.run


def _seed_publication(root: Path) -> None:
    manifest = root / "windsprig/content/assets.json"
    manifest.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "windsprig/content/assets.json", manifest)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        if os.name != "nt":
            pytest.skip(f"directory links are unavailable: {error}")
        junction = _REAL_SUBPROCESS_RUN(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            pytest.skip(f"directory links are unavailable: {error}; {junction.stderr}")


def _remove_directory_link(link: Path) -> None:
    if getattr(os.path, "isjunction", lambda _path: False)(link):
        os.rmdir(link)
    elif link.is_symlink():
        link.unlink()


def test_generation_is_byte_stable_and_two_checks_perform_zero_writes(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)
    baseline_manifest = load_asset_manifest(publication / "windsprig/content/assets.json")

    first_entries = generate_audio.generate(publication)
    first = _snapshot(publication)
    second_entries = generate_audio.generate(publication)
    second = _snapshot(publication)

    assert len(first_entries) == len(second_entries) == 57
    assert first == second
    assert generate_audio.check(publication) == ()
    assert _snapshot(publication) == second
    assert generate_audio.check(publication) == ()
    assert _snapshot(publication) == second

    regenerated = load_asset_manifest(publication / "windsprig/content/assets.json")
    assert regenerated.art == baseline_manifest.art
    assert regenerated.font == baseline_manifest.font
    assert regenerated.provenance_files == (
        "generated/art-provenance.json",
        "generated/audio-provenance.json",
    )


def test_check_reports_all_missing_corrupt_unexpected_and_noncanonical_outputs_without_writes(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)
    generate_audio.generate(publication)

    (publication / "assets/generated/audio/music/title.wav").write_bytes(b"not a wav")
    (publication / "assets/generated/audio/sfx/ui-confirm.wav").unlink()
    unexpected = publication / "assets/generated/audio/sfx/unexpected.wav"
    unexpected.write_bytes(b"unexpected")
    provenance_path = publication / "assets/generated/audio-provenance.json"
    provenance_path.write_text("{}\n", encoding="utf-8")
    manifest_path = publication / "windsprig/content/assets.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    before = _snapshot(publication)

    findings = generate_audio.check(publication)

    assert findings == tuple(sorted(findings))
    assert "STALE audio music.title: unreadable WAV" in findings
    assert "STALE audio sfx.ui.confirm: missing or unsafe" in findings
    assert "UNEXPECTED audio generated/audio/sfx/unexpected.wav" in findings
    assert "STALE manifest: canonical JSON" in findings
    assert "STALE provenance: canonical JSON" in findings
    assert _snapshot(publication) == before


@pytest.mark.parametrize("target_name", ["manifest", "provenance"])
def test_check_rejects_noncanonical_json_bytes_without_writing(tmp_path: Path, target_name: str) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)
    generate_audio.generate(publication)
    path = (
        publication / "windsprig/content/assets.json"
        if target_name == "manifest"
        else publication / "assets/generated/audio-provenance.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    before = _snapshot(publication)

    assert generate_audio.check(publication) == (f"STALE {target_name}: canonical JSON",)
    assert _snapshot(publication) == before


def test_publication_rolls_back_every_owned_output_when_the_manifest_swap_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)
    generate_audio.generate(publication)
    before = _snapshot(publication)
    manifest_target = publication / "windsprig/content/assets.json"
    real_replace = generate_audio._replace
    failed = False

    def fail_manifest_swap(source: Path, destination: Path) -> None:
        nonlocal failed
        if destination == manifest_target and "stage" in source.parts and not failed:
            failed = True
            raise OSError("injected manifest swap failure")
        real_replace(source, destination)

    monkeypatch.setattr(generate_audio, "_replace", fail_manifest_swap)

    with pytest.raises(OSError, match="injected manifest swap failure"):
        generate_audio.generate(publication)

    assert failed
    assert _snapshot(publication) == before


def test_generation_rejects_a_linked_audio_directory_without_touching_its_target(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)
    generated = publication / "assets/generated"
    generated.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.wav"
    sentinel.write_bytes(b"outside stays unchanged")
    audio_link = generated / "audio"
    _make_directory_link(audio_link, outside)
    try:
        with pytest.raises(ValueError, match="audio publication target is unsafe"):
            generate_audio.generate(publication)
        assert sentinel.read_bytes() == b"outside stays unchanged"
        assert list(outside.iterdir()) == [sentinel]
    finally:
        _remove_directory_link(audio_link)


def test_check_rejects_linked_read_paths_without_writing_inside_or_outside(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)
    generate_audio.generate(publication)
    audio = publication / "assets/generated/audio"
    displaced = publication / "assets/generated/audio-real"
    audio.rename(displaced)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.wav"
    sentinel.write_bytes(b"outside stays unchanged")
    _make_directory_link(audio, outside)
    before_publication = _snapshot(publication)
    before_outside = _snapshot(outside)
    try:
        with pytest.raises(ValueError, match="audio read path is unsafe"):
            generate_audio.check(publication)
        assert _snapshot(publication) == before_publication
        assert _snapshot(outside) == before_outside
    finally:
        _remove_directory_link(audio)
        displaced.rename(audio)


def test_check_mode_never_creates_missing_publication_directories(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    before = _snapshot(publication)

    with pytest.raises(FileNotFoundError, match="asset manifest"):
        generate_audio.check(publication)

    assert _snapshot(publication) == before
    assert list(publication.iterdir()) == []


def test_cli_prints_the_exact_release_inventory_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    _seed_publication(publication)

    assert generate_audio.main(["--root", str(publication)]) == 0
    assert capsys.readouterr().out == "audio: 28 music loops, 29 sfx, 22050 Hz mono PCM\n"
    before = _snapshot(publication)
    assert generate_audio.main(["--root", str(publication), "--check"]) == 0
    assert capsys.readouterr().out == "audio: 28 music loops, 29 sfx, 22050 Hz mono PCM\n"
    assert _snapshot(publication) == before
