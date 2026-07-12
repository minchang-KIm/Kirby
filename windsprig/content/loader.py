"""Strictly load canonical immutable release content from JSON documents."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .models import (
    AbilityId,
    ArtAssetSpec,
    AssetManifest,
    AttackMarker,
    AudioAssetSpec,
    AudioBus,
    BossAttackSpec,
    BossPhaseSpec,
    BossSpec,
    CampaignCatalog,
    CatalogBundle,
    CheckpointSpec,
    EnemySpawn,
    FontAssetSpec,
    InteractionKind,
    InteractionSpec,
    LocaleCatalog,
    MoteSpec,
    NavigationGraph,
    NavigationNode,
    ParameterValue,
    RewardCatalog,
    RewardKind,
    RewardSpec,
    RouteKind,
    StageSpec,
    ValidationIssue,
    ValidationReport,
    Vulnerability,
    WorldNode,
    WorldSpec,
)

PUBLIC_ABILITY_IDS = frozenset({"bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest"})
INTERACTION_KINDS = frozenset(
    {
        "gust_lift",
        "breakable",
        "conveyor",
        "heat_vent",
        "timed_shutter",
        "current",
        "buoyant_pod",
        "falling_water",
        "rail",
        "conductor",
        "rotating_tower",
        "mirror",
        "color_beam",
        "gravity_bloom",
        "silence_field",
        "ability_lock",
        "breakable_floor",
        "switch",
    }
)
ROUTE_KINDS = frozenset({"main", "optional", "mastery"})
ATTACK_MARKERS = frozenset({"ground", "silhouette", "lane", "orbit", "beam", "arena"})
VULNERABILITY_STATES = frozenset({"vulnerable", "armored", "hidden", "invulnerable"})
REWARD_KINDS = frozenset({"challenge", "gallery", "palette"})

# Save migration still documents prototype-to-public IDs. The strict content parser
# never consults this table and therefore cannot accept these aliases.
LEGACY_ABILITY_IDS: Mapping[str, AbilityId] = {
    "sword": "bloomblade",
    "spear": "bloomblade",
    "fighter": "bloomblade",
    "fire": "cinder",
    "monster_flame": "cinder",
    "beam": "voltsong",
    "spark": "voltsong",
    "cutter": "galehook",
    "whip": "galehook",
    "ninja": "galehook",
    "parasol": "galehook",
    "ice": "stoneheart",
    "hammer": "stoneheart",
    "grand_hammer": "stoneheart",
    "ultra_sword": "tempest",
}


class ContentError(ValueError):
    """Report one parse or schema failure at a deterministic full JSON path."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


@dataclass(frozen=True, slots=True)
class _ObjectPairs:
    pairs: tuple[tuple[str, object], ...]


def _object_pairs(pairs: list[tuple[str, object]]) -> _ObjectPairs:
    return _ObjectPairs(tuple(pairs))


def _load_json(path: Path, document_path: str) -> object:
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ContentError(document_path, f"file not found: {path}") from None
    except UnicodeError as error:
        raise ContentError(document_path, "invalid UTF-8") from error
    except OSError as error:
        raise ContentError(document_path, f"could not read {path}: {error}") from error
    try:
        return json.loads(source, object_pairs_hook=_object_pairs)
    except (json.JSONDecodeError, RecursionError) as error:
        if isinstance(error, json.JSONDecodeError):
            detail = f"invalid JSON at line {error.lineno} column {error.colno}"
        else:
            detail = "invalid JSON nesting"
        raise ContentError(document_path, detail) from error


