from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .save_models import _id_frozenset, _immutable_int_map


@dataclass
class SaveProfile:
    """Mutable prototype profile with lossless fields used only until save v2 replaces it."""

    profile_name: str
    unlocked_worlds: set[str] = field(default_factory=lambda: {"world_1"})
    cleared_nodes: set[str] = field(default_factory=set)
    energy_spheres: dict[str, int] = field(default_factory=dict)
    collected_mote_ids: set[str] | None = None
    challenge_unlocks: set[str] = field(default_factory=set)
    best_times: dict[str, int] = field(default_factory=dict)
    clear_counts: dict[str, int] | None = None
    settings: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # These extension fields keep the temporary v1 app bridge from erasing v2 identities.
        if self.collected_mote_ids is not None:
            self.collected_mote_ids = set(
                _id_frozenset(self.collected_mote_ids, "collected_mote_ids")
            )
        if self.clear_counts is not None:
            self.clear_counts = dict(_immutable_int_map(self.clear_counts, "clear_counts"))


@dataclass
class SaveSchema:
    save_version: int = 1
    profiles: list[SaveProfile] = field(
        default_factory=lambda: [SaveProfile("P1"), SaveProfile("P2"), SaveProfile("P3")]
    )

    def to_json_dict(self) -> dict[str, object]:
        return {
            "save_version": self.save_version,
            "profiles": [
                {
                    "profile_name": profile.profile_name,
                    "unlocked_worlds": sorted(profile.unlocked_worlds),
                    "cleared_nodes": sorted(profile.cleared_nodes),
                    "energy_spheres": profile.energy_spheres,
                    **(
                        {"collected_mote_ids": sorted(profile.collected_mote_ids)}
                        if profile.collected_mote_ids is not None
                        else {}
                    ),
                    "challenge_unlocks": sorted(profile.challenge_unlocks),
                    "best_times": profile.best_times,
                    **(
                        {"clear_counts": profile.clear_counts}
                        if profile.clear_counts is not None
                        else {}
                    ),
                    "settings": profile.settings,
                }
                for profile in self.profiles
            ],
        }

    @staticmethod
    def from_json_dict(payload: dict[str, object]) -> SaveSchema:
        profiles: list[SaveProfile] = []
        raw_profiles = payload.get("profiles", [])
        if not isinstance(raw_profiles, list):
            raise ValueError("profiles must be a list")
        for item in raw_profiles:
            if not isinstance(item, dict):
                raise ValueError("profile must be an object")
            profiles.append(
                SaveProfile(
                    profile_name=str(item.get("profile_name", "P1")),
                    unlocked_worlds=set(item.get("unlocked_worlds", ["world_1"])),
                    cleared_nodes=set(item.get("cleared_nodes", [])),
                    energy_spheres={str(k): int(v) for k, v in dict(item.get("energy_spheres", {})).items()},
                    collected_mote_ids=(
                        set(_id_frozenset(item["collected_mote_ids"], "collected_mote_ids"))
                        if "collected_mote_ids" in item
                        else None
                    ),
                    challenge_unlocks=set(item.get("challenge_unlocks", [])),
                    best_times={str(k): int(v) for k, v in dict(item.get("best_times", {})).items()},
                    clear_counts=(
                        dict(_immutable_int_map(item["clear_counts"], "clear_counts"))
                        if "clear_counts" in item
                        else None
                    ),
                    settings=dict(item.get("settings", {})),
                )
            )
        if not profiles:
            profiles = [SaveProfile("P1"), SaveProfile("P2"), SaveProfile("P3")]
        while len(profiles) < 3:
            profiles.append(SaveProfile(f"P{len(profiles) + 1}"))
        save_version = payload.get("save_version", 1)
        if type(save_version) is not int:
            raise ValueError("save_version must be an integer")
        return SaveSchema(save_version=save_version, profiles=profiles[:3])


class SaveManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> SaveSchema:
        if not self.path.exists():
            schema = SaveSchema()
            self.save(schema)
            return schema
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return SaveSchema.from_json_dict(payload)

    def save(self, schema: SaveSchema) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(schema.to_json_dict(), indent=2), encoding="utf-8")
