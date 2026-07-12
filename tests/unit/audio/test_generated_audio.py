"""Committed PCM, manifest, provenance, and release-audio contracts."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import wave
from pathlib import Path

import pytest

from windsprig.audio.catalog import MUSIC_CUE_IDS, SFX_CUE_IDS
from windsprig.content.loader import load_asset_manifest, load_catalog_bundle, load_locales
from windsprig.content.validator import validate_bundle
from windsprig.render.assets import AssetCatalog

ROOT = Path(__file__).resolve().parents[3]
ASSET_ROOT = ROOT / "assets"
PROVENANCE_PATH = ASSET_ROOT / "generated/audio-provenance.json"
MANIFEST_PATH = ROOT / "windsprig/content/assets.json"
RATE = 22_050


def _provenance() -> dict[str, object]:
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


def _records() -> dict[str, dict[str, object]]:
    provenance = _provenance()
    music = provenance["music"]
    sfx = provenance["sfx"]
    assert isinstance(music, dict)
    assert isinstance(sfx, dict)
    return {**music, **sfx}


def _samples(path: Path) -> tuple[int, ...]:
    with wave.open(path.as_posix(), "rb") as source:
        payload = source.readframes(source.getnframes())
    return tuple(sample[0] for sample in struct.iter_unpack("<h", payload))


def _canonical_json(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def test_audio_catalog_has_the_exact_original_release_inventory() -> None:
    provenance = _provenance()
    manifest = load_asset_manifest(MANIFEST_PATH)
    music = provenance["music"]
    sfx = provenance["sfx"]
    assert isinstance(music, dict)
    assert isinstance(sfx, dict)

    assert set(music) == MUSIC_CUE_IDS
    assert set(sfx) == SFX_CUE_IDS
    assert len(music) == 28
    assert len(sfx) == 29
    assert set(manifest.audio) == MUSIC_CUE_IDS | SFX_CUE_IDS
    assert all(spec.mandatory for spec in manifest.audio.values())
    assert all(manifest.audio[cue_id].bus == "music" for cue_id in MUSIC_CUE_IDS)
    assert all(manifest.audio[cue_id].bus == "sfx" for cue_id in SFX_CUE_IDS)
    assert provenance["algorithm"] == "windsprig-additive-pcm-v1"
    assert provenance["generator"] == "tools/generate_audio.py"
    assert provenance["license"] == "Original project audio distributed under the root MIT license"
    assert provenance["schema_version"] == 1
    assert manifest.provenance_files == (
        "generated/art-provenance.json",
        "generated/audio-provenance.json",
    )


def test_every_wav_is_canonical_mono_signed_little_endian_pcm_with_exact_provenance() -> None:
    for cue_id, record in _records().items():
        relative = record["path"]
        assert isinstance(relative, str)
        path = ASSET_ROOT / relative
        payload = path.read_bytes()
        assert payload[:4] == b"RIFF"
        assert struct.unpack_from("<I", payload, 4)[0] == len(payload) - 8
        assert payload[8:12] == b"WAVE"
        assert payload[12:16] == b"fmt "
        assert struct.unpack_from("<I", payload, 16)[0] == 16
        assert struct.unpack_from("<HHIIHH", payload, 20) == (1, 1, RATE, RATE * 2, 2, 16)
        assert payload[36:40] == b"data"
        data_size = struct.unpack_from("<I", payload, 40)[0]
        assert len(payload) == 44 + data_size
        assert data_size % 2 == 0

        with wave.open(path.as_posix(), "rb") as source:
            assert source.getnchannels() == 1
            assert source.getsampwidth() == 2
            assert source.getframerate() == RATE
            assert source.getcomptype() == "NONE"
            frame_count = source.getnframes()
            pcm = source.readframes(frame_count)
            assert source.readframes(1) == b""

        assert len(pcm) == frame_count * 2 == data_size
        assert record == {
            **record,
            "algorithm": "windsprig-additive-pcm-v1",
            "channels": 1,
            "duration_seconds": pytest.approx(frame_count / RATE, abs=1e-9),
            "frame_count": frame_count,
            "license": "Original project audio distributed under the root MIT license",
            "path": relative,
            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "sample_rate": RATE,
            "sample_width_bytes": 2,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        assert set(record) >= {
            "algorithm",
            "channels",
            "duration_seconds",
            "frame_count",
            "license",
            "parameters",
            "path",
            "pcm_sha256",
            "phase",
            "sample_rate",
            "sample_width_bytes",
            "seed",
            "sha256",
            "theme",
        }
        assert record["sha256"] == load_asset_manifest(MANIFEST_PATH).audio[cue_id].sha256


def test_generated_pcm_has_controlled_levels_silent_seams_and_no_duplicate_cues() -> None:
    pcm_hashes: set[str] = set()
    for cue_id, record in _records().items():
        path = ASSET_ROOT / str(record["path"])
        samples = _samples(path)
        peak = max(abs(sample) for sample in samples)
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        dc_offset = abs(sum(samples) / len(samples))

        assert 4_000 <= peak <= 29_500, cue_id
        assert 500 <= rms <= 13_000, cue_id
        assert dc_offset <= 450, cue_id
        assert all(-32_768 <= sample <= 32_767 for sample in samples)
        assert all(sample % 64 == 0 for sample in samples), cue_id
        parameters = record["parameters"]
        assert isinstance(parameters, dict)
        assert parameters["quantization_step"] == 64
        assert samples[0] == samples[-1] == 0
        if cue_id.startswith("music."):
            assert abs(samples[0] - samples[-1]) <= 64
            assert 5.5 <= len(samples) / RATE <= 13.0
        else:
            assert 0.1 <= len(samples) / RATE <= 1.0
        pcm_hashes.add(hashlib.sha256(struct.pack(f"<{len(samples)}h", *samples)).hexdigest())

    assert len(pcm_hashes) == 57


def test_audio_manifest_and_provenance_are_exact_canonical_utf8_json() -> None:
    for path in (MANIFEST_PATH, PROVENANCE_PATH):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert path.read_bytes() == _canonical_json(document)


def test_all_thirty_six_boss_telegraphs_resolve_to_manifested_exact_boss_cues() -> None:
    bundle = load_catalog_bundle(ROOT / "windsprig/content")
    manifest = load_asset_manifest(MANIFEST_PATH)
    attacks = [attack for boss in bundle.bosses.values() for phase in boss.phases for attack in phase.attacks]

    assert len(attacks) == 36
    assert {attack.cue_id for attack in attacks} == {f"sfx.boss.{boss_id}" for boss_id in bundle.bosses}
    assert all(attack.cue_id in manifest.audio for attack in attacks)

    report = validate_bundle(
        bundle,
        manifest,
        load_locales(ROOT / "windsprig/content"),
        asset_root=ASSET_ROOT,
    )
    assert report.errors == ()
    assert report.counts["music"] == 28
    assert report.counts["sfx"] == 29


def test_release_asset_catalog_verifies_and_exposes_all_fifty_seven_audio_files() -> None:
    manifest = load_asset_manifest(MANIFEST_PATH)
    catalog = AssetCatalog.load(ASSET_ROOT, manifest)
    verified_paths = AssetCatalog.verified_audio_paths(ASSET_ROOT, manifest)

    for cue_id, spec in manifest.audio.items():
        assert catalog.sound_path(cue_id) == ASSET_ROOT / spec.path
        assert verified_paths[cue_id] == ASSET_ROOT / spec.path
    assert set(verified_paths) == MUSIC_CUE_IDS | SFX_CUE_IDS


def test_audio_provenance_and_paths_contain_no_legacy_public_identity() -> None:
    text = PROVENANCE_PATH.read_text(encoding="utf-8").lower()
    paths = "\n".join(
        path.relative_to(ASSET_ROOT).as_posix().lower() for path in (ASSET_ROOT / "generated/audio").rglob("*")
    )
    for forbidden in ("kirby", "nintendo", "return to dream land"):
        assert forbidden not in text
        assert forbidden not in paths


def test_asset_license_ledger_records_original_mit_audio_and_retains_the_font_attribution() -> None:
    ledger = (ASSET_ROOT / "LICENSES.md").read_text(encoding="utf-8")

    assert "57 WAV" in ledger
    assert "tools/generate_audio.py" in ledger
    assert "assets/generated/audio-provenance.json" in ledger
    assert "project MIT license" in ledger
    assert "SIL Open Font License 1.1" in ledger
