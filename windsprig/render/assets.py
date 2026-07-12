"""Strict manifest-backed loading for mandatory release assets."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final

import pygame

from windsprig.content.models import ArtAssetSpec, AssetManifest

_ASSET_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*\Z")


class MissingAssetError(RuntimeError):
    """Report deterministic mandatory-asset lookup or integrity failures."""


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


def _safe_relative_path(root: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if (
        type(relative) is not str
        or not relative
        or "\\" in relative
        or candidate.is_absolute()
        or candidate.as_posix() != relative
        or any(part in {"", ".", ".."} or ":" in part for part in candidate.parts)
    ):
        raise ValueError("unsafe path")
    current = root
    for index, part in enumerate(candidate.parts):
        current = current / part
        if _is_link_or_reparse(current):
            raise ValueError("unsafe path")
        if index < len(candidate.parts) - 1 and current.exists() and not current.is_dir():
            raise ValueError("unsafe path")
    return current


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_size,
        left.st_mtime_ns,
    ) == (
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
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags | no_follow)
    except OSError as error:
        raise OSError("unreadable regular file") from error
    try:
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


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decoded_image(payload: bytes, name: str) -> pygame.Surface:
    try:
        return pygame.image.load(io.BytesIO(payload), name)
    except (OSError, pygame.error, ValueError) as error:
        raise ValueError("unreadable PNG") from error


def _pixel_sha256(surface: pygame.Surface) -> str:
    return _sha256(pygame.image.tobytes(surface, "RGBA", False))


def _diagnostic_placeholder(spec: ArtAssetSpec, asset_id: str) -> pygame.Surface:
    surface = pygame.Surface((spec.width, spec.height), pygame.SRCALPHA)
    surface.fill((210, 26, 184, 220))
    thickness = max(2, min(spec.width, spec.height) // 12)
    pygame.draw.line(surface, (15, 20, 25), (0, 0), (spec.width - 1, spec.height - 1), thickness)
    pygame.draw.line(surface, (15, 20, 25), (spec.width - 1, 0), (0, spec.height - 1), thickness)
    stripe = int(hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:2], 16) % max(1, spec.width)
    pygame.draw.line(surface, (250, 236, 76), (stripe, 0), (stripe, spec.height - 1), thickness)
    return surface


def _validate_lookup_id(asset_id: object) -> str:
    if type(asset_id) is not str:
        raise TypeError("asset ID must be a string")
    if _ASSET_ID_PATTERN.fullmatch(asset_id) is None:
        raise ValueError("asset ID must be a non-empty lowercase dotted stable ID")
    return asset_id


@dataclass(slots=True)
class AssetCatalog:
    """Own verified runtime assets and expose only typed deterministic lookups."""

    _art_specs: MappingProxyType[str, ArtAssetSpec]
    _images: MappingProxyType[str, pygame.Surface]
    _sound_paths: MappingProxyType[str, Path]
    _font_payload: bytes | None
    _developer_mode: bool
    _font_cache: dict[tuple[int, int], pygame.font.Font] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        root: Path,
        manifest: AssetManifest,
        *,
        developer_mode: bool = False,
    ) -> AssetCatalog:
        """Verify every mandatory file before publishing an immutable catalog."""

        if not isinstance(root, Path):
            raise TypeError("root must be a pathlib.Path")
        if not isinstance(manifest, AssetManifest):
            raise TypeError("manifest must be an AssetManifest")
        if type(developer_mode) is not bool:
            raise TypeError("developer_mode must be a boolean")
        lexical_root = Path(os.path.abspath(root))
        if _is_link_or_reparse(lexical_root) or not lexical_root.is_dir():
            raise MissingAssetError(f"asset root: unsafe or missing directory: {lexical_root}")

        images: dict[str, pygame.Surface] = {}
        sounds: dict[str, Path] = {}
        failures: list[str] = []
        for asset_id, art_spec in manifest.art.items():
            try:
                path = _safe_relative_path(lexical_root, art_spec.path)
                payload = _read_regular_file(path)
                surface = _decoded_image(payload, path.name)
                if surface.get_size() != (art_spec.width, art_spec.height):
                    expected_size = (art_spec.width, art_spec.height)
                    raise ValueError(f"invalid dimensions: expected {expected_size}, received {surface.get_size()}")
                digest = _pixel_sha256(surface)
                if digest != art_spec.pixel_sha256:
                    raise ValueError("decoded pixel hash mismatch")
                images[asset_id] = surface.convert_alpha() if pygame.display.get_surface() is not None else surface
            except (FileNotFoundError, OSError, ValueError) as error:
                if art_spec.mandatory:
                    failures.append(f"{asset_id}: {error}")
                if developer_mode:
                    images[asset_id] = _diagnostic_placeholder(art_spec, asset_id)

        for cue_id, audio_spec in manifest.audio.items():
            try:
                path = _safe_relative_path(lexical_root, audio_spec.path)
                payload = _read_regular_file(path)
                if _sha256(payload) != audio_spec.sha256:
                    raise ValueError("file hash mismatch")
                sounds[cue_id] = path
            except (FileNotFoundError, OSError, ValueError) as error:
                if audio_spec.mandatory:
                    failures.append(f"{cue_id}: {error}")

        font_payload: bytes | None = None
        try:
            font_path = _safe_relative_path(lexical_root, manifest.font.path)
            font_payload = _read_regular_file(font_path)
            if _sha256(font_payload) != manifest.font.sha256:
                raise ValueError("file hash mismatch")
        except (FileNotFoundError, OSError, ValueError) as error:
            if manifest.font.mandatory:
                failures.append(f"font.noto_sans_kr: {error}")
        try:
            license_path = _safe_relative_path(lexical_root, manifest.font.license)
            _read_regular_file(license_path)
        except (FileNotFoundError, OSError, ValueError) as error:
            if manifest.font.mandatory:
                failures.append(f"font.license: {error}")

        if failures and not developer_mode:
            raise MissingAssetError("asset catalog release load failed: " + "; ".join(sorted(failures)))
        return cls(
            MappingProxyType(dict(sorted(manifest.art.items()))),
            MappingProxyType(dict(sorted(images.items()))),
            MappingProxyType(dict(sorted(sounds.items()))),
            font_payload,
            developer_mode,
        )

    def frame_count(self, asset_id: str) -> int:
        """Return the manifest-declared frame count for one verified atlas."""

        stable_id = _validate_lookup_id(asset_id)
        try:
            return self._art_specs[stable_id].frames
        except KeyError:
            raise MissingAssetError(f"unknown art asset ID: {stable_id}") from None

    def frame(self, asset_id: str, frame_index: int) -> pygame.Surface:
        """Return one in-bounds atlas cell using the declared release layout."""

        stable_id = _validate_lookup_id(asset_id)
        if type(frame_index) is not int:
            raise TypeError("frame index must be an integer")
        try:
            spec = self._art_specs[stable_id]
            surface = self._images[stable_id]
        except KeyError:
            raise MissingAssetError(f"unknown art asset ID: {stable_id}") from None
        if not 0 <= frame_index < spec.frames:
            raise IndexError(f"frame index {frame_index} is outside {stable_id} [0, {spec.frames})")

        if stable_id == "player.sprig":
            columns, rows = 8, 7
        elif stable_id.startswith("boss."):
            columns, rows = 6, 3
        elif stable_id.endswith(".background"):
            columns, rows = 1, spec.frames
        else:
            columns, rows = spec.frames, 1
        if columns * rows != spec.frames or spec.width % columns or spec.height % rows:
            raise MissingAssetError(f"invalid manifest frame grid for {stable_id}")
        cell_width = spec.width // columns
        cell_height = spec.height // rows
        column = frame_index % columns
        row = frame_index // columns
        return surface.subsurface(pygame.Rect(column * cell_width, row * cell_height, cell_width, cell_height))

    def image(self, asset_id: str) -> pygame.Surface:
        """Return one verified image or a deterministic missing-ID error."""

        stable_id = _validate_lookup_id(asset_id)
        try:
            return self._images[stable_id]
        except KeyError:
            raise MissingAssetError(f"unknown art asset ID: {stable_id}") from None

    def sound_path(self, cue_id: str) -> Path:
        """Return one verified audio path or a deterministic missing-ID error."""

        stable_id = _validate_lookup_id(cue_id)
        try:
            return self._sound_paths[stable_id]
        except KeyError:
            raise MissingAssetError(f"unknown audio asset ID: {stable_id}") from None

    def font(self, size_px: int, weight: int = 500) -> pygame.font.Font:
        """Return a cached verified font at one validated presentation size."""

        if type(size_px) is not int:
            raise TypeError("font size must be an integer")
        if size_px <= 0:
            raise ValueError("font size must be positive")
        if type(weight) is not int:
            raise TypeError("font weight must be an integer")
        if not 1 <= weight <= 1000:
            raise ValueError("font weight must be in [1, 1000]")
        key = (size_px, weight)
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached
        pygame.font.init()
        if self._font_payload is None:
            if not self._developer_mode:
                raise MissingAssetError("font.noto_sans_kr: verified payload is unavailable")
            font = pygame.font.Font(None, size_px)
        else:
            font = pygame.font.Font(io.BytesIO(self._font_payload), size_px)
        font.set_bold(weight >= 700)
        self._font_cache[key] = font
        return font


__all__ = ["AssetCatalog", "MissingAssetError"]
