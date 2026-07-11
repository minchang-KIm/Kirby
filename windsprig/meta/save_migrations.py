"""Deterministic, validated conversion from prototype-v1 saves to save v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from windsprig.content.loader import CampaignCatalog

from .save_models import (
    AccessibilitySettings,
    AudioSettings,
    ControlSettings,
    DisplaySettings,
    GlobalSettings,
    SaveData,
    SaveProfile,
    _id_list,
    _identifier,
    _object,
    _profile_name,
    _require_fields,
    _strict_bool,
    _strict_int,
    _volume,
)


@dataclass(frozen=True, slots=True)
class SaveMigrationCatalog:
    """Frozen stable-mote and campaign-successor identities used by v1 migration."""

    mote_ids_by_stage: Mapping[str, tuple[str, ...]]
    next_node_by_node: Mapping[str, str]
    stage_id_by_node: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.mote_ids_by_stage, Mapping):
            raise ValueError("mote_ids_by_stage must be a mapping")
        mote_ids_by_stage: dict[str, tuple[str, ...]] = {}
        all_mote_ids: set[str] = set()
        for raw_stage_id, raw_mote_ids in self.mote_ids_by_stage.items():
            stage_id = _identifier("mote_ids_by_stage stage ID", raw_stage_id)
            if not isinstance(raw_mote_ids, (tuple, list)):
                raise ValueError(f"mote IDs for {stage_id} must be an ordered sequence")
            mote_ids = tuple(_identifier(f"mote ID for {stage_id}", value) for value in raw_mote_ids)
            if len(mote_ids) != len(set(mote_ids)) or any(mote_id in all_mote_ids for mote_id in mote_ids):
                raise ValueError("migration catalog contains duplicate mote IDs")
            all_mote_ids.update(mote_ids)
            mote_ids_by_stage[stage_id] = mote_ids

        if not isinstance(self.next_node_by_node, Mapping):
            raise ValueError("next_node_by_node must be a mapping")
        next_node_by_node: dict[str, str] = {}
        for raw_node_id, raw_next_node_id in self.next_node_by_node.items():
            node_id = _identifier("next_node_by_node node ID", raw_node_id)
            next_node_id = _identifier(f"next node for {node_id}", raw_next_node_id)
            if node_id == next_node_id:
                raise ValueError(f"next node for {node_id} must be a different ID")
            next_node_by_node[node_id] = next_node_id

        if not isinstance(self.stage_id_by_node, Mapping):
            raise ValueError("stage_id_by_node must be a mapping")
        stage_id_by_node: dict[str, str] = {}
        for raw_node_id, raw_stage_id in self.stage_id_by_node.items():
            node_id = _identifier("stage_id_by_node node ID", raw_node_id)
            stage_id = _identifier(f"stage ID for {node_id}", raw_stage_id)
            if stage_id not in mote_ids_by_stage:
                raise ValueError(f"stage ID for {node_id} is not in mote_ids_by_stage: {stage_id}")
            stage_id_by_node[node_id] = stage_id

        object.__setattr__(
            self,
            "mote_ids_by_stage",
            MappingProxyType(dict(sorted(mote_ids_by_stage.items()))),
        )
        object.__setattr__(
            self,
            "next_node_by_node",
            MappingProxyType(dict(sorted(next_node_by_node.items()))),
        )
        object.__setattr__(
            self,
            "stage_id_by_node",
            MappingProxyType(dict(sorted(stage_id_by_node.items()))),
        )

    @classmethod
    def from_campaign(cls, campaign: CampaignCatalog) -> SaveMigrationCatalog:
        """Freeze current campaign order into compatibility IDs and successor edges."""

        if not isinstance(campaign, CampaignCatalog):
            raise ValueError("campaign must be CampaignCatalog")
        mote_ids_by_stage: dict[str, tuple[str, ...]] = {}
        for stage_id, stage in sorted(campaign.stages.items()):
            if stage.stage_id != stage_id:
                raise ValueError(f"campaign stage key does not match stage_id: {stage_id}")
            if len(stage.energy_spheres) != 3:
                raise ValueError(f"{stage_id} must contain exactly three prototype collectible positions")
            # Position order is the compatibility seam; later art/layout changes must retain these IDs.
            mote_ids_by_stage[stage_id] = tuple(
                f"{stage_id}:mote:{index}" for index, _ in enumerate(stage.energy_spheres, start=1)
            )

        # Stable world IDs define cross-world succession without relying on mapping insertion order.
        ordered_nodes = [
            node
            for world_id in sorted(campaign.worlds)
            for node in campaign.worlds[world_id]
        ]
        node_ids = [node.node_id for node in ordered_nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("campaign contains duplicate node IDs")
        references_by_stage: dict[str, list[str]] = {}
        for world_id in sorted(campaign.worlds):
            for node in campaign.worlds[world_id]:
                if node.world_id != world_id:
                    raise ValueError(
                        f"node {node.node_id} world_id does not match catalog world {world_id}"
                    )
                if node.stage_id not in campaign.stages:
                    raise ValueError(f"node {node.node_id} references missing stage {node.stage_id}")
                references_by_stage.setdefault(node.stage_id, []).append(node.node_id)

        multiply_referenced = sorted(
            stage_id
            for stage_id, references in references_by_stage.items()
            if len(references) > 1
        )
        if multiply_referenced:
            raise ValueError(f"stage referenced more than once: {multiply_referenced}")
        orphan_stages = sorted(set(campaign.stages) - set(references_by_stage))
        if orphan_stages:
            raise ValueError(f"orphan stage IDs are not referenced by campaign nodes: {orphan_stages}")

        for node in ordered_nodes:
            stage = campaign.stages[node.stage_id]
            if stage.node_id != node.node_id:
                raise ValueError(
                    f"stage {stage.stage_id} node_id does not match node {node.node_id}"
                )
            if stage.world_id != node.world_id:
                raise ValueError(
                    f"stage {stage.stage_id} world_id does not match node {node.node_id}"
                )
        next_node_by_node = {
            node.node_id: ordered_nodes[index + 1].node_id
            for index, node in enumerate(ordered_nodes[:-1])
        }
        stage_id_by_node = {node.node_id: node.stage_id for node in ordered_nodes}
        return cls(
            mote_ids_by_stage=mote_ids_by_stage,
            next_node_by_node=next_node_by_node,
            stage_id_by_node=stage_id_by_node,
        )


def migration_catalog(campaign: CampaignCatalog) -> SaveMigrationCatalog:
    """Build the migration compatibility catalog from campaign content order."""

    return SaveMigrationCatalog.from_campaign(campaign)


@dataclass(frozen=True, slots=True)
class _LegacyProfile:
    profile_name: str
    unlocked_worlds: frozenset[str]
    cleared_nodes: frozenset[str]
    energy_spheres: Mapping[str, int]
    collected_mote_ids: frozenset[str] | None
    best_times: Mapping[str, int]
    clear_counts: Mapping[str, int] | None
    challenge_unlocks: frozenset[str]
    settings: GlobalSettings


_LEGACY_SAVE_FIELDS = frozenset({"save_version", "profiles"})
_LEGACY_PROFILE_FIELDS = frozenset(
    {
        "profile_name",
        "unlocked_worlds",
        "cleared_nodes",
        "energy_spheres",
        "collected_mote_ids",
        "best_times",
        "clear_counts",
        "challenge_unlocks",
        "settings",
    }
)
_LEGACY_SETTINGS_FIELDS = frozenset(
    {
        "fullscreen",
        "integer_scaling",
        "master_volume",
        "music_volume",
        "sfx_volume",
        "muted",
        "screen_shake",
        "reduced_motion",
        "draw_toggle",
        "guard_toggle",
        "language",
        "keyboard_p1_preset",
        "keyboard_p2_preset",
        "gamepad_mapping",
    }
)


def _legacy_int_map(payload: object, name: str, *, allow_negative: bool) -> Mapping[str, int]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    values: dict[str, int] = {}
    for raw_key, raw_value in payload.items():
        key = _identifier(f"{name} key", raw_key)
        values[key] = _strict_int(f"{name}[{key}]", raw_value, non_negative=not allow_negative)
    return MappingProxyType(dict(sorted(values.items())))


def _legacy_settings(payload: object) -> GlobalSettings:
    raw = _object(payload, _LEGACY_SETTINGS_FIELDS, "prototype settings")
    language = raw.get("language", "en")
    if language not in ("en", "ko"):
        raise ValueError("language must be en or ko")
    return GlobalSettings(
        display=DisplaySettings(
            fullscreen=_strict_bool("fullscreen", raw.get("fullscreen", False)),
            integer_scaling=_strict_bool("integer_scaling", raw.get("integer_scaling", False)),
        ),
        audio=AudioSettings(
            master_volume=_volume("master_volume", raw.get("master_volume", 1.0)),
            music_volume=_volume("music_volume", raw.get("music_volume", 0.8)),
            sfx_volume=_volume("sfx_volume", raw.get("sfx_volume", 0.9)),
            muted=_strict_bool("muted", raw.get("muted", False)),
        ),
        accessibility=AccessibilitySettings(
            screen_shake=_strict_bool("screen_shake", raw.get("screen_shake", True)),
            reduced_motion=_strict_bool("reduced_motion", raw.get("reduced_motion", False)),
            draw_toggle=_strict_bool("draw_toggle", raw.get("draw_toggle", False)),
            guard_toggle=_strict_bool("guard_toggle", raw.get("guard_toggle", False)),
        ),
        language=language,
        controls=ControlSettings(
            keyboard_p1_preset=_identifier(
                "keyboard_p1_preset",
                raw.get("keyboard_p1_preset", "wasd"),
            ),
            keyboard_p2_preset=_identifier(
                "keyboard_p2_preset",
                raw.get("keyboard_p2_preset", "arrows"),
            ),
            gamepad_mapping=_identifier("gamepad_mapping", raw.get("gamepad_mapping", "standard")),
        ),
    )


def _legacy_profile(payload: object) -> _LegacyProfile:
    raw = _object(payload, _LEGACY_PROFILE_FIELDS, "prototype profile")
    _require_fields(raw, frozenset({"profile_name"}), "prototype profile")
    return _LegacyProfile(
        profile_name=_profile_name("profile_name", raw["profile_name"]),
        unlocked_worlds=_id_list(raw.get("unlocked_worlds", ["world_1"]), "unlocked_worlds"),
        cleared_nodes=_id_list(raw.get("cleared_nodes", []), "cleared_nodes"),
        energy_spheres=_legacy_int_map(
            raw.get("energy_spheres", {}),
            "energy_spheres",
            allow_negative=True,
        ),
        collected_mote_ids=(
            _id_list(raw["collected_mote_ids"], "collected_mote_ids")
            if "collected_mote_ids" in raw
            else None
        ),
        best_times=_legacy_int_map(raw.get("best_times", {}), "best_times", allow_negative=False),
        clear_counts=(
            _legacy_int_map(raw["clear_counts"], "clear_counts", allow_negative=False)
            if "clear_counts" in raw
            else None
        ),
        challenge_unlocks=_id_list(
            raw.get("challenge_unlocks", []),
            "challenge_unlocks",
        ),
        settings=_legacy_settings(raw.get("settings", {})),
    )


def _validated_v1_profiles(payload: object) -> tuple[_LegacyProfile, ...]:
    raw = _object(payload, _LEGACY_SAVE_FIELDS, "prototype save")
    _require_fields(raw, frozenset({"save_version", "profiles"}), "prototype save")
    version = _strict_int("save_version", raw["save_version"])
    if version != 1:
        raise ValueError("save_version must be 1 for prototype migration")
    profiles = raw["profiles"]
    if not isinstance(profiles, list):
        raise ValueError("prototype profiles must be a list")
    if not profiles:
        raise ValueError("prototype save must contain at least one profile")
    if len(profiles) > 3:
        raise ValueError("prototype save must contain at most three profiles")
    return tuple(_legacy_profile(profile) for profile in profiles)


def migrate_v1(payload: object, catalog: SaveMigrationCatalog) -> SaveData:
    """Validate and deterministically migrate one prototype-v1 save document."""

    if not isinstance(catalog, SaveMigrationCatalog):
        raise ValueError("catalog must be SaveMigrationCatalog")
    raw_profiles = _validated_v1_profiles(payload)
    migrated: list[SaveProfile] = []
    for index in range(3):
        if index >= len(raw_profiles):
            migrated.append(SaveProfile(profile_id=f"profile_{index + 1}", display_name=f"Sprig {index + 1}"))
            continue

        raw = raw_profiles[index]
        unlocked_nodes = set(raw.cleared_nodes)
        if not unlocked_nodes:
            unlocked_nodes.add("world_1_node_1")
        for node_id in sorted(raw.cleared_nodes):
            next_node = catalog.next_node_by_node.get(node_id)
            if next_node is not None:
                unlocked_nodes.add(next_node)

        if raw.collected_mote_ids is None:
            collected_mote_ids: set[str] = set()
            for stage_id in sorted(raw.energy_spheres):
                available = catalog.mote_ids_by_stage.get(stage_id, ())
                # Negative prototype counts represented no collectibles; clamping prevents minted replay currency.
                count = min(max(raw.energy_spheres[stage_id], 0), len(available))
                collected_mote_ids.update(available[:count])
        else:
            known_mote_ids = {
                mote_id
                for stage_mote_ids in catalog.mote_ids_by_stage.values()
                for mote_id in stage_mote_ids
            }
            unknown_mote_ids = sorted(raw.collected_mote_ids - known_mote_ids)
            if unknown_mote_ids:
                raise ValueError(f"collected_mote_ids are not in the migration catalog: {unknown_mote_ids}")
            collected_mote_ids = set(raw.collected_mote_ids)

        best_times_ms: dict[str, int] = {}
        for saved_id in sorted(raw.best_times):
            if saved_id in catalog.stage_id_by_node:
                stage_id = catalog.stage_id_by_node[saved_id]
            elif saved_id in catalog.mote_ids_by_stage:
                stage_id = saved_id
            else:
                raise ValueError(f"best_times has no stage mapping for {saved_id}")
            previous = best_times_ms.get(stage_id)
            elapsed_ms = raw.best_times[saved_id]
            best_times_ms[stage_id] = elapsed_ms if previous is None else min(previous, elapsed_ms)
        clear_counts: dict[str, int] = {}
        for node_id in sorted(raw.cleared_nodes):
            mapped_stage_id = catalog.stage_id_by_node.get(node_id)
            if mapped_stage_id is None:
                raise ValueError(f"stage mapping is required for cleared node {node_id}")
            clear_counts[mapped_stage_id] = 1
        if raw.clear_counts is not None:
            for stage_id, count in raw.clear_counts.items():
                if stage_id not in catalog.mote_ids_by_stage:
                    raise ValueError(f"clear_counts stage is not in the migration catalog: {stage_id}")
                clear_counts[stage_id] = max(clear_counts.get(stage_id, 0), count)

        migrated.append(
            SaveProfile(
                profile_id=f"profile_{index + 1}",
                display_name=raw.profile_name,
                unlocked_nodes=frozenset(unlocked_nodes),
                unlocked_worlds=raw.unlocked_worlds,
                collected_mote_ids=frozenset(collected_mote_ids),
                best_times_ms=best_times_ms,
                clear_counts=clear_counts,
                challenge_rewards=raw.challenge_unlocks,
            )
        )
    return SaveData(
        profiles=(migrated[0], migrated[1], migrated[2]),
        settings=raw_profiles[0].settings,
        prototype_imported=True,
    )
