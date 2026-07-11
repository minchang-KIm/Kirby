"""Load immutable campaign contracts from release content."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from windsprig.physics import TileCollisionWorld

AbilityId = Literal[
    "bloomblade",
    "cinder",
    "voltsong",
    "galehook",
    "stoneheart",
    "tempest",
]
InteractionKind = Literal["conductor", "switch", "breakable_floor"]

PUBLIC_ABILITY_IDS = frozenset(
    {"bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest"}
)
INTERACTION_KINDS = frozenset({"conductor", "switch", "breakable_floor"})
LEGACY_ABILITY_IDS: dict[str, AbilityId] = {
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


@dataclass(frozen=True, slots=True)
class MoteSpec:
    """Stable collectible identity and tile position."""

    mote_id: str
    tile_x: int
    tile_y: int


@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    """Stable checkpoint identity and tile position."""

    checkpoint_id: str
    tile_x: int
    tile_y: int


@dataclass(frozen=True, slots=True)
class InteractionSpec:
    """Authored gameplay interaction with deterministic tile bounds."""

    interaction_id: str
    kind: InteractionKind
    tile_x: int
    tile_y: int
    width_tiles: int = 1
    height_tiles: int = 1


@dataclass(frozen=True, slots=True)
class EnemySpawn:
    """Enemy placement using only public gameplay ability identities."""

    x: float
    y: float
    kind: str
    ability_id: AbilityId | None
    patrol_left: float
    patrol_right: float


@dataclass(frozen=True, slots=True)
class StageSpec:
    """Immutable stage geometry and stable gameplay content references."""

    stage_id: str
    world_id: str
    node_id: str
    width_tiles: int
    height_tiles: int
    tile_size: int
    ground_y_tile: int
    player_spawns: tuple[tuple[float, float], ...]
    enemy_spawns: tuple[EnemySpawn, ...]
    motes: tuple[MoteSpec, ...]
    checkpoints: tuple[CheckpointSpec, ...]
    interactions: tuple[InteractionSpec, ...]
    goal_tile: tuple[int, int]
    hazards: tuple[tuple[int, int], ...]
    one_way_tiles: tuple[tuple[int, int], ...]
    solids: tuple[tuple[int, int], ...]

    @property
    def pixel_width(self) -> int:
        """Return the authored width in logical pixels."""
        return self.width_tiles * self.tile_size

    @property
    def pixel_height(self) -> int:
        """Return the authored height in logical pixels."""
        return self.height_tiles * self.tile_size

    def build_collision_world(self) -> TileCollisionWorld:
        """Build an isolated collision world from immutable tile geometry."""
        return TileCollisionWorld(
            tile_size=self.tile_size,
            width_tiles=self.width_tiles,
            height_tiles=self.height_tiles,
            solid_tiles=set(self.solids),
            one_way_tiles=set(self.one_way_tiles),
            hazard_tiles=set(self.hazards),
        )


@dataclass(frozen=True, slots=True)
class WorldNode:
    """Campaign graph node linking progression to a stage."""

    node_id: str
    world_id: str
    stage_id: str
    requires: list[str]
    rewards: list[str]
    position: tuple[int, int]
    is_boss: bool


@dataclass(frozen=True, slots=True)
class CampaignCatalog:
    """Loaded world graph and stages indexed by stable IDs."""

    worlds: dict[str, list[WorldNode]]
    stages: dict[str, StageSpec]

    def world_nodes(self, world_id: str) -> list[WorldNode]:
        """Return the authored node order for ``world_id``."""
        return self.worlds.get(world_id, [])


def load_campaign_catalog(content_dir: Path) -> CampaignCatalog:
    """Load the campaign and adapt supported prototype keys at this boundary."""
    payload = _mapping(
        json.loads((content_dir / "campaign.json").read_text(encoding="utf-8")),
        "campaign",
    )
    worlds: dict[str, list[WorldNode]] = {}
    for world_value in _sequence(payload.get("worlds"), "campaign worlds"):
        world = _mapping(world_value, "campaign world")
        world_id = _text(world.get("world_id"), "world_id")
        worlds[world_id] = [
            _load_world_node(world_id, node_value)
            for node_value in _sequence(world.get("nodes"), f"nodes for {world_id}")
        ]

    stages: dict[str, StageSpec] = {}
    for stage_value in _sequence(payload.get("stages"), "campaign stages"):
        raw = _mapping(stage_value, "campaign stage")
        stage = _load_stage(raw)
        stages[stage.stage_id] = stage
    return CampaignCatalog(worlds=worlds, stages=stages)


def _load_world_node(world_id: str, node_value: object) -> WorldNode:
    raw = _mapping(node_value, f"node in {world_id}")
    position = _pair(raw.get("position"), "node position", _integer)
    return WorldNode(
        node_id=_text(raw.get("node_id"), "node_id"),
        world_id=world_id,
        stage_id=_text(raw.get("stage_id"), "stage_id"),
        requires=[_text(value, "required node ID") for value in _optional_sequence(raw.get("requires"))],
        rewards=[_text(value, "reward ID") for value in _optional_sequence(raw.get("rewards"))],
        position=position,
        is_boss=_boolean(raw.get("is_boss", False), "is_boss"),
    )


def _load_stage(raw: dict[str, object]) -> StageSpec:
    stage_id = _text(raw.get("stage_id"), "stage_id")
    return StageSpec(
        stage_id=stage_id,
        world_id=_text(raw.get("world_id"), f"world_id for {stage_id}"),
        node_id=_text(raw.get("node_id"), f"node_id for {stage_id}"),
        width_tiles=_integer(raw.get("width_tiles"), f"width_tiles for {stage_id}"),
        height_tiles=_integer(raw.get("height_tiles"), f"height_tiles for {stage_id}"),
        tile_size=_integer(raw.get("tile_size"), f"tile_size for {stage_id}"),
        ground_y_tile=_integer(raw.get("ground_y_tile"), f"ground_y_tile for {stage_id}"),
        player_spawns=tuple(
            _pair(value, f"player spawn for {stage_id}", _number)
            for value in _sequence(raw.get("player_spawns"), f"player_spawns for {stage_id}")
        ),
        enemy_spawns=_load_enemy_spawns(raw, stage_id),
        motes=_load_motes(raw),
        checkpoints=_load_checkpoints(raw),
        interactions=_load_interactions(raw, stage_id),
        goal_tile=_pair(raw.get("goal_tile"), f"goal_tile for {stage_id}", _integer),
        hazards=_load_tile_pairs(raw.get("hazards"), f"hazards for {stage_id}"),
        one_way_tiles=_load_tile_pairs(raw.get("one_way_tiles"), f"one_way_tiles for {stage_id}"),
        solids=_load_tile_pairs(raw.get("solids"), f"solids for {stage_id}"),
    )


def _load_enemy_spawns(raw: dict[str, object], stage_id: str) -> tuple[EnemySpawn, ...]:
    spawns: list[EnemySpawn] = []
    for enemy_value in _sequence(raw.get("enemy_spawns"), f"enemy_spawns for {stage_id}"):
        enemy = _mapping(enemy_value, f"enemy spawn for {stage_id}")
        ability_value = enemy.get("ability_id")
        uses_legacy_id = "ability_id" not in enemy
        if uses_legacy_id:
            ability_value = enemy.get("copy_ability")
        spawns.append(
            EnemySpawn(
                x=_number(enemy.get("x"), f"enemy x for {stage_id}"),
                y=_number(enemy.get("y"), f"enemy y for {stage_id}"),
                kind=_text(enemy.get("kind"), f"enemy kind for {stage_id}"),
                ability_id=_ability_id(ability_value, legacy=uses_legacy_id),
                patrol_left=_number(enemy.get("patrol_left"), f"patrol_left for {stage_id}"),
                patrol_right=_number(enemy.get("patrol_right"), f"patrol_right for {stage_id}"),
            )
        )
    return tuple(spawns)


def _load_motes(raw: dict[str, object]) -> tuple[MoteSpec, ...]:
    stage_id = _text(raw.get("stage_id"), "stage_id")
    if "motes" in raw:
        motes: list[MoteSpec] = []
        seen_ids: set[str] = set()
        for value in _sequence(raw.get("motes"), f"motes for {stage_id}"):
            item = _mapping(value, f"mote for {stage_id}")
            mote_id = _canonical_mote_id(item.get("mote_id"), stage_id)
            if mote_id in seen_ids:
                raise ValueError(f"duplicate mote_id for {stage_id}: {mote_id}")
            seen_ids.add(mote_id)
            motes.append(
                MoteSpec(
                    mote_id=mote_id,
                    tile_x=_integer(item.get("tile_x"), f"mote tile_x for {stage_id}"),
                    tile_y=_integer(item.get("tile_y"), f"mote tile_y for {stage_id}"),
                )
            )
        return tuple(motes)

    # Prototype saves already persist this identity form; content migration must not fork it.
    return tuple(
        MoteSpec(
            f"{stage_id}:mote:{index}",
            *_pair(tile, f"prototype mote for {stage_id}", _integer),
        )
        for index, tile in enumerate(_optional_sequence(raw.get("energy_spheres")), start=1)
    )


def _canonical_mote_id(value: object, stage_id: str) -> str:
    mote_id = _text(value, f"mote_id for {stage_id}")
    prefix = f"{stage_id}:mote:"
    index_text = mote_id.removeprefix(prefix) if mote_id.startswith(prefix) else ""
    # Save and replay identity is permanent; accepting aliases would fork one collectible's history.
    if not index_text.isascii() or not index_text.isdigit():
        raise ValueError(f"canonical mote_id must match {prefix}<positive integer>: {mote_id}")
    if index_text.startswith("0"):
        raise ValueError(f"canonical mote_id must match {prefix}<positive integer>: {mote_id}")
    return mote_id


def _load_checkpoints(raw: dict[str, object]) -> tuple[CheckpointSpec, ...]:
    stage_id = _text(raw.get("stage_id"), "stage_id")
    if "checkpoints" in raw:
        return tuple(
            CheckpointSpec(
                checkpoint_id=_text(item.get("checkpoint_id"), f"checkpoint_id for {stage_id}"),
                tile_x=_integer(item.get("tile_x"), f"checkpoint tile_x for {stage_id}"),
                tile_y=_integer(item.get("tile_y"), f"checkpoint tile_y for {stage_id}"),
            )
            for item in (
                _mapping(value, f"checkpoint for {stage_id}")
                for value in _sequence(raw.get("checkpoints"), f"checkpoints for {stage_id}")
            )
        )

    player_spawns = _sequence(raw.get("player_spawns"), f"player_spawns for {stage_id}")
    if not player_spawns:
        raise ValueError(f"player_spawns for {stage_id} must not be empty")
    spawn_x, spawn_y = _pair(player_spawns[0], f"first player spawn for {stage_id}", _number)
    tile_size = _integer(raw.get("tile_size"), f"tile_size for {stage_id}")
    return (
        CheckpointSpec(
            f"{stage_id}.start",
            int(spawn_x // tile_size),
            int(spawn_y // tile_size),
        ),
    )


def _load_interactions(raw: dict[str, object], stage_id: str) -> tuple[InteractionSpec, ...]:
    interactions: list[InteractionSpec] = []
    for value in _optional_sequence(raw.get("interactions")):
        item = _mapping(value, f"interaction for {stage_id}")
        interactions.append(
            InteractionSpec(
                interaction_id=_text(item.get("interaction_id"), f"interaction_id for {stage_id}"),
                kind=_interaction_kind(item.get("kind")),
                tile_x=_integer(item.get("tile_x"), f"interaction tile_x for {stage_id}"),
                tile_y=_integer(item.get("tile_y"), f"interaction tile_y for {stage_id}"),
                width_tiles=_integer(item.get("width_tiles", 1), f"interaction width for {stage_id}"),
                height_tiles=_integer(item.get("height_tiles", 1), f"interaction height for {stage_id}"),
            )
        )
    return tuple(interactions)


def _load_tile_pairs(value: object, context: str) -> tuple[tuple[int, int], ...]:
    return tuple(_pair(item, context, _integer) for item in _sequence(value, context))


def _ability_id(value: object, *, legacy: bool) -> AbilityId | None:
    if value is None or value == "none":
        return None
    raw_id = _text(value, "enemy ability_id")
    public_id = LEGACY_ABILITY_IDS.get(raw_id) if legacy else raw_id
    if public_id not in PUBLIC_ABILITY_IDS:
        raise ValueError(f"unknown enemy ability_id: {raw_id}")
    return cast(AbilityId, public_id)


def _interaction_kind(value: object) -> InteractionKind:
    kind = _text(value, "interaction kind")
    if kind not in INTERACTION_KINDS:
        raise ValueError(f"unknown interaction kind: {kind}")
    return cast(InteractionKind, kind)


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list")
    return cast(list[object], value)


def _optional_sequence(value: object) -> list[object]:
    if value is None:
        return []
    return _sequence(value, "optional content sequence")


def _pair[T](value: object, context: str, convert: Callable[[object, str], T]) -> tuple[T, T]:
    values = _sequence(value, context)
    if len(values) != 2:
        raise ValueError(f"{context} must contain exactly two values")
    return convert(values[0], context), convert(values[1], context)


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def _number(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be a number")
    return float(value)


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value
