from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class SaveProfile:
    profile_name: str
    unlocked_worlds: set[str] = field(default_factory=lambda: {"world_1"})
    cleared_nodes: set[str] = field(default_factory=set)
    energy_spheres: dict[str, int] = field(default_factory=dict)
    challenge_unlocks: set[str] = field(default_factory=set)
    best_times: dict[str, int] = field(default_factory=dict)
    settings: dict[str, object] = field(default_factory=dict)


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
                    "challenge_unlocks": sorted(profile.challenge_unlocks),
                    "best_times": profile.best_times,
                    "settings": profile.settings,
                }
                for profile in self.profiles
            ],
        }

    @staticmethod
    def from_json_dict(payload: dict[str, object]) -> "SaveSchema":
        profiles: list[SaveProfile] = []
        for item in payload.get("profiles", []):
            profiles.append(
                SaveProfile(
                    profile_name=str(item.get("profile_name", "P1")),
                    unlocked_worlds=set(item.get("unlocked_worlds", ["world_1"])),
                    cleared_nodes=set(item.get("cleared_nodes", [])),
                    energy_spheres={str(k): int(v) for k, v in dict(item.get("energy_spheres", {})).items()},
                    challenge_unlocks=set(item.get("challenge_unlocks", [])),
                    best_times={str(k): int(v) for k, v in dict(item.get("best_times", {})).items()},
                    settings=dict(item.get("settings", {})),
                )
            )
        if not profiles:
            profiles = [SaveProfile("P1"), SaveProfile("P2"), SaveProfile("P3")]
        while len(profiles) < 3:
            profiles.append(SaveProfile(f"P{len(profiles) + 1}"))
        return SaveSchema(save_version=int(payload.get("save_version", 1)), profiles=profiles[:3])


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
