"""Canonical immutable content contracts shared by gameplay and presentation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from hashlib import sha256
from types import MappingProxyType
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
RouteKind = Literal["main", "optional", "mastery"]
InteractionKind = Literal[
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
]
ParameterValue = int | float | str | bool
AttackMarker = Literal["ground", "silhouette", "lane", "orbit", "beam", "arena"]
Vulnerability = Literal["vulnerable", "armored", "hidden", "invulnerable"]
RewardKind = Literal["challenge", "gallery", "palette"]
AudioBus = Literal["music", "sfx"]


def frozen_map[T](values: Mapping[str, T]) -> Mapping[str, T]:
    """Return a sorted immutable copy of a stable-ID mapping."""

    return MappingProxyType(dict(sorted(values.items())))


def _freeze_parameters(
    values: tuple[tuple[str, ParameterValue], ...] | Mapping[str, ParameterValue],
) -> tuple[tuple[str, ParameterValue], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    return tuple(sorted(items))


@dataclass(frozen=True, slots=True)
class MoteSpec:
    """Stable collectible identity, tile position, and authored route."""

    mote_id: str
    tile_x: int
    tile_y: int
    route: RouteKind = "main"


@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    """Stable checkpoint identity and tile position."""

    checkpoint_id: str
    tile_x: int
    tile_y: int


@dataclass(frozen=True, slots=True)
class InteractionSpec:
    """Authored gameplay interaction with immutable deterministic parameters."""

    interaction_id: str
    kind: InteractionKind
    tile_x: int
    tile_y: int
    width_tiles: int = 1
    height_tiles: int = 1
    params: tuple[tuple[str, ParameterValue], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", _freeze_parameters(self.params))


@dataclass(frozen=True, slots=True)
class EnemySpawn:
    """Enemy placement in logical pixels with stable authored metadata."""

    x: float
    y: float
    kind: str
    ability_id: AbilityId | None
    patrol_left: float
    patrol_right: float
    spawn_id: str = ""
    elite: bool = False


@dataclass(frozen=True, slots=True)
class NavigationNode:
    """One authored reachability point in tile coordinates."""

    nav_id: str
    tile_x: int
    tile_y: int
    route: RouteKind


@dataclass(frozen=True, slots=True)
class NavigationGraph:
    """Immutable directed navigation evidence for one stage."""

    start: str
    goal: str
    nodes: tuple[NavigationNode, ...]
    edges: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(tuple(edge) for edge in self.edges))


def _empty_navigation() -> NavigationGraph:
    return NavigationGraph(start="", goal="", nodes=(), edges=())


@dataclass(frozen=True, slots=True)
class StageSpec:
    """Immutable stage geometry with gameplay fields retained as a stable prefix."""

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
    order: int = 0
    name_key: str = ""
    intro_key: str = ""
    target_time_ms: int = 0
    navigation: NavigationGraph = field(default_factory=_empty_navigation)
    boss_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_spawns",
            tuple((float(x), float(y)) for x, y in self.player_spawns),
        )
        object.__setattr__(self, "enemy_spawns", tuple(self.enemy_spawns))
        object.__setattr__(self, "motes", tuple(self.motes))
        object.__setattr__(self, "checkpoints", tuple(self.checkpoints))
        object.__setattr__(self, "interactions", tuple(self.interactions))
        object.__setattr__(self, "goal_tile", tuple(self.goal_tile))
        object.__setattr__(self, "hazards", tuple(tuple(tile) for tile in self.hazards))
        object.__setattr__(
            self,
            "one_way_tiles",
            tuple(tuple(tile) for tile in self.one_way_tiles),
        )
        object.__setattr__(self, "solids", tuple(tuple(tile) for tile in self.solids))

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

    def layout_signature(self) -> str:
        """Hash gameplay-significant geometry without identity or presentation keys."""

        payload = {
            "size": [self.width_tiles, self.height_tiles],
            "solids": sorted(self.solids),
            "one_way": sorted(self.one_way_tiles),
            "hazards": sorted(self.hazards),
            "encounters": [
                [enemy.kind, enemy.ability_id, enemy.x, enemy.y, enemy.elite] for enemy in self.enemy_spawns
            ],
            "mote_routes": [[mote.tile_x, mote.tile_y, mote.route] for mote in self.motes],
            "interactions": [
                [
                    interaction.kind,
                    interaction.tile_x,
                    interaction.tile_y,
                    interaction.width_tiles,
                    interaction.height_tiles,
                    list(interaction.params),
                ]
                for interaction in self.interactions
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256(raw).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class WorldNode:
    """Campaign graph node linking progression to a stage."""

    node_id: str
    world_id: str
    stage_id: str
    requires: tuple[str, ...]
    rewards: tuple[str, ...]
    position: tuple[int, int]
    is_boss: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "requires", tuple(self.requires))
        object.__setattr__(self, "rewards", tuple(self.rewards))
        object.__setattr__(self, "position", tuple(self.position))


@dataclass(frozen=True, slots=True)
class WorldSpec:
    """Presentation metadata for one ordered campaign world."""

    world_id: str
    order: int
    name_key: str
    identity_key: str
    mechanic_keys: tuple[str, ...]
    palette_id: str
    nodes: tuple[WorldNode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "mechanic_keys", tuple(self.mechanic_keys))
        object.__setattr__(self, "nodes", tuple(self.nodes))


@dataclass(frozen=True, slots=True)
class BossAttackSpec:
    """One deterministic boss attack timing and telegraph contract."""

    attack_id: str
    telegraph_ms: int
    active_ms: int
    recovery_ms: int
    marker: AttackMarker
    cue_id: str
    parameters: tuple[tuple[str, ParameterValue], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _freeze_parameters(self.parameters))


@dataclass(frozen=True, slots=True)
class BossPhaseSpec:
    """One ordered boss phase and its immutable attack rotation."""

    phase_id: str
    enter_at_hp_ratio: float
    vulnerability: Vulnerability
    arena_rule: str
    attacks: tuple[BossAttackSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attacks", tuple(self.attacks))


@dataclass(frozen=True, slots=True)
class BossSpec:
    """Stable boss identity, presentation, health, and phase definitions."""

    boss_id: str
    name_key: str
    max_hp: int
    visual_id: str
    phases: tuple[BossPhaseSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "phases", tuple(self.phases))


@dataclass(frozen=True, slots=True)
class RewardSpec:
    """One optional campaign reward unlocked at a mote threshold."""

    threshold: int
    reward_id: str
    kind: RewardKind
    name_key: str


@dataclass(frozen=True, slots=True)
class CampaignCatalog:
    """Loaded world graph and stages indexed by stable IDs."""

    worlds: Mapping[str, tuple[WorldNode, ...]]
    stages: Mapping[str, StageSpec]
    version: str = "1.0.0"
    nodes: Mapping[str, WorldNode] = field(default_factory=dict)
    world_specs: Mapping[str, WorldSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        worlds = {world_id: tuple(nodes) for world_id, nodes in self.worlds.items()}
        stages = dict(self.stages)
        nodes = {node.node_id: node for world_nodes in worlds.values() for node in world_nodes}
        supplied_specs = dict(self.world_specs)
        world_specs: dict[str, WorldSpec] = {}
        for world_id, world_nodes in worlds.items():
            supplied = supplied_specs.get(world_id)
            if supplied is None:
                world_specs[world_id] = WorldSpec(
                    world_id=world_id,
                    order=0,
                    name_key="",
                    identity_key="",
                    mechanic_keys=(),
                    palette_id="",
                    nodes=world_nodes,
                )
            else:
                world_specs[world_id] = replace(supplied, nodes=world_nodes)
        object.__setattr__(self, "worlds", frozen_map(worlds))
        object.__setattr__(self, "stages", frozen_map(stages))
        object.__setattr__(self, "nodes", frozen_map(nodes))
        object.__setattr__(self, "world_specs", frozen_map(world_specs))

    def world_nodes(self, world_id: str) -> tuple[WorldNode, ...]:
        """Return the immutable authored node order for ``world_id``."""

        return self.worlds.get(world_id, ())


@dataclass(frozen=True, slots=True)
class RewardCatalog:
    """Immutable ordered mote-threshold rewards."""

    mote_thresholds: tuple[RewardSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "mote_thresholds", tuple(self.mote_thresholds))


@dataclass(frozen=True, slots=True)
class CatalogBundle:
    """One canonical campaign, boss, and reward content snapshot."""

    campaign: CampaignCatalog
    bosses: Mapping[str, BossSpec]
    rewards: RewardCatalog

    def __post_init__(self) -> None:
        # Boss iteration follows the authored world order, which is gameplay-significant
        # for one-to-one campaign/boss reconciliation. The copied proxy still prevents
        # callers from mutating the catalog after validation.
        object.__setattr__(self, "bosses", MappingProxyType(dict(self.bosses)))


@dataclass(frozen=True, slots=True)
class ArtAssetSpec:
    """One immutable raster asset and its decoded-pixel identity."""

    path: str
    width: int
    height: int
    frames: int
    pixel_sha256: str
    mandatory: bool
    provenance: str


@dataclass(frozen=True, slots=True)
class AudioAssetSpec:
    """One immutable audio cue and its release-file identity."""

    path: str
    bus: AudioBus
    mandatory: bool
    sha256: str


@dataclass(frozen=True, slots=True)
class FontAssetSpec:
    """The mandatory Korean-capable font and retained license path."""

    path: str
    license: str
    mandatory: bool
    sha256: str


type AssetRecord = ArtAssetSpec | AudioAssetSpec | FontAssetSpec


@dataclass(frozen=True, slots=True)
class AssetManifest:
    """Immutable asset records partitioned by runtime kind."""

    art: Mapping[str, ArtAssetSpec]
    audio: Mapping[str, AudioAssetSpec]
    font: FontAssetSpec
    provenance_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "art", frozen_map(self.art))
        object.__setattr__(self, "audio", frozen_map(self.audio))
        object.__setattr__(self, "provenance_files", tuple(self.provenance_files))


@dataclass(frozen=True, slots=True)
class LocaleCatalog:
    """Immutable locale string tables keyed by language and message ID."""

    strings: Mapping[str, Mapping[str, str]]

    def __post_init__(self) -> None:
        tables = {language: frozen_map(table) for language, table in self.strings.items()}
        object.__setattr__(self, "strings", frozen_map(tables))


@dataclass(frozen=True, slots=True, order=True)
class ValidationIssue:
    """One stable machine-readable content validation finding."""

    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Ordered validation findings plus immutable catalog counts."""

    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "counts", frozen_map(self.counts))

    @property
    def ok(self) -> bool:
        """Return whether the report contains no validation errors."""

        return not self.errors


def parameter_mapping(
    values: tuple[tuple[str, ParameterValue], ...],
) -> Mapping[str, ParameterValue]:
    """Expose immutable parameters as a mapping without storing duplicate state."""

    return MappingProxyType(dict(values))


def coerce_parameter_tuple(value: object) -> tuple[tuple[str, ParameterValue], ...]:
    """Narrow an already validated parameter mapping for model construction."""

    return _freeze_parameters(cast(Mapping[str, ParameterValue], value))
