"""Deterministic procedural-art generation contracts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import generate_art

PYTHON = Path(os.environ.get("WINDSPRIG_TEST_PYTHON", os.sys.executable))
ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/generate_art.py"
_REAL_SUBPROCESS_RUN = subprocess.run


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


def _run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["SDL_VIDEODRIVER"] = "dummy"
    environment["SDL_AUDIODRIVER"] = "dummy"
    return subprocess.run(
        [str(PYTHON), str(SCRIPT), *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_generation_is_pixel_stable_and_check_never_writes(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()

    generated = _run("--root", str(publication), cwd=ROOT)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert "art: 52 PNGs, 56 player frames, 18 enemies, 6 bosses, 6 world sets" in generated.stdout

    first = _snapshot(publication)
    checked = _run("--root", str(publication), "--check", cwd=ROOT)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert _snapshot(publication) == first
    checked_again = _run("--root", str(publication), "--check", cwd=ROOT)
    assert checked_again.returncode == 0, checked_again.stdout + checked_again.stderr
    assert _snapshot(publication) == first

    target = publication / "assets/generated/enemies/breezeling.png"
    target.write_bytes(b"not a png")
    (publication / "assets/generated/enemies/bramblekin.png").unlink()
    shutil.copy2(
        publication / "assets/generated/ui/favicon.png",
        publication / "assets/generated/ui/unexpected.png",
    )
    provenance_path = publication / "assets/generated/art-provenance.json"
    provenance_path.write_text("{}\n", encoding="utf-8")
    manifest_path = publication / "windsprig/content/assets.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["art"].pop("enemy.breezeling")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    stale = _snapshot(publication)
    rejected = _run("--root", str(publication), "--check", cwd=ROOT)
    assert rejected.returncode == 1
    assert "STALE art enemy.breezeling" in rejected.stdout
    assert "STALE art enemy.bramblekin" in rejected.stdout
    assert "UNEXPECTED art generated/ui/unexpected.png" in rejected.stdout
    assert "STALE provenance: canonical JSON" in rejected.stdout
    assert "STALE manifest: canonical JSON" in rejected.stdout
    assert _snapshot(publication) == stale


def test_check_rejects_noncanonical_manifest_bytes_without_writing(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    generate_art.generate(publication)
    manifest_path = publication / "windsprig/content/assets.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    before = _snapshot(publication)

    rejected = _run("--root", str(publication), "--check", cwd=ROOT)

    assert rejected.returncode == 1
    assert rejected.stdout == "STALE manifest: canonical JSON\n"
    assert _snapshot(publication) == before


def test_check_rejects_noncanonical_provenance_bytes_without_writing(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    generate_art.generate(publication)
    provenance_path = publication / "assets/generated/art-provenance.json"
    document = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance_path.write_text(json.dumps(document, indent=4, sort_keys=False), encoding="utf-8")
    before = _snapshot(publication)

    rejected = _run("--root", str(publication), "--check", cwd=ROOT)

    assert rejected.returncode == 1
    assert rejected.stdout == "STALE provenance: canonical JSON\n"
    assert _snapshot(publication) == before


def test_generation_preserves_future_audio_records_and_files(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    generate_art.generate(publication)
    audio_path = publication / "assets/generated/audio/keep.wav"
    audio_path.parent.mkdir()
    audio_path.write_bytes(b"future deterministic audio")
    audio_provenance = publication / "assets/generated/audio-provenance.json"
    audio_provenance.write_text("{}\n", encoding="utf-8")
    manifest_path = publication / "windsprig/content/assets.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["audio"] = {
        "sfx.keep": {
            "bus": "sfx",
            "mandatory": True,
            "path": "generated/audio/keep.wav",
            "sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        }
    }
    document["provenance_files"].append("generated/audio-provenance.json")
    manifest_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    generate_art.generate(publication)

    regenerated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert regenerated["audio"] == document["audio"]
    assert regenerated["provenance_files"] == [
        "generated/art-provenance.json",
        "generated/audio-provenance.json",
    ]
    assert audio_path.read_bytes() == b"future deterministic audio"


def test_visual_qa_montages_cover_every_art_family(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    entries = generate_art.generate(publication)

    montages = generate_art.write_montages(publication, entries)

    assert [path.name for path in montages] == [
        "sprig-states.png",
        "enemy-boss-silhouettes.png",
        "world-sets.png",
        "ui-launch-art.png",
    ]
    assert all(path.is_file() and path.stat().st_size > 1_000 for path in montages)


def test_publication_rolls_back_every_owned_output_on_manifest_swap_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    generate_art.generate(publication)
    before = _snapshot(publication)
    manifest_target = publication / "windsprig/content/assets.json"
    real_replace = generate_art._replace
    failed = False

    def fail_manifest_swap(source: Path, destination: Path) -> None:
        nonlocal failed
        if destination == manifest_target and not failed:
            failed = True
            raise OSError("injected manifest publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(generate_art, "_replace", fail_manifest_swap)

    with pytest.raises(OSError, match="injected manifest publication failure"):
        generate_art.generate(publication)

    assert failed
    assert _snapshot(publication) == before


def test_publication_rejects_an_owned_directory_link_without_touching_its_target(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    generate_art.generate(publication)
    target = publication / "assets/generated/enemies"
    shutil.rmtree(target)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("do not touch\n", encoding="utf-8")
    _make_directory_link(target, outside)
    try:
        with pytest.raises(ValueError, match="publication target is unsafe"):
            generate_art.generate(publication)

        assert sentinel.read_text(encoding="utf-8") == "do not touch\n"
        assert list(outside.iterdir()) == [sentinel]
    finally:
        _remove_directory_link(target)


@pytest.mark.parametrize("linked_relative", [Path("assets/generated"), Path("windsprig/content")])
def test_generation_rejects_linked_read_parents_before_loading_outside(
    tmp_path: Path,
    linked_relative: Path,
) -> None:
    publication = tmp_path / "publication"
    publication.mkdir()
    generate_art.generate(publication)
    linked = publication / linked_relative
    outside = tmp_path / f"outside-{linked_relative.name}"
    linked.rename(outside)
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside stays unchanged\n", encoding="utf-8")
    _make_directory_link(linked, outside)
    try:
        with pytest.raises(ValueError, match="unsafe"):
            generate_art.check(publication)
        assert sentinel.read_text(encoding="utf-8") == "outside stays unchanged\n"
    finally:
        _remove_directory_link(linked)
        shutil.rmtree(outside)
