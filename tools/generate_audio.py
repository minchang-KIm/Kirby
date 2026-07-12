"""Generate Windsprig's exact deterministic PCM music and sound inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import stat
import struct
import sys
import tempfile
from array import array
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from windsprig.audio.catalog import BOSS_PHASES, MUSIC_CUE_IDS, SFX_CUE_IDS
from windsprig.content.loader import load_asset_manifest
from windsprig.content.models import AssetManifest

RATE: Final = 22_050
CHANNELS: Final = 1
SAMPLE_WIDTH_BYTES: Final = 2
QUANTIZATION_STEP: Final = 64
REST: Final = -99
ALGORITHM: Final = "windsprig-additive-pcm-v1"
LICENSE_TEXT: Final = "Original project audio distributed under the root MIT license"
DEFAULT_ROOT: Final = Path(__file__).resolve().parents[1]

type Waveform = Literal["sine", "triangle", "square", "saw"]
type Theme = tuple[int, int, tuple[int, ...], tuple[int, ...], Waveform]
type SfxSpec = tuple[Waveform, float, int, int, float]
type AudioParameter = str | int | float | tuple[int, ...]

THEMES: Final[Mapping[str, Theme]] = {
    "world_1": (112, 60, (0, 2, 4, 7, 9, 7, 4, 2, 0, 4, 7, 11, 9, 7, 4, 2), (0, 7, 5, 7, 0, 7, 5, 4), "triangle"),
    "world_2": (124, 50, (0, 3, 7, 8, 7, 3, 0, REST, 0, 5, 8, 10, 8, 5, 3, REST), (0, 5, 3, 7, 0, 8, 5, 7), "square"),
    "world_3": (88, 57, (0, 2, 5, 7, 9, 7, 5, 2, 0, 5, 9, 12, 9, 7, 5, 2), (0, 5, 2, 7, 0, 5, 9, 7), "sine"),
    "world_4": (138, 62, (0, 3, 5, 10, 7, 5, 3, 0, 0, 7, 10, 12, 10, 7, 5, 3), (0, 7, 3, 10, 0, 7, 5, 10), "saw"),
    "world_5": (104, 65, (0, 2, 6, 7, 11, 9, 7, 6, 0, 6, 9, 13, 11, 9, 7, 2), (0, 6, 2, 7, 0, 9, 6, 7), "triangle"),
    "world_6": (76, 48, (0, 3, 5, 7, REST, 5, 3, 0, 0, 7, 8, 12, 10, 8, 5, 3), (0, 5, 3, 7, 0, 8, 5, 10), "sine"),
}

SYSTEM_THEMES: Final[Mapping[str, Theme]] = {
    "title": (96, 60, (0, 4, 7, 11, 9, 7, 4, 2, 0, 7, 12, 11, 9, 7, 4, REST), (0, 7, 5, 4, 0, 7, 9, 5), "triangle"),
    "map": (108, 55, (0, 2, 4, 7, 4, 2, 0, REST, 5, 7, 9, 12, 9, 7, 5, REST), (0, 5, 7, 4, 0, 5, 9, 7), "sine"),
    "results": (120, 67, (0, 4, 7, 12, 11, 9, 7, 4, 5, 9, 12, 16, 14, 12, 9, 7), (0, 7, 5, 9, 0, 7, 5, 12), "triangle"),
    "credits": (84, 53, (0, 5, 7, 9, 7, 5, 2, 0, 0, 4, 7, 11, 9, 7, 4, 2), (0, 5, 2, 7, 0, 4, 5, 7), "sine"),
}

SFX: Final[Mapping[str, SfxSpec]] = {
    "ui.confirm": ("sine", 0.12, 520, 780, 0.00),
    "ui.cancel": ("triangle", 0.14, 420, 220, 0.00),
    "save.ok": ("sine", 0.22, 440, 660, 0.00),
    "player.jump": ("triangle", 0.20, 260, 620, 0.00),
    "player.hover": ("sine", 0.34, 360, 300, 0.08),
    "draw.start": ("sine", 0.40, 180, 520, 0.12),
    "draw.release": ("triangle", 0.25, 520, 170, 0.05),
    "enemy.launch": ("saw", 0.32, 220, 760, 0.08),
    "harmonize": ("sine", 0.55, 330, 990, 0.02),
    "damage": ("square", 0.20, 170, 90, 0.25),
    "guard": ("triangle", 0.18, 240, 180, 0.10),
    "dodge": ("sine", 0.22, 640, 280, 0.08),
    "mote": ("sine", 0.35, 660, 1320, 0.00),
    "checkpoint": ("triangle", 0.60, 392, 784, 0.01),
    "goal": ("sine", 0.75, 440, 880, 0.00),
    "defeat": ("triangle", 0.85, 330, 110, 0.06),
    "victory": ("sine", 0.90, 523, 1046, 0.00),
    "ability.bloomblade": ("triangle", 0.28, 380, 620, 0.05),
    "ability.cinder": ("saw", 0.42, 210, 150, 0.18),
    "ability.voltsong": ("square", 0.35, 720, 960, 0.12),
    "ability.galehook": ("sine", 0.38, 310, 690, 0.10),
    "ability.stoneheart": ("triangle", 0.50, 130, 70, 0.16),
    "ability.tempest": ("saw", 0.90, 180, 880, 0.20),
    "boss.rootjaw": ("triangle", 0.55, 120, 70, 0.20),
    "boss.crucible_crab": ("square", 0.52, 150, 95, 0.18),
    "boss.luma_eel": ("sine", 0.58, 420, 840, 0.06),
    "boss.volt_roc": ("square", 0.48, 760, 190, 0.22),
    "boss.prism_warden": ("triangle", 0.62, 520, 1040, 0.08),
    "boss.the_stillness": ("sine", 0.80, 90, 720, 0.14),
}

BOSS_WORLD: Final = {
    "rootjaw": "world_1",
    "crucible_crab": "world_2",
    "luma_eel": "world_3",
    "volt_roc": "world_4",
    "prism_warden": "world_5",
    "the_stillness": "world_6",
}
SFX_WAVEFORM_GAIN: Final[Mapping[Waveform, float]] = {
    "sine": 1.0,
    "triangle": 1.0,
    "square": 0.82,
    "saw": 0.92,
}


@dataclass(frozen=True, slots=True)
class AudioEntry:
    """One immutable generated WAV and its complete reproducibility metadata."""

    cue_id: str
    bus: Literal["music", "sfx"]
    path: PurePosixPath
    wav: bytes
    pcm: bytes
    seed: int
    theme: str
    phase: int | None
    parameters: tuple[tuple[str, AudioParameter], ...]


def oscillator(kind: Waveform, phase: float) -> float:
    """Return one bounded analytic waveform sample."""

    cycle = phase / math.tau
    if kind == "sine":
        return math.sin(phase)
    if kind == "triangle":
        return 2.0 * abs(2.0 * (cycle - math.floor(cycle + 0.5))) - 1.0
    if kind == "square":
        return 1.0 if math.sin(phase) >= 0.0 else -1.0
    return 2.0 * (cycle - math.floor(cycle + 0.5))


def hz(midi: int) -> float:
    """Convert one MIDI note number to equal-tempered frequency."""

    return 440.0 * math.pow(2.0, (midi - 69) / 12.0)


def edge_fade(index: int, count: int) -> float:
    """Use equal-power 25 ms edges so repeated music has a silent seam."""

    fade = max(1, int(RATE * 0.025))
    if index < fade:
        return math.sin(index / fade * math.pi / 2.0) ** 2
    if index >= count - fade:
        return math.sin((count - 1 - index) / fade * math.pi / 2.0) ** 2
    return 1.0


def quantize(sample: int) -> int:
    """Retain ten effective bits so both web archives stay within budget.

    The WAV remains signed 16-bit PCM at 22,050 Hz. A 64-unit step places
    quantization noise near -60 dB while making deterministic PCM materially
    more compressible for the browser's duplicated APK and tar archives.
    """

    value = round(sample / QUANTIZATION_STEP) * QUANTIZATION_STEP
    return max(-32_768, min(32_704, value))


def compose(theme: Theme, phase: int = 0, *, seed: int) -> list[int]:
    """Compose one fixed-length theme variation from reviewed note recipes."""

    tempo, root, authored_melody, bass, kind = theme
    tempo += phase * 8
    melody = authored_melody[phase * 2 :] + authored_melody[: phase * 2]
    beats = 16
    count = round(RATE * 60 / tempo * beats)
    texture_phase = random.Random(seed).random() * math.tau
    samples: list[int] = []
    for index in range(count):
        time_s = index / RATE
        beat_position = time_s * tempo / 60.0
        beat = min(beats - 1, int(beat_position))
        beat_phase = beat_position - beat
        note = melody[beat]
        bass_note = bass[(beat // 2) % len(bass)]
        attack = min(1.0, beat_phase / 0.055)
        lead_envelope = attack * math.exp(-beat_phase * 2.4)
        lead = (
            0.0
            if note == REST
            else oscillator(kind, math.tau * hz(root + note) * time_s + texture_phase) * lead_envelope
        )
        low = oscillator("sine", math.tau * hz(root - 12 + bass_note) * time_s) * 0.42
        pulse = oscillator("triangle", math.tau * (2 + phase) * time_s + texture_phase / 2.0) * 0.08
        value = (lead * 0.40 + low * 0.32 + pulse) * edge_fade(index, count)
        samples.append(quantize(max(-32_000, min(32_000, round(value * 32_000)))))
    samples[0] = samples[-1] = 0
    return samples


def synth_sfx(spec: SfxSpec, seed: int) -> list[int]:
    """Synthesize one short, deterministic pitched/noise action envelope."""

    kind, duration, start_hz, end_hz, noise = spec
    count = round(RATE * duration)
    rng = random.Random(seed)
    phase = 0.0
    output: list[int] = []
    for index in range(count):
        position = index / max(1, count - 1)
        frequency = start_hz + (end_hz - start_hz) * position
        phase += math.tau * frequency / RATE
        envelope = math.sin(math.pi * position) ** 1.5
        value = (oscillator(kind, phase) * (1.0 - noise) + (rng.random() * 2.0 - 1.0) * noise) * SFX_WAVEFORM_GAIN[kind]
        output.append(quantize(round(max(-1.0, min(1.0, value * envelope)) * 24_500)))
    output[0] = output[-1] = 0
    return output


def _pcm_bytes(samples: Sequence[int]) -> bytes:
    pcm = array("h", samples)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def _wav_bytes(pcm: bytes) -> bytes:
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        CHANNELS,
        RATE,
        RATE * CHANNELS * SAMPLE_WIDTH_BYTES,
        CHANNELS * SAMPLE_WIDTH_BYTES,
        SAMPLE_WIDTH_BYTES * 8,
        b"data",
        data_size,
    )
    return header + pcm


def _music_parameters(theme: Theme, phase: int) -> tuple[tuple[str, AudioParameter], ...]:
    tempo, root, melody, bass, kind = theme
    return (
        ("bass", bass),
        ("beats", 16),
        ("melody", melody),
        ("oscillator", kind),
        ("phase_variant", phase),
        ("quantization_step", QUANTIZATION_STEP),
        ("root_midi", root),
        ("tempo_bpm", tempo + phase * 8),
    )


def _sfx_parameters(spec: SfxSpec) -> tuple[tuple[str, AudioParameter], ...]:
    kind, duration, start_hz, end_hz, noise = spec
    return (
        ("duration_seconds", duration),
        ("end_hz", end_hz),
        ("noise_mix", noise),
        ("oscillator", kind),
        ("output_gain", SFX_WAVEFORM_GAIN[kind]),
        ("quantization_step", QUANTIZATION_STEP),
        ("start_hz", start_hz),
    )


def _entry(
    cue_id: str,
    bus: Literal["music", "sfx"],
    path: PurePosixPath,
    samples: Sequence[int],
    *,
    seed: int,
    theme: str,
    phase: int | None,
    parameters: tuple[tuple[str, AudioParameter], ...],
) -> AudioEntry:
    pcm = _pcm_bytes(samples)
    return AudioEntry(cue_id, bus, path, _wav_bytes(pcm), pcm, seed, theme, phase, parameters)


@lru_cache(maxsize=1)
def build_entries() -> tuple[AudioEntry, ...]:
    """Build the exact in-memory inventory without touching publication paths."""

    entries: list[AudioEntry] = []
    for index, (theme_id, theme) in enumerate(sorted(SYSTEM_THEMES.items()), start=1):
        cue_id = f"music.{theme_id}"
        seed = 6_100 + index
        entries.append(
            _entry(
                cue_id,
                "music",
                PurePosixPath(f"generated/audio/music/{theme_id}.wav"),
                compose(theme, seed=seed),
                seed=seed,
                theme=theme_id,
                phase=0,
                parameters=_music_parameters(theme, 0),
            )
        )
    for index, (world_id, theme) in enumerate(THEMES.items(), start=1):
        cue_id = f"music.world.{world_id}"
        seed = 6_200 + index
        entries.append(
            _entry(
                cue_id,
                "music",
                PurePosixPath(f"generated/audio/music/world-{world_id}.wav"),
                compose(theme, seed=seed),
                seed=seed,
                theme=world_id,
                phase=0,
                parameters=_music_parameters(theme, 0),
            )
        )
    for boss_index, boss_id in enumerate(BOSS_PHASES, start=1):
        world_id = BOSS_WORLD[boss_id]
        theme = THEMES[world_id]
        for phase in range(1, 4):
            cue_id = f"music.boss.{boss_id}.p{phase}"
            seed = 6_300 + boss_index * 10 + phase
            entries.append(
                _entry(
                    cue_id,
                    "music",
                    PurePosixPath(f"generated/audio/music/boss-{boss_id}-p{phase}.wav"),
                    compose(theme, phase, seed=seed),
                    seed=seed,
                    theme=world_id,
                    phase=phase,
                    parameters=_music_parameters(theme, phase),
                )
            )
    for seed, (cue_suffix, spec) in enumerate(sorted(SFX.items()), start=7_001):
        cue_id = f"sfx.{cue_suffix}"
        entries.append(
            _entry(
                cue_id,
                "sfx",
                PurePosixPath(f"generated/audio/sfx/{cue_suffix.replace('.', '-')}.wav"),
                synth_sfx(spec, seed),
                seed=seed,
                theme=cue_suffix.split(".", 1)[0],
                phase=None,
                parameters=_sfx_parameters(spec),
            )
        )
    entries.sort(key=lambda item: item.cue_id)
    actual_music = {entry.cue_id for entry in entries if entry.bus == "music"}
    actual_sfx = {entry.cue_id for entry in entries if entry.bus == "sfx"}
    if actual_music != MUSIC_CUE_IDS or actual_sfx != SFX_CUE_IDS:
        raise AssertionError("generated audio inventory differs from the canonical cue catalog")
    return tuple(entries)


def _canonical_json(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _entry_record(entry: AudioEntry) -> dict[str, object]:
    return {
        "algorithm": ALGORITHM,
        "channels": CHANNELS,
        "duration_seconds": len(entry.pcm) / (RATE * SAMPLE_WIDTH_BYTES),
        "frame_count": len(entry.pcm) // SAMPLE_WIDTH_BYTES,
        "license": LICENSE_TEXT,
        "parameters": dict(entry.parameters),
        "path": entry.path.as_posix(),
        "pcm_sha256": hashlib.sha256(entry.pcm).hexdigest(),
        "phase": entry.phase,
        "sample_rate": RATE,
        "sample_width_bytes": SAMPLE_WIDTH_BYTES,
        "seed": entry.seed,
        "sha256": hashlib.sha256(entry.wav).hexdigest(),
        "theme": entry.theme,
    }


def _provenance(entries: Sequence[AudioEntry]) -> dict[str, object]:
    return {
        "algorithm": ALGORITHM,
        "channels": CHANNELS,
        "generator": "tools/generate_audio.py",
        "license": LICENSE_TEXT,
        "music": {entry.cue_id: _entry_record(entry) for entry in entries if entry.bus == "music"},
        "quantization_step": QUANTIZATION_STEP,
        "sample_rate": RATE,
        "sample_width_bytes": SAMPLE_WIDTH_BYTES,
        "schema_version": 1,
        "sfx": {entry.cue_id: _entry_record(entry) for entry in entries if entry.bus == "sfx"},
    }


def _manifest_audio(entries: Sequence[AudioEntry]) -> dict[str, object]:
    return {
        entry.cue_id: {
            "bus": entry.bus,
            "mandatory": True,
            "path": entry.path.as_posix(),
            "sha256": hashlib.sha256(entry.wav).hexdigest(),
        }
        for entry in entries
    }


def _manifest_document(existing: AssetManifest, entries: Sequence[AudioEntry]) -> dict[str, object]:
    provenance_files = set(existing.provenance_files)
    provenance_files.add("generated/art-provenance.json")
    provenance_files.add("generated/audio-provenance.json")
    return {
        "art": {
            asset_id: {
                "frames": spec.frames,
                "height": spec.height,
                "mandatory": spec.mandatory,
                "path": spec.path,
                "pixel_sha256": spec.pixel_sha256,
                "provenance": spec.provenance,
                "width": spec.width,
            }
            for asset_id, spec in existing.art.items()
        },
        "audio": _manifest_audio(entries),
        "font": {
            "license": existing.font.license,
            "mandatory": existing.font.mandatory,
            "path": existing.font.path,
            "sha256": existing.font.sha256,
        },
        "provenance_files": sorted(provenance_files),
    }


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction) and isjunction(path):
        return True
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _safe_root(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    lexical = Path(os.path.abspath(root))
    if not lexical.exists():
        raise FileNotFoundError(f"audio publication root does not exist: {lexical}")
    if _is_link_or_reparse(lexical) or not lexical.is_dir():
        raise ValueError(f"audio publication root must be a regular directory: {lexical}")
    return lexical


def _safe_existing_path(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if _is_link_or_reparse(current):
            raise ValueError(f"audio read path is unsafe: {current}")
        if index < len(relative.parts) - 1 and current.exists() and not current.is_dir():
            raise ValueError(f"audio read path is unsafe: {current}")
    return current


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_mode, left.st_size, left.st_mtime_ns) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_size,
        right.st_mtime_ns,
    )


def _read_regular_file(path: Path) -> bytes:
    try:
        expected = path.lstat()
    except FileNotFoundError:
        raise FileNotFoundError("missing regular file") from None
    if _is_link_or_reparse(path) or not stat.S_ISREG(expected.st_mode):
        raise FileNotFoundError("missing regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise OSError("unreadable regular file") from error
    try:
        opened = os.fstat(descriptor)
        if not _same_file_identity(expected, opened):
            raise OSError("file changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read()
        completed = os.fstat(descriptor)
        if not _same_file_identity(opened, completed):
            raise OSError("file changed while reading")
        return payload
    except OSError as error:
        raise OSError("unreadable regular file") from error
    finally:
        os.close(descriptor)


def _load_manifest(root: Path) -> AssetManifest:
    manifest_path = _safe_existing_path(root, PurePosixPath("windsprig/content/assets.json"))
    try:
        payload = _read_regular_file(manifest_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"asset manifest is missing: {manifest_path}") from None
    with tempfile.TemporaryDirectory(prefix="windsprig-audio-manifest-") as temporary:
        isolated = Path(temporary) / "assets.json"
        isolated.write_bytes(payload)
        return load_asset_manifest(isolated)


def _ensure_directory(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() or _is_link_or_reparse(current):
            if _is_link_or_reparse(current) or not current.is_dir():
                raise ValueError(f"audio publication directory is unsafe: {current}")
        else:
            current.mkdir()
    return current


def _validate_publication_targets(root: Path) -> None:
    _ensure_directory(root, PurePosixPath("assets"))
    _ensure_directory(root, PurePosixPath("assets/generated"))
    _ensure_directory(root, PurePosixPath("windsprig/content"))
    audio = root / "assets/generated/audio"
    if audio.exists() or _is_link_or_reparse(audio):
        if _is_link_or_reparse(audio) or not audio.is_dir():
            raise ValueError(f"audio publication target is unsafe: {audio}")
    for relative in (
        PurePosixPath("assets/generated/audio-provenance.json"),
        PurePosixPath("windsprig/content/assets.json"),
    ):
        target = root / Path(relative.as_posix())
        if target.exists() or _is_link_or_reparse(target):
            if _is_link_or_reparse(target) or not target.is_file():
                raise ValueError(f"audio publication target is unsafe: {target}")


def _write_stage(
    stage_root: Path,
    entries: Sequence[AudioEntry],
    manifest: Mapping[str, object],
) -> None:
    for entry in entries:
        path = stage_root / "assets" / Path(entry.path.as_posix())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.wav)
    provenance_path = stage_root / "assets/generated/audio-provenance.json"
    provenance_path.write_bytes(_canonical_json(_provenance(entries)))
    manifest_path = stage_root / "windsprig/content/assets.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(_canonical_json(manifest))


def _decode_wav(payload: bytes) -> bytes:
    try:
        if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
            raise ValueError
        if struct.unpack_from("<I", payload, 4)[0] != len(payload) - 8:
            raise ValueError
        if payload[12:16] != b"fmt " or struct.unpack_from("<I", payload, 16)[0] != 16:
            raise ValueError
        audio_format, channels, rate, byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", payload, 20)
        if (audio_format, channels, rate, byte_rate, block_align, bits) != (1, 1, RATE, RATE * 2, 2, 16):
            raise ValueError
        if payload[36:40] != b"data":
            raise ValueError
        data_size = struct.unpack_from("<I", payload, 40)[0]
        if data_size <= 0 or data_size != len(payload) - 44 or data_size % 2:
            raise ValueError
        return payload[44:]
    except (ValueError, struct.error):
        raise ValueError("unreadable WAV") from None


def _validate_stage(
    stage_root: Path,
    entries: Sequence[AudioEntry],
    manifest: Mapping[str, object],
) -> None:
    for entry in entries:
        payload = (stage_root / "assets" / Path(entry.path.as_posix())).read_bytes()
        if _decode_wav(payload) != entry.pcm:
            raise RuntimeError(f"staged audio failed PCM validation: {entry.cue_id}")
    provenance_path = stage_root / "assets/generated/audio-provenance.json"
    if provenance_path.read_bytes() != _canonical_json(_provenance(entries)):
        raise RuntimeError("staged audio provenance failed canonical validation")
    manifest_path = stage_root / "windsprig/content/assets.json"
    if manifest_path.read_bytes() != _canonical_json(manifest):
        raise RuntimeError("staged asset manifest failed canonical validation")
    loaded = load_asset_manifest(manifest_path)
    if set(loaded.audio) != MUSIC_CUE_IDS | SFX_CUE_IDS:
        raise RuntimeError("staged asset manifest failed audio inventory validation")


def _replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _remove_owned(path: Path) -> None:
    if _is_link_or_reparse(path) or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _publish(root: Path, stage_root: Path) -> None:
    _validate_publication_targets(root)
    owned = (
        PurePosixPath("assets/generated/audio"),
        PurePosixPath("assets/generated/audio-provenance.json"),
        PurePosixPath("windsprig/content/assets.json"),
    )
    backup_root = stage_root / "backup"
    published: list[tuple[Path, Path, bool]] = []
    try:
        for relative in owned:
            staged = stage_root / Path(relative.as_posix())
            target = root / Path(relative.as_posix())
            backup = backup_root / Path(relative.as_posix())
            backup.parent.mkdir(parents=True, exist_ok=True)
            existed = target.exists()
            if existed:
                _replace(target, backup)
            try:
                _replace(staged, target)
            except BaseException:
                if existed:
                    _replace(backup, target)
                raise
            published.append((target, backup, existed))
    except BaseException:
        for target, backup, existed in reversed(published):
            _remove_owned(target)
            if existed:
                _replace(backup, target)
        raise


def _canonical_bytes_match(committed: Path, generated: Path) -> bool:
    try:
        return _read_regular_file(committed) == generated.read_bytes()
    except (FileNotFoundError, OSError):
        return False


def _check_against_stage(
    root: Path,
    stage_root: Path,
    entries: Sequence[AudioEntry],
) -> tuple[str, ...]:
    findings: list[str] = []
    expected_paths = {entry.path.as_posix(): entry for entry in entries}
    audio_root = _safe_existing_path(root, PurePosixPath("assets/generated/audio"))
    actual_files: set[str] = set()
    if audio_root.is_dir():
        for path in audio_root.rglob("*"):
            if _is_link_or_reparse(path):
                raise ValueError(f"audio read path is unsafe: {path}")
            if path.is_file():
                actual_files.add(path.relative_to(root / "assets").as_posix())
    for unexpected in sorted(actual_files - expected_paths.keys()):
        findings.append(f"UNEXPECTED audio {unexpected}")
    for relative, entry in sorted(expected_paths.items()):
        committed = _safe_existing_path(root / "assets", PurePosixPath(relative))
        generated = stage_root / "assets" / Path(relative)
        try:
            committed_pcm = _decode_wav(_read_regular_file(committed))
        except (FileNotFoundError, OSError):
            findings.append(f"STALE audio {entry.cue_id}: missing or unsafe")
            continue
        except ValueError:
            findings.append(f"STALE audio {entry.cue_id}: unreadable WAV")
            continue
        if committed_pcm != _decode_wav(generated.read_bytes()):
            findings.append(f"STALE audio {entry.cue_id}: decoded PCM")
    comparisons = (
        (
            "manifest",
            _safe_existing_path(root, PurePosixPath("windsprig/content/assets.json")),
            stage_root / "windsprig/content/assets.json",
        ),
        (
            "provenance",
            _safe_existing_path(root, PurePosixPath("assets/generated/audio-provenance.json")),
            stage_root / "assets/generated/audio-provenance.json",
        ),
    )
    for label, committed, generated in comparisons:
        if not _canonical_bytes_match(committed, generated):
            findings.append(f"STALE {label}: canonical JSON")
    return tuple(sorted(findings))


def generate(root: Path) -> tuple[AudioEntry, ...]:
    """Validate, stage, and transactionally publish all owned audio outputs."""

    lexical_root = _safe_root(root)
    existing = _load_manifest(lexical_root)
    _validate_publication_targets(lexical_root)
    entries = build_entries()
    manifest = _manifest_document(existing, entries)
    with tempfile.TemporaryDirectory(prefix=".windsprig-audio-", dir=lexical_root) as temporary:
        stage_root = Path(temporary) / "stage"
        _write_stage(stage_root, entries, manifest)
        _validate_stage(stage_root, entries, manifest)
        _publish(lexical_root, stage_root)
    return entries


def check(root: Path) -> tuple[str, ...]:
    """Regenerate outside the repository and report drift without writes."""

    lexical_root = _safe_root(root)
    existing = _load_manifest(lexical_root)
    _safe_existing_path(lexical_root, PurePosixPath("assets/generated/audio"))
    entries = build_entries()
    manifest = _manifest_document(existing, entries)
    with tempfile.TemporaryDirectory(prefix="windsprig-audio-check-") as temporary:
        stage_root = Path(temporary) / "stage"
        _write_stage(stage_root, entries, manifest)
        _validate_stage(stage_root, entries, manifest)
        return _check_against_stage(lexical_root, stage_root, entries)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate release audio, or perform an isolated no-write drift check."""

    args = _parser().parse_args(argv)
    if args.check:
        findings = check(args.root)
        for finding in findings:
            print(finding)
        if findings:
            return 1
    else:
        generate(args.root)
    print("audio: 28 music loops, 29 sfx, 22050 Hz mono PCM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