def _fields(
    value: object,
    path: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if not isinstance(value, _ObjectPairs):
        raise ContentError(path, "must be an object")
    result: dict[str, object] = {}
    duplicates: set[str] = set()
    for key, item in value.pairs:
        if key in result:
            duplicates.add(key)
        else:
            result[key] = item
    if duplicates:
        duplicate = sorted(duplicates)[0]
        raise ContentError(f"{path}.{duplicate}", "duplicate field")
    unknown = sorted(result.keys() - (required | optional))
    if unknown:
        raise ContentError(f"{path}.{unknown[0]}", "unknown field")
    missing = sorted(required - result.keys())
    if missing:
        raise ContentError(f"{path}.{missing[0]}", "missing field")
    return result


def _parameter_fields(value: object, path: str) -> tuple[tuple[str, ParameterValue], ...]:
    if not isinstance(value, _ObjectPairs):
        raise ContentError(path, "must be an object")
    result: dict[str, ParameterValue] = {}
    duplicates: set[str] = set()
    for key, item in value.pairs:
        if key in result:
            duplicates.add(key)
            continue
        result[key] = _parameter(item, f"{path}.{key}")
    if duplicates:
        duplicate = sorted(duplicates)[0]
        raise ContentError(f"{path}.{duplicate}", "duplicate field")
    return tuple(sorted(result.items()))


def _named_objects[T](
    value: object,
    path: str,
    convert: Callable[[object, str], T],
) -> dict[str, T]:
    if not isinstance(value, _ObjectPairs):
        raise ContentError(path, "must be an object")
    raw: dict[str, object] = {}
    duplicates: set[str] = set()
    for key, item in value.pairs:
        if key in raw:
            duplicates.add(key)
        else:
            raw[key] = item
    if duplicates:
        duplicate = sorted(duplicates)[0]
        raise ContentError(f"{path}.{duplicate}", "duplicate field")
    return {key: convert(raw[key], f"{path}.{key}") for key in sorted(raw)}


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ContentError(path, "must be a list")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContentError(path, "must be a non-empty string")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentError(path, "must be an integer")
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContentError(path, "must be a number")
    try:
        result = float(value)
    except OverflowError:
        raise ContentError(path, "must be finite") from None
    if not math.isfinite(result):
        raise ContentError(path, "must be finite")
    return result


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ContentError(path, "must be a boolean")
    return value


def _parameter(value: object, path: str) -> ParameterValue:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContentError(path, "must be finite")
        return value
    if isinstance(value, str):
        return value
    raise ContentError(path, "must be a string, boolean, integer, or number")


def _pair[T](
    value: object,
    path: str,
    convert: Callable[[object, str], T],
) -> tuple[T, T]:
    values = _array(value, path)
    if len(values) != 2:
        raise ContentError(path, "must contain exactly two values")
    return convert(values[0], f"{path}[0]"), convert(values[1], f"{path}[1]")


def _sequence[T](
    value: object,
    path: str,
    convert: Callable[[object, str], T],
) -> tuple[T, ...]:
    return tuple(convert(item, f"{path}[{index}]") for index, item in enumerate(_array(value, path)))


def _enum(value: object, path: str, allowed: frozenset[str], name: str) -> str:
    text = _text(value, path)
    if text not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ContentError(path, f"{name} must be one of {choices}; received {text!r}")
    return text


def _route(value: object, path: str) -> RouteKind:
    return cast(RouteKind, _enum(value, path, ROUTE_KINDS, "route"))


def _interaction_kind(value: object, path: str) -> InteractionKind:
    return cast(
        InteractionKind,
        _enum(value, path, INTERACTION_KINDS, "interaction kind"),
    )


def _ability_id(value: object, path: str) -> AbilityId | None:
    if value is None:
        return None
    text = _text(value, path)
    if text not in PUBLIC_ABILITY_IDS:
        raise ContentError(path, f"unknown public ability ID: {text}")
    return cast(AbilityId, text)


def _canonical_mote_id(value: object, path: str, stage_id: str) -> str:
    mote_id = _text(value, path)
    prefix = f"{stage_id}:mote:"
    suffix = mote_id[len(prefix) :] if mote_id.startswith(prefix) else ""
    if not suffix or not suffix.isascii() or not suffix.isdigit() or suffix.startswith("0"):
        raise ContentError(path, f"must match {prefix}<positive ASCII integer>")
    return mote_id


def _load_world_node(value: object, path: str, world_id: str) -> WorldNode:
    raw = _fields(
        value,
        path,
        frozenset({"node_id", "stage_id", "requires", "rewards", "position", "is_boss"}),
    )
    return WorldNode(
        node_id=_text(raw["node_id"], f"{path}.node_id"),
        world_id=world_id,
        stage_id=_text(raw["stage_id"], f"{path}.stage_id"),
        requires=_sequence(raw["requires"], f"{path}.requires", _text),
        rewards=_sequence(raw["rewards"], f"{path}.rewards", _text),
        position=_pair(raw["position"], f"{path}.position", _integer),
        is_boss=_boolean(raw["is_boss"], f"{path}.is_boss"),
    )


def _load_world(value: object, path: str) -> WorldSpec:
    raw = _fields(
        value,
        path,
        frozenset({"world_id", "nodes"}),
        frozenset({"order", "name_key", "identity_key", "mechanic_keys", "palette_id"}),
    )
    world_id = _text(raw["world_id"], f"{path}.world_id")
    nodes = _sequence(
        raw["nodes"],
        f"{path}.nodes",
        lambda item, item_path: _load_world_node(item, item_path, world_id),
    )
    return WorldSpec(
        world_id=world_id,
        order=_integer(raw["order"], f"{path}.order") if "order" in raw else 0,
        name_key=_text(raw["name_key"], f"{path}.name_key") if "name_key" in raw else "",
        identity_key=(_text(raw["identity_key"], f"{path}.identity_key") if "identity_key" in raw else ""),
        mechanic_keys=(
            _sequence(raw["mechanic_keys"], f"{path}.mechanic_keys", _text) if "mechanic_keys" in raw else ()
        ),
        palette_id=(_text(raw["palette_id"], f"{path}.palette_id") if "palette_id" in raw else ""),
        nodes=nodes,
    )


def _load_enemy(value: object, path: str) -> EnemySpawn:
    raw = _fields(
        value,
        path,
        frozenset({"x", "y", "kind", "ability_id", "patrol_left", "patrol_right"}),
        frozenset({"spawn_id", "elite"}),
    )
    return EnemySpawn(
        x=_number(raw["x"], f"{path}.x"),
        y=_number(raw["y"], f"{path}.y"),
        kind=_text(raw["kind"], f"{path}.kind"),
        ability_id=_ability_id(raw["ability_id"], f"{path}.ability_id"),
        patrol_left=_number(raw["patrol_left"], f"{path}.patrol_left"),
        patrol_right=_number(raw["patrol_right"], f"{path}.patrol_right"),
        spawn_id=(_text(raw["spawn_id"], f"{path}.spawn_id") if "spawn_id" in raw else ""),
        elite=_boolean(raw["elite"], f"{path}.elite") if "elite" in raw else False,
    )


def _load_mote(value: object, path: str, stage_id: str) -> MoteSpec:
    raw = _fields(
        value,
        path,
        frozenset({"mote_id", "tile_x", "tile_y"}),
        frozenset({"route"}),
    )
    return MoteSpec(
        mote_id=_canonical_mote_id(raw["mote_id"], f"{path}.mote_id", stage_id),
        tile_x=_integer(raw["tile_x"], f"{path}.tile_x"),
        tile_y=_integer(raw["tile_y"], f"{path}.tile_y"),
        route=_route(raw["route"], f"{path}.route") if "route" in raw else "main",
    )


def _load_checkpoint(value: object, path: str) -> CheckpointSpec:
    raw = _fields(
        value,
        path,
        frozenset({"checkpoint_id", "tile_x", "tile_y"}),
    )
    return CheckpointSpec(
        checkpoint_id=_text(raw["checkpoint_id"], f"{path}.checkpoint_id"),
        tile_x=_integer(raw["tile_x"], f"{path}.tile_x"),
        tile_y=_integer(raw["tile_y"], f"{path}.tile_y"),
    )


def _load_interaction(value: object, path: str) -> InteractionSpec:
    raw = _fields(
        value,
        path,
        frozenset({"interaction_id", "kind", "tile_x", "tile_y"}),
        frozenset({"width_tiles", "height_tiles", "params"}),
    )
    return InteractionSpec(
        interaction_id=_text(raw["interaction_id"], f"{path}.interaction_id"),
        kind=_interaction_kind(raw["kind"], f"{path}.kind"),
        tile_x=_integer(raw["tile_x"], f"{path}.tile_x"),
        tile_y=_integer(raw["tile_y"], f"{path}.tile_y"),
        width_tiles=(_integer(raw["width_tiles"], f"{path}.width_tiles") if "width_tiles" in raw else 1),
        height_tiles=(_integer(raw["height_tiles"], f"{path}.height_tiles") if "height_tiles" in raw else 1),
        params=(_parameter_fields(raw["params"], f"{path}.params") if "params" in raw else ()),
    )


def _load_navigation_node(value: object, path: str) -> NavigationNode:
    raw = _fields(
        value,
        path,
        frozenset({"nav_id", "tile_x", "tile_y", "route"}),
    )
    return NavigationNode(
        nav_id=_text(raw["nav_id"], f"{path}.nav_id"),
        tile_x=_integer(raw["tile_x"], f"{path}.tile_x"),
        tile_y=_integer(raw["tile_y"], f"{path}.tile_y"),
        route=_route(raw["route"], f"{path}.route"),
    )


def _load_navigation(value: object, path: str) -> NavigationGraph:
    raw = _fields(value, path, frozenset({"start", "goal", "nodes", "edges"}))
    return NavigationGraph(
        start=_text(raw["start"], f"{path}.start"),
        goal=_text(raw["goal"], f"{path}.goal"),
        nodes=_sequence(raw["nodes"], f"{path}.nodes", _load_navigation_node),
        edges=_sequence(
            raw["edges"],
            f"{path}.edges",
            lambda item, item_path: _pair(item, item_path, _text),
        ),
    )


def _load_stage(value: object, path: str) -> StageSpec:
    raw = _fields(
        value,
        path,
        frozenset(
            {
                "stage_id",
                "world_id",
                "node_id",
                "width_tiles",
                "height_tiles",
                "tile_size",
                "ground_y_tile",
                "player_spawns",
                "enemy_spawns",
                "motes",
                "checkpoints",
                "interactions",
                "goal_tile",
                "hazards",
                "one_way_tiles",
                "solids",
            }
        ),
        frozenset({"order", "name_key", "intro_key", "target_time_ms", "navigation", "boss_id"}),
    )
    stage_id = _text(raw["stage_id"], f"{path}.stage_id")
    motes = _sequence(
        raw["motes"],
        f"{path}.motes",
        lambda item, item_path: _load_mote(item, item_path, stage_id),
    )
    seen_motes: set[str] = set()
    for index, mote in enumerate(motes):
        if mote.mote_id in seen_motes:
            raise ContentError(f"{path}.motes[{index}].mote_id", "duplicate value")
        seen_motes.add(mote.mote_id)
    return StageSpec(
        stage_id=stage_id,
        world_id=_text(raw["world_id"], f"{path}.world_id"),
        node_id=_text(raw["node_id"], f"{path}.node_id"),
        width_tiles=_integer(raw["width_tiles"], f"{path}.width_tiles"),
        height_tiles=_integer(raw["height_tiles"], f"{path}.height_tiles"),
        tile_size=_integer(raw["tile_size"], f"{path}.tile_size"),
        ground_y_tile=_integer(raw["ground_y_tile"], f"{path}.ground_y_tile"),
        player_spawns=_sequence(
            raw["player_spawns"],
            f"{path}.player_spawns",
            lambda item, item_path: _pair(item, item_path, _number),
        ),
        enemy_spawns=_sequence(raw["enemy_spawns"], f"{path}.enemy_spawns", _load_enemy),
        motes=motes,
        checkpoints=_sequence(raw["checkpoints"], f"{path}.checkpoints", _load_checkpoint),
        interactions=_sequence(raw["interactions"], f"{path}.interactions", _load_interaction),
        goal_tile=_pair(raw["goal_tile"], f"{path}.goal_tile", _integer),
        hazards=_sequence(
            raw["hazards"],
            f"{path}.hazards",
            lambda item, item_path: _pair(item, item_path, _integer),
        ),
        one_way_tiles=_sequence(
            raw["one_way_tiles"],
            f"{path}.one_way_tiles",
            lambda item, item_path: _pair(item, item_path, _integer),
        ),
        solids=_sequence(
            raw["solids"],
            f"{path}.solids",
            lambda item, item_path: _pair(item, item_path, _integer),
        ),
        order=_integer(raw["order"], f"{path}.order") if "order" in raw else 0,
        name_key=_text(raw["name_key"], f"{path}.name_key") if "name_key" in raw else "",
        intro_key=_text(raw["intro_key"], f"{path}.intro_key") if "intro_key" in raw else "",
        target_time_ms=(_integer(raw["target_time_ms"], f"{path}.target_time_ms") if "target_time_ms" in raw else 0),
        navigation=(
            _load_navigation(raw["navigation"], f"{path}.navigation")
            if "navigation" in raw
            else NavigationGraph("", "", (), ())
        ),
        boss_id=(None if raw.get("boss_id") is None else _text(raw["boss_id"], f"{path}.boss_id")),
    )


def _unique_index[T](
    values: tuple[T, ...],
    key: Callable[[T], str],
    paths: tuple[str, ...],
    field_name: str,
) -> dict[str, T]:
    result: dict[str, T] = {}
    for value, path in zip(values, paths, strict=True):
        stable_id = key(value)
        if stable_id in result:
            raise ContentError(f"{path}.{field_name}", "duplicate value")
        result[stable_id] = value
    return dict(sorted(result.items()))


def _load_campaign(content_dir: Path) -> CampaignCatalog:
    raw = _fields(
        _load_json(content_dir / "campaign.json", "campaign"),
        "campaign",
        frozenset({"worlds", "stages"}),
        frozenset({"version"}),
    )
    world_values = _array(raw["worlds"], "campaign.worlds")
    worlds_loaded = tuple(_load_world(item, f"campaign.worlds[{index}]") for index, item in enumerate(world_values))
    worlds: dict[str, tuple[WorldNode, ...]] = {}
    node_ids: set[str] = set()
    world_specs: dict[str, WorldSpec] = {}
    for index, world in enumerate(worlds_loaded):
        world_id = world.world_id
        nodes = world.nodes
        if world_id in worlds:
            raise ContentError(f"campaign.worlds[{index}].world_id", "duplicate value")
        worlds[world_id] = nodes
        world_specs[world_id] = world
        for node_index, node in enumerate(nodes):
            if node.node_id in node_ids:
                raise ContentError(
                    f"campaign.worlds[{index}].nodes[{node_index}].node_id",
                    "duplicate value",
                )
            node_ids.add(node.node_id)

    stage_values = _array(raw["stages"], "campaign.stages")
    stages_loaded = tuple(_load_stage(item, f"campaign.stages[{index}]") for index, item in enumerate(stage_values))
    stages = _unique_index(
        stages_loaded,
        lambda stage: stage.stage_id,
        tuple(f"campaign.stages[{index}]" for index in range(len(stages_loaded))),
        "stage_id",
    )
    version = _text(raw["version"], "campaign.version") if "version" in raw else "1.0.0"
    return CampaignCatalog(
        worlds=worlds,
        stages=stages,
        version=version,
        world_specs=world_specs,
    )


def _load_boss_attack(value: object, path: str) -> BossAttackSpec:
    raw = _fields(
        value,
        path,
        frozenset(
            {
                "attack_id",
                "telegraph_ms",
                "active_ms",
                "recovery_ms",
                "marker",
                "cue_id",
                "parameters",
            }
        ),
    )
    return BossAttackSpec(
        attack_id=_text(raw["attack_id"], f"{path}.attack_id"),
        telegraph_ms=_integer(raw["telegraph_ms"], f"{path}.telegraph_ms"),
        active_ms=_integer(raw["active_ms"], f"{path}.active_ms"),
        recovery_ms=_integer(raw["recovery_ms"], f"{path}.recovery_ms"),
        marker=cast(
            AttackMarker,
            _enum(raw["marker"], f"{path}.marker", ATTACK_MARKERS, "attack marker"),
        ),
        cue_id=_text(raw["cue_id"], f"{path}.cue_id"),
        parameters=_parameter_fields(raw["parameters"], f"{path}.parameters"),
    )


def _load_boss_phase(value: object, path: str) -> BossPhaseSpec:
    raw = _fields(
        value,
        path,
        frozenset({"phase_id", "enter_at_hp_ratio", "vulnerability", "arena_rule", "attacks"}),
    )
    return BossPhaseSpec(
        phase_id=_text(raw["phase_id"], f"{path}.phase_id"),
        enter_at_hp_ratio=_number(raw["enter_at_hp_ratio"], f"{path}.enter_at_hp_ratio"),
        vulnerability=cast(
            Vulnerability,
            _enum(
                raw["vulnerability"],
                f"{path}.vulnerability",
                VULNERABILITY_STATES,
                "vulnerability",
            ),
        ),
        arena_rule=_text(raw["arena_rule"], f"{path}.arena_rule"),
        attacks=_sequence(raw["attacks"], f"{path}.attacks", _load_boss_attack),
    )


def _load_boss(value: object, path: str) -> BossSpec:
    raw = _fields(
        value,
        path,
        frozenset({"boss_id", "name_key", "max_hp", "visual_id", "phases"}),
    )
    return BossSpec(
        boss_id=_text(raw["boss_id"], f"{path}.boss_id"),
        name_key=_text(raw["name_key"], f"{path}.name_key"),
        max_hp=_integer(raw["max_hp"], f"{path}.max_hp"),
        visual_id=_text(raw["visual_id"], f"{path}.visual_id"),
        phases=_sequence(raw["phases"], f"{path}.phases", _load_boss_phase),
    )


def _load_bosses(content_dir: Path) -> dict[str, BossSpec]:
    raw = _fields(
        _load_json(content_dir / "bosses.json", "bosses"),
        "bosses",
        frozenset({"bosses"}),
    )
    values = _sequence(raw["bosses"], "bosses.bosses", _load_boss)
    return _unique_index(
        values,
        lambda boss: boss.boss_id,
        tuple(f"bosses.bosses[{index}]" for index in range(len(values))),
        "boss_id",
    )


def _load_reward(value: object, path: str) -> RewardSpec:
    raw = _fields(
        value,
        path,
        frozenset({"threshold", "reward_id", "kind", "name_key"}),
    )
    return RewardSpec(
        threshold=_integer(raw["threshold"], f"{path}.threshold"),
        reward_id=_text(raw["reward_id"], f"{path}.reward_id"),
        kind=cast(
            RewardKind,
            _enum(raw["kind"], f"{path}.kind", REWARD_KINDS, "reward kind"),
        ),
        name_key=_text(raw["name_key"], f"{path}.name_key"),
    )


def _load_rewards(content_dir: Path) -> RewardCatalog:
    raw = _fields(
        _load_json(content_dir / "rewards.json", "rewards"),
        "rewards",
        frozenset({"mote_thresholds"}),
    )
    return RewardCatalog(_sequence(raw["mote_thresholds"], "rewards.mote_thresholds", _load_reward))


def _load_art_asset(value: object, path: str) -> ArtAssetSpec:
    raw = _fields(
        value,
        path,
        frozenset(
            {
                "path",
                "width",
                "height",
                "frames",
                "pixel_sha256",
                "mandatory",
                "provenance",
            }
        ),
    )
    return ArtAssetSpec(
        path=_text(raw["path"], f"{path}.path"),
        width=_integer(raw["width"], f"{path}.width"),
        height=_integer(raw["height"], f"{path}.height"),
        frames=_integer(raw["frames"], f"{path}.frames"),
        pixel_sha256=_text(raw["pixel_sha256"], f"{path}.pixel_sha256"),
        mandatory=_boolean(raw["mandatory"], f"{path}.mandatory"),
        provenance=_text(raw["provenance"], f"{path}.provenance"),
    )


def _load_audio_asset(value: object, path: str) -> AudioAssetSpec:
    raw = _fields(
        value,
        path,
        frozenset({"path", "bus", "mandatory", "sha256"}),
    )
    bus: AudioBus = cast(
        AudioBus,
        _enum(raw["bus"], f"{path}.bus", frozenset({"music", "sfx"}), "audio bus"),
    )
    return AudioAssetSpec(
        path=_text(raw["path"], f"{path}.path"),
        bus=bus,
        mandatory=_boolean(raw["mandatory"], f"{path}.mandatory"),
        sha256=_text(raw["sha256"], f"{path}.sha256"),
    )


def _load_font_asset(value: object, path: str) -> FontAssetSpec:
    raw = _fields(
        value,
        path,
        frozenset({"path", "license", "mandatory"}),
    )
    return FontAssetSpec(
        path=_text(raw["path"], f"{path}.path"),
        license=_text(raw["license"], f"{path}.license"),
        mandatory=_boolean(raw["mandatory"], f"{path}.mandatory"),
    )


def load_asset_manifest(path: Path) -> AssetManifest:
    """Load a strict immutable release asset manifest."""

    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    raw = _fields(
        _load_json(path, "assets"),
        "assets",
        frozenset({"art", "font"}),
        frozenset({"audio", "provenance_files"}),
    )
    return AssetManifest(
        art=_named_objects(raw["art"], "assets.art", _load_art_asset),
        audio=(_named_objects(raw["audio"], "assets.audio", _load_audio_asset) if "audio" in raw else {}),
        font=_load_font_asset(raw["font"], "assets.font"),
        provenance_files=(
            _sequence(raw["provenance_files"], "assets.provenance_files", _text) if "provenance_files" in raw else ()
        ),
    )


def _load_locale(path: Path, language: str) -> dict[str, str]:
    root_path = f"locales.{language}"
    value = _load_json(path, root_path)
    if not isinstance(value, _ObjectPairs):
        raise ContentError(root_path, "must be an object")
    result: dict[str, str] = {}
    duplicates: set[str] = set()
    for key, item in value.pairs:
        if key in result:
            duplicates.add(key)
        elif not isinstance(item, str) or not item:
            raise ContentError(f"{root_path}.{key}", "must be a non-empty string")
        else:
            result[key] = item
    if duplicates:
        duplicate = sorted(duplicates)[0]
        raise ContentError(f"{root_path}.{duplicate}", "duplicate field")
    return dict(sorted(result.items()))


def load_locales(content_dir: Path) -> LocaleCatalog:
    """Load English and Korean string tables without hiding parity defects."""

    if not isinstance(content_dir, Path):
        raise TypeError("content_dir must be a pathlib.Path")
    return LocaleCatalog(
        {
            "en": _load_locale(content_dir / "strings.en.json", "en"),
            "ko": _load_locale(content_dir / "strings.ko.json", "ko"),
        }
    )


def load_catalog_bundle(content_dir: Path) -> CatalogBundle:
    """Load one strict campaign, boss, and reward bundle from ``content_dir``."""

    if not isinstance(content_dir, Path):
        raise TypeError("content_dir must be a pathlib.Path")
    return CatalogBundle(
        campaign=_load_campaign(content_dir),
        bosses=_load_bosses(content_dir),
        rewards=_load_rewards(content_dir),
    )


def load_campaign_catalog(content_dir: Path) -> CampaignCatalog:
    """Load the compatibility campaign projection through the strict parser."""

    if not isinstance(content_dir, Path):
        raise TypeError("content_dir must be a pathlib.Path")
    return _load_campaign(content_dir)


def load_reward_catalog(content_dir: Path) -> RewardCatalog:
    """Load the strict reward projection without requiring Task 3 boss content."""

    if not isinstance(content_dir, Path):
        raise TypeError("content_dir must be a pathlib.Path")
    return _load_rewards(content_dir)


__all__ = [
    "ATTACK_MARKERS",
    "INTERACTION_KINDS",
    "LEGACY_ABILITY_IDS",
    "PUBLIC_ABILITY_IDS",
    "ROUTE_KINDS",
    "VULNERABILITY_STATES",
    "AbilityId",
    "AssetManifest",
    "ArtAssetSpec",
    "AudioAssetSpec",
    "BossAttackSpec",
    "BossPhaseSpec",
    "BossSpec",
    "CampaignCatalog",
    "CatalogBundle",
    "CheckpointSpec",
    "ContentError",
    "EnemySpawn",
    "FontAssetSpec",
    "InteractionKind",
    "InteractionSpec",
    "LocaleCatalog",
    "MoteSpec",
    "NavigationGraph",
    "NavigationNode",
    "RewardCatalog",
    "RewardSpec",
    "StageSpec",
    "ValidationIssue",
    "ValidationReport",
    "WorldNode",
    "WorldSpec",
    "load_campaign_catalog",
    "load_catalog_bundle",
    "load_asset_manifest",
    "load_locales",
    "load_reward_catalog",
]
