"""Release-art inventory and manifest contracts."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import wave
from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from windsprig.content.loader import load_asset_manifest
from windsprig.content.models import ArtAssetSpec, AssetManifest, AudioAssetSpec, FontAssetSpec
from windsprig.render import assets as asset_module
from windsprig.render.assets import AssetCatalog, MissingAssetError

ROOT = Path(__file__).resolve().parents[3]
_REAL_SUBPROCESS_RUN = subprocess.run

EXPECTED_CLIPS = {
    "attack": 6,
    "captured": 4,
    "defeated": 4,
    "dodge": 4,
    "draw": 4,
    "fall": 2,
    "guard": 2,
    "harmonize": 6,
    "hover": 4,
    "hurt": 2,
    "idle": 4,
    "jump": 2,
    "run": 6,
    "victory": 6,
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


def test_release_art_manifest_is_complete_original_and_named() -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")
    art = manifest.art

    assert len(art) == 52
    assert art["player.sprig"].frames == 56
    assert len([asset_id for asset_id in art if asset_id.startswith("enemy.")]) == 18
    assert len([asset_id for asset_id in art if asset_id.startswith("boss.")]) == 6
    assert len([asset_id for asset_id in art if asset_id.startswith("world.")]) == 24
    assert len([asset_id for asset_id in art if asset_id.startswith("ui.")]) == 3
    assert all(item.mandatory for item in art.values())
    assert {item.provenance for item in art.values()} == {"procedural-vector-v1"}

    provenance = json.loads((ROOT / "assets/generated/art-provenance.json").read_text(encoding="utf-8"))
    assert provenance["algorithm"] == "procedural-vector-v1"
    assert provenance["clips"] == EXPECTED_CLIPS
    assert sum(EXPECTED_CLIPS.values()) == 56
    assert provenance["license"] == "Original project art distributed under the root MIT license"
    assert set(provenance["assets"]) == set(art)


def _pixel_hash(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA", False)).hexdigest()


def test_release_art_dimensions_and_decoded_hashes_match_the_manifest() -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")
    expected_dimensions = {
        "player.sprig": (768, 672, 56),
        "ui.icons": (2048, 64, 32),
        "ui.favicon": (192, 192, 1),
        "ui.social_card": (1200, 630, 1),
    }
    for world_index in range(1, 7):
        prefix = f"world.world_{world_index}"
        expected_dimensions.update(
            {
                f"{prefix}.background": (1280, 2880, 4),
                f"{prefix}.tiles": (512, 64, 8),
                f"{prefix}.props": (576, 96, 6),
                f"{prefix}.transition": (1280, 720, 1),
            }
        )
    for asset_id, spec in manifest.art.items():
        surface = pygame.image.load(ROOT / "assets" / spec.path)
        assert surface.get_size() == (spec.width, spec.height)
        assert _pixel_hash(surface) == spec.pixel_sha256
        if asset_id.startswith("enemy."):
            assert (spec.width, spec.height, spec.frames) == (384, 96, 4)
        elif asset_id.startswith("boss."):
            assert (spec.width, spec.height, spec.frames) == (768, 384, 18)
        elif asset_id in expected_dimensions:
            assert (spec.width, spec.height, spec.frames) == expected_dimensions[asset_id]


def test_committed_release_catalog_loads_all_art_and_the_pinned_font() -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")

    catalog = AssetCatalog.load(ROOT / "assets", manifest)

    assert catalog.image("player.sprig").get_size() == (768, 672)
    assert catalog.image("ui.social_card").get_size() == (1200, 630)
    assert catalog.font(20, 500).get_height() > 0


def test_catalog_slices_manifest_declared_frames_without_atlas_bleed() -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")
    catalog = AssetCatalog.load(ROOT / "assets", manifest)

    assert catalog.frame_count("player.sprig") == 56
    assert catalog.frame("player.sprig", 55).get_size() == (96, 96)
    assert catalog.frame("enemy.breezeling", 3).get_size() == (96, 96)
    assert catalog.frame("boss.rootjaw", 17).get_size() == (128, 128)
    assert catalog.frame("world.world_1.background", 3).get_size() == (1280, 720)
    assert catalog.frame("world.world_1.tiles", 7).get_size() == (64, 64)
    assert catalog.frame("ui.icons", 31).get_size() == (64, 64)


@pytest.mark.parametrize("frame_index", [-1, 56])
def test_catalog_rejects_out_of_bounds_frame_indices(frame_index: int) -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")
    catalog = AssetCatalog.load(ROOT / "assets", manifest)

    with pytest.raises(IndexError, match="frame"):
        catalog.frame("player.sprig", frame_index)
    with pytest.raises(TypeError, match="frame"):
        catalog.frame("player.sprig", True)


def test_sprite_cells_are_nonempty_unclipped_and_visually_distinct() -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")
    provenance = json.loads((ROOT / "assets/generated/art-provenance.json").read_text(encoding="utf-8"))
    player = pygame.image.load(ROOT / "assets" / manifest.art["player.sprig"].path)
    clip_frames = provenance["clip_frames"]
    assert {state: len(frames) for state, frames in clip_frames.items()} == EXPECTED_CLIPS
    frame_ids = [frame for frames in clip_frames.values() for frame in frames]
    assert sorted(frame_ids) == list(range(56))
    for frame in sorted(frame_ids):
        cell = player.subsurface(pygame.Rect((frame % 8) * 96, (frame // 8) * 96, 96, 96))
        bounds = cell.get_bounding_rect(min_alpha=1)
        assert bounds.width > 20 and bounds.height > 20
        assert bounds.left > 0 and bounds.top > 0 and bounds.right < 96 and bounds.bottom < 96

    enemy_hashes: set[str] = set()
    for asset_id, spec in manifest.art.items():
        if asset_id.startswith("enemy."):
            enemy = pygame.image.load(ROOT / "assets" / spec.path)
            enemy_hashes.add(_pixel_hash(enemy.subsurface(pygame.Rect(0, 0, 96, 96))))
    assert len(enemy_hashes) == 18

    boss_phase_hashes: set[str] = set()
    for asset_id, spec in manifest.art.items():
        if asset_id.startswith("boss."):
            boss = pygame.image.load(ROOT / "assets" / spec.path)
            for phase in range(3):
                boss_phase_hashes.add(_pixel_hash(boss.subsurface(pygame.Rect(0, phase * 128, 128, 128))))
    assert len(boss_phase_hashes) == 18

    icons = pygame.image.load(ROOT / "assets" / manifest.art["ui.icons"].path)
    icon_hashes = {_pixel_hash(icons.subsurface(pygame.Rect(index * 64, 0, 64, 64))) for index in range(32)}
    assert len(icon_hashes) == 32


def test_world_sets_have_six_distinct_palette_and_silhouette_families() -> None:
    manifest = load_asset_manifest(ROOT / "windsprig/content/assets.json")
    for kind in ("background", "tiles", "props", "transition"):
        hashes = {manifest.art[f"world.world_{world_index}.{kind}"].pixel_sha256 for world_index in range(1, 7)}
        assert len(hashes) == 6


def test_generated_json_is_canonical_sorted_utf8() -> None:
    for path in (ROOT / "windsprig/content/assets.json", ROOT / "assets/generated/art-provenance.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        canonical = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
        assert path.read_bytes() == canonical.encode("utf-8")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wav_bytes(*, channels: int = 1, width: int = 2, rate: int = 22_050) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(b"\x00" * channels * width * 128)
    return stream.getvalue()


def _fixture_manifest(root: Path, art: ArtAssetSpec, *, audio: AudioAssetSpec | None = None) -> AssetManifest:
    font = root / "fonts/font.ttf"
    font.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets/fonts/NotoSansKR[wght].ttf", font)
    license_path = root / "fonts/OFL.txt"
    license_path.write_text("SIL Open Font License 1.1\n", encoding="utf-8")
    return AssetManifest(
        art={"art.fixture": art},
        audio={} if audio is None else {"sfx.fixture": audio},
        font=FontAssetSpec(
            path="fonts/font.ttf",
            license="fonts/OFL.txt",
            mandatory=True,
            sha256=_file_hash(font),
        ),
    )


def _fixture_art(root: Path) -> ArtAssetSpec:
    surface = pygame.Surface((32, 24), pygame.SRCALPHA)
    surface.fill((31, 77, 53, 255))
    pygame.draw.polygon(surface, (244, 198, 76), ((3, 20), (15, 2), (28, 18)))
    path = root / "generated/fixture.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, path)
    digest = hashlib.sha256(pygame.image.tobytes(pygame.image.load(path), "RGBA", False)).hexdigest()
    return ArtAssetSpec(
        path="generated/fixture.png",
        width=32,
        height=24,
        frames=1,
        pixel_sha256=digest,
        mandatory=True,
        provenance="procedural-vector-v1",
    )


def test_release_catalog_loads_and_verifies_every_runtime_kind(tmp_path: Path) -> None:
    art = _fixture_art(tmp_path)
    sound = tmp_path / "audio/cue.wav"
    sound.parent.mkdir()
    sound.write_bytes(_wav_bytes())
    audio = AudioAssetSpec(
        path="audio/cue.wav",
        bus="sfx",
        mandatory=True,
        sha256=_file_hash(sound),
    )
    manifest = _fixture_manifest(tmp_path, art, audio=audio)

    catalog = AssetCatalog.load(tmp_path, manifest)

    assert catalog.image("art.fixture").get_size() == (32, 24)
    assert catalog.sound_path("sfx.fixture") == sound
    assert catalog.font(18, 700).get_bold()
    assert not hasattr(catalog, "images")
    assert not hasattr(catalog, "sound_paths")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda spec: replace(spec, width=31), "invalid dimensions"),
        (lambda spec: replace(spec, pixel_sha256="0" * 64), "decoded pixel hash mismatch"),
        (lambda spec: replace(spec, path="../escape.png"), "unsafe path"),
    ],
)
def test_release_catalog_rejects_invalid_art(
    tmp_path: Path,
    mutation: object,
    message: str,
) -> None:
    art = _fixture_art(tmp_path)
    mutate = mutation
    assert callable(mutate)
    manifest = _fixture_manifest(tmp_path, mutate(art))

    with pytest.raises(MissingAssetError, match=message):
        AssetCatalog.load(tmp_path, manifest)


def test_release_catalog_rejects_missing_corrupt_and_non_file_art(tmp_path: Path) -> None:
    art = _fixture_art(tmp_path)
    manifest = _fixture_manifest(tmp_path, art)
    target = tmp_path / art.path

    target.unlink()
    with pytest.raises(MissingAssetError, match="missing regular file"):
        AssetCatalog.load(tmp_path, manifest)

    target.write_bytes(b"not a png")
    with pytest.raises(MissingAssetError, match="unreadable PNG"):
        AssetCatalog.load(tmp_path, manifest)

    target.unlink()
    target.mkdir()
    with pytest.raises(MissingAssetError, match="missing regular file"):
        AssetCatalog.load(tmp_path, manifest)


def test_release_catalog_rejects_a_linked_asset_directory_without_reading_outside(tmp_path: Path) -> None:
    art = _fixture_art(tmp_path)
    manifest = _fixture_manifest(tmp_path, art)
    generated = tmp_path / "generated"
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    generated.rename(outside)
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside stays unchanged\n", encoding="utf-8")
    _make_directory_link(generated, outside)
    try:
        with pytest.raises(MissingAssetError, match="art.fixture: unsafe path"):
            AssetCatalog.load(tmp_path, manifest)
        assert sentinel.read_text(encoding="utf-8") == "outside stays unchanged\n"
    finally:
        _remove_directory_link(generated)
        shutil.rmtree(outside)


def test_release_catalog_reports_unreadable_files_with_a_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    art = _fixture_art(tmp_path)
    manifest = _fixture_manifest(tmp_path, art)
    target = tmp_path / art.path
    real_open = asset_module.os.open

    def reject_fixture(path: object, flags: int) -> int:
        if Path(path) == target:
            raise PermissionError("host-specific permission detail")
        return real_open(path, flags)

    monkeypatch.setattr(asset_module.os, "open", reject_fixture)

    with pytest.raises(MissingAssetError, match="art.fixture: unreadable regular file"):
        AssetCatalog.load(tmp_path, manifest)


def test_release_catalog_rejects_font_audio_and_license_integrity_failures(tmp_path: Path) -> None:
    art = _fixture_art(tmp_path)
    sound = tmp_path / "audio/cue.wav"
    sound.parent.mkdir()
    valid_wav = _wav_bytes()
    sound.write_bytes(valid_wav)
    audio = AudioAssetSpec("audio/cue.wav", "sfx", True, _file_hash(sound))
    manifest = _fixture_manifest(tmp_path, art, audio=audio)

    sound.write_bytes(b"tampered")
    with pytest.raises(MissingAssetError, match="sfx.fixture: file hash mismatch"):
        AssetCatalog.load(tmp_path, manifest)

    sound.write_bytes(valid_wav)
    (tmp_path / manifest.font.path).write_bytes(b"tampered")
    with pytest.raises(MissingAssetError, match="font.noto_sans_kr: file hash mismatch"):
        AssetCatalog.load(tmp_path, manifest)

    shutil.copy2(ROOT / "assets/fonts/NotoSansKR[wght].ttf", tmp_path / manifest.font.path)
    (tmp_path / manifest.font.license).unlink()
    with pytest.raises(MissingAssetError, match="font.license: missing regular file"):
        AssetCatalog.load(tmp_path, manifest)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not a wav", "unreadable WAV"),
        (_wav_bytes(channels=2), "expected mono 16-bit 22050 Hz PCM"),
        (_wav_bytes(width=1), "expected mono 16-bit 22050 Hz PCM"),
        (_wav_bytes(rate=44_100), "expected mono 16-bit 22050 Hz PCM"),
        (_wav_bytes()[:-3], "unreadable WAV"),
    ],
)
def test_release_catalog_rejects_corrupt_or_wrong_format_audio_even_when_its_hash_matches(
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    art = _fixture_art(tmp_path)
    sound = tmp_path / "audio/cue.wav"
    sound.parent.mkdir()
    sound.write_bytes(payload)
    manifest = _fixture_manifest(
        tmp_path,
        art,
        audio=AudioAssetSpec("audio/cue.wav", "sfx", True, _file_hash(sound)),
    )

    with pytest.raises(MissingAssetError, match=message):
        AssetCatalog.load(tmp_path, manifest)


def test_release_catalog_rejects_an_escaped_audio_path_without_reading_it(tmp_path: Path) -> None:
    art = _fixture_art(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.wav"
    outside.write_bytes(_wav_bytes())
    manifest = _fixture_manifest(
        tmp_path,
        art,
        audio=AudioAssetSpec("../outside.wav", "sfx", True, _file_hash(outside)),
    )

    try:
        with pytest.raises(MissingAssetError, match="sfx.fixture: unsafe path"):
            AssetCatalog.load(tmp_path, manifest)
        assert outside.read_bytes() == _wav_bytes()
    finally:
        outside.unlink()


def test_developer_placeholders_are_explicit_and_cannot_make_release_pass(tmp_path: Path) -> None:
    missing = ArtAssetSpec(
        path="generated/missing.png",
        width=20,
        height=16,
        frames=1,
        pixel_sha256="0" * 64,
        mandatory=True,
        provenance="procedural-vector-v1",
    )
    manifest = AssetManifest(
        art={"art.missing": missing},
        audio={},
        font=FontAssetSpec("fonts/missing.ttf", "fonts/missing.txt", True, "0" * 64),
    )

    with pytest.raises(MissingAssetError):
        AssetCatalog.load(tmp_path, manifest, developer_mode=False)

    catalog = AssetCatalog.load(tmp_path, manifest, developer_mode=True)
    assert catalog.image("art.missing").get_size() == (20, 16)
    assert catalog.font(14).get_height() > 0


@pytest.mark.parametrize(
    ("method", "value", "exception"),
    [
        ("image", "", ValueError),
        ("image", True, TypeError),
        ("sound_path", "", ValueError),
        ("font", 0, ValueError),
        ("font", True, TypeError),
        ("font_weight", 0, ValueError),
        ("font_weight", True, TypeError),
    ],
)
def test_catalog_lookup_inputs_are_strict(
    method: str, value: object, exception: type[Exception], tmp_path: Path
) -> None:
    art = _fixture_art(tmp_path)
    catalog = AssetCatalog.load(tmp_path, _fixture_manifest(tmp_path, art))

    with pytest.raises(exception):
        if method == "font_weight":
            catalog.font(14, value)  # type: ignore[arg-type]
        else:
            getattr(catalog, method)(value)
