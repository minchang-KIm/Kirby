"""Compose verified release audio into platform services at initialization time."""

from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType

from windsprig.audio.catalog import MUSIC_CUE_IDS, SFX_CUE_IDS
from windsprig.config import GameConfig
from windsprig.content.loader import load_asset_manifest
from windsprig.render.assets import AssetCatalog, MissingAssetError


def load_canonical_sound_paths(config: GameConfig) -> MappingProxyType[str, Path]:
    """Resolve the exact verified release inventory for deferred mixer decoding.

    The content manifest owns cue-to-file records and :class:`AssetCatalog`
    owns byte, container, and path integrity. This composition boundary merely
    proves that the resulting set is the canonical 28/29 release inventory.
    """

    if not isinstance(config, GameConfig):
        raise TypeError("config must be a GameConfig")
    content_dir = Path(os.path.abspath(config.content_dir))
    manifest = load_asset_manifest(content_dir / "assets.json")
    asset_root = content_dir.parent.parent / "assets"
    paths = AssetCatalog.verified_audio_paths(asset_root, manifest)
    expected = MUSIC_CUE_IDS | SFX_CUE_IDS
    if set(paths) != expected:
        missing = sorted(expected - paths.keys())
        unexpected = sorted(paths.keys() - expected)
        raise MissingAssetError(
            "canonical audio inventory mismatch: "
            f"missing={missing!r}; unexpected={unexpected!r}"
        )
    return paths


__all__ = ["load_canonical_sound_paths"]
