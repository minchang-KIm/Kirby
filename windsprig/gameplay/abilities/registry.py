"""Strategy registry with strict public ability metadata validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from windsprig.content.loader import PUBLIC_ABILITY_IDS

from .base import AbilityStrategy, NoneAbilityStrategy
from .bloomblade import BloombladeStrategy
from .cinder import CinderStrategy
from .galehook import GalehookStrategy
from .stoneheart import StoneheartStrategy
from .tempest import TempestStrategy
from .voltsong import VoltsongStrategy

METADATA_FIELDS = frozenset({"strategy", "icon_id", "palette_token", "enemy_source_tag"})


@dataclass(frozen=True, slots=True)
class _ObjectMembers:
    values: tuple[tuple[str, object], ...]


def _preserve_object_members(values: list[tuple[str, object]]) -> _ObjectMembers:
    return _ObjectMembers(tuple(values))


def _reject_duplicate_members(value: object, path: str = "") -> object:
    if isinstance(value, _ObjectMembers):
        decoded: dict[str, object] = {}
        for name, member in value.values:
            member_path = f"{path}.{name}" if path else name
            if name in decoded:
                raise ValueError(f"duplicate ability metadata member: {member_path}")
            decoded[name] = _reject_duplicate_members(member, member_path)
        return decoded
    if isinstance(value, list):
        return [_reject_duplicate_members(member, f"{path}[{index}]") for index, member in enumerate(value)]
    return value


def _decode_metadata(source: str) -> object:
    preserved: object = json.loads(source, object_pairs_hook=_preserve_object_members)
    return _reject_duplicate_members(preserved)


class AbilityRegistry:
    """Resolve registered strategies and fail unknown names to the ``none`` sentinel."""

    def __init__(self) -> None:
        self._strategies: dict[str, AbilityStrategy] = {}

    def register(self, strategy: AbilityStrategy) -> None:
        """Register or replace the implementation owning one stable strategy name."""
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> AbilityStrategy:
        """Resolve ``name`` or return the safe empty strategy."""
        fallback = self._strategies.get("none")
        if fallback is None:
            raise RuntimeError("ability registry has no 'none' strategy")
        return self._strategies.get(name, fallback)

    def names(self) -> list[str]:
        """Return registered strategy names in deterministic order."""
        return sorted(self._strategies)

    def validate_metadata(self, path: Path) -> None:
        """Reject metadata that changes the six public IDs or embeds gameplay tuning."""
        payload = _decode_metadata(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"abilities"}:
            raise ValueError("abilities metadata must contain only the 'abilities' object")
        raw_abilities = payload["abilities"]
        if not isinstance(raw_abilities, dict) or set(raw_abilities) != PUBLIC_ABILITY_IDS:
            raise ValueError("abilities metadata must define exactly the six public ability IDs")
        for ability_id in sorted(PUBLIC_ABILITY_IDS):
            metadata = raw_abilities[ability_id]
            if not isinstance(metadata, dict) or set(metadata) != METADATA_FIELDS:
                raise ValueError(f"ability metadata for {ability_id!r} has invalid fields")
            if any(not isinstance(value, str) or not value for value in metadata.values()):
                raise ValueError(f"ability metadata for {ability_id!r} must use non-empty strings")
            if metadata["strategy"] != ability_id:
                raise ValueError(f"ability metadata for {ability_id!r} has mismatched strategy")


def create_default_registry(content_dir: Path) -> AbilityRegistry:
    """Build the current typed strategies after validating shared presentation metadata."""
    registry = AbilityRegistry()
    for strategy in (
        NoneAbilityStrategy(),
        BloombladeStrategy(),
        CinderStrategy(),
        VoltsongStrategy(),
        GalehookStrategy(),
        StoneheartStrategy(),
        TempestStrategy(),
    ):
        registry.register(strategy)
    registry.validate_metadata(content_dir / "abilities.json")
    return registry
