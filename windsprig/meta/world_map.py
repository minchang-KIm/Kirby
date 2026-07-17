"""Build immutable localized world-map views in authored campaign order."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from windsprig.content.models import CampaignCatalog, CatalogBundle, WorldNode, WorldSpec
from windsprig.localization import Localizer

from .completion import CompletionTracker, completion_breakdown, ordered_worlds
from .save_models import SaveProfile
from .unlock_rules import UnlockRules


class NodeState(StrEnum):
    """Presentation state shared by node shape, icon, text, and color."""

    LOCKED = "locked"
    AVAILABLE = "available"
    CLEARED = "cleared"


@dataclass(frozen=True, slots=True)
class MapNodeVM:
    """Immutable presentation facts for one campaign node."""

    node_id: str
    stage_id: str
    label: str
    x: int
    y: int
    state: NodeState
    shape_token: str
    icon_token: str
    mote_states: tuple[bool, bool, bool]
    best_time_label: str
    selected: bool
    is_boss: bool


@dataclass(frozen=True, slots=True)
class ConnectorVM:
    """One canonical map edge and whether both endpoints are accessible."""

    from_node_id: str
    to_node_id: str
    unlocked: bool


@dataclass(frozen=True, slots=True)
class MapWorldVM:
    """Localized world identity and its ordered map graph."""

    world_id: str
    label: str
    identity: str
    palette_id: str
    locked: bool
    nodes: tuple[MapNodeVM, ...]
    connectors: tuple[ConnectorVM, ...]


@dataclass(frozen=True, slots=True)
class WorldMapViewModel:
    """Complete immutable state consumed by the world-map renderer."""

    worlds: tuple[MapWorldVM, ...]
    total_motes_label: str
    completion_label: str
    selected_node_id: str
    save_status_key: str


def format_stage_time(milliseconds: int) -> str:
    """Format a non-negative stage duration as ``MM:SS.mmm``."""

    if type(milliseconds) is not int or milliseconds < 0:
        raise ValueError("stage time must be a non-negative integer")
    minutes, within_minute = divmod(milliseconds, 60_000)
    seconds, remainder = divmod(within_minute, 1_000)
    return f"{minutes:02d}:{seconds:02d}.{remainder:03d}"


def _campaign_worlds(catalog: CampaignCatalog) -> tuple[WorldSpec, ...]:
    worlds = tuple(catalog.world_specs.values())
    orders = tuple(world.order for world in worlds)
    if len(orders) != len(set(orders)):
        raise ValueError("campaign world orders must be unique")
    return tuple(sorted(worlds, key=lambda world: world.order))


@dataclass(slots=True)
class WorldMapService:
    """Compatibility adapter for the foundation screen's mutable tracker."""

    catalog: CampaignCatalog
    rules: UnlockRules

    def unlocked_nodes(
        self,
        tracker: CompletionTracker,
        unlocked_worlds: set[str],
    ) -> dict[str, list[WorldNode]]:
        """Return visible nodes without replacing authored order with ID order."""

        visible: dict[str, list[WorldNode]] = {}
        for world in _campaign_worlds(self.catalog):
            if world.world_id not in unlocked_worlds:
                continue
            visible[world.world_id] = [
                node
                for node in world.nodes
                if self.rules.is_node_unlocked(
                    node.node_id,
                    tracker,
                    unlocked_worlds,
                )
            ]
        return visible

    def first_playable_node(
        self,
        tracker: CompletionTracker,
        unlocked_worlds: set[str],
    ) -> WorldNode | None:
        """Return the first uncleared node in canonical campaign order."""

        visible = self.unlocked_nodes(tracker, unlocked_worlds)
        for world in _campaign_worlds(self.catalog):
            for node in visible.get(world.world_id, ()):
                if node.node_id not in tracker.cleared_nodes:
                    return node
        return None


def _node_state(
    profile: SaveProfile,
    world_locked: bool,
    node: WorldNode,
    stage_cleared: bool,
) -> NodeState:
    if world_locked:
        return NodeState.LOCKED
    if stage_cleared:
        return NodeState.CLEARED
    if node.node_id in profile.unlocked_nodes:
        return NodeState.AVAILABLE
    return NodeState.LOCKED


def _map_node(
    profile: SaveProfile,
    catalog: CatalogBundle,
    world_locked: bool,
    node: WorldNode,
    selected_node_id: str,
    tr: Localizer,
) -> MapNodeVM:
    stage = catalog.campaign.stages.get(node.stage_id)
    if stage is None:
        raise ValueError(f"unknown stage_id for node {node.node_id}: {node.stage_id}")
    if len(stage.motes) != 3:
        raise ValueError(f"stage {stage.stage_id} must contain exactly three motes")
    state = _node_state(
        profile,
        world_locked,
        node,
        profile.clear_counts.get(stage.stage_id, 0) > 0,
    )
    mote_values = tuple(mote.mote_id in profile.collected_mote_ids for mote in stage.motes)
    mote_states = cast(tuple[bool, bool, bool], mote_values)
    best_time = profile.best_times_ms.get(stage.stage_id)
    best_time_label = tr.text("map.best", time=format_stage_time(best_time)) if best_time is not None else ""
    return MapNodeVM(
        node_id=node.node_id,
        stage_id=node.stage_id,
        label=tr.text(stage.name_key),
        x=node.position[0],
        y=node.position[1],
        state=state,
        shape_token="node.hex-boss" if node.is_boss else "node.round",
        icon_token="boss.crown" if node.is_boss else "stage.leaf",
        mote_states=mote_states,
        best_time_label=best_time_label,
        selected=node.node_id == selected_node_id,
        is_boss=node.is_boss,
    )


def _map_world(
    profile: SaveProfile,
    catalog: CatalogBundle,
    world: WorldSpec,
    selected_node_id: str,
    tr: Localizer,
) -> MapWorldVM:
    world_locked = world.world_id not in profile.unlocked_worlds
    nodes = tuple(
        _map_node(
            profile,
            catalog,
            world_locked,
            node,
            selected_node_id,
            tr,
        )
        for node in world.nodes
    )
    states = {node.node_id: node.state for node in nodes}
    connectors = tuple(
        ConnectorVM(
            from_node_id=source.node_id,
            to_node_id=target.node_id,
            unlocked=(
                states[source.node_id] is not NodeState.LOCKED and states[target.node_id] is not NodeState.LOCKED
            ),
        )
        for source, target in zip(world.nodes, world.nodes[1:], strict=False)
    )
    return MapWorldVM(
        world_id=world.world_id,
        label=tr.text(world.name_key),
        identity=tr.text(world.identity_key),
        palette_id=world.palette_id,
        locked=world_locked,
        nodes=nodes,
        connectors=connectors,
    )


def build_world_map_view(
    profile: SaveProfile,
    catalog: CatalogBundle,
    selected_node_id: str,
    tr: Localizer,
) -> WorldMapViewModel:
    """Build a localized map while filtering future or adversarial save facts."""

    if not isinstance(profile, SaveProfile):
        raise ValueError("profile must be SaveProfile")
    if not isinstance(catalog, CatalogBundle):
        raise ValueError("catalog must be CatalogBundle")
    if selected_node_id not in catalog.campaign.nodes:
        raise ValueError(f"unknown selected_node_id: {selected_node_id}")
    breakdown = completion_breakdown(profile, catalog)
    return WorldMapViewModel(
        worlds=tuple(_map_world(profile, catalog, world, selected_node_id, tr) for world in ordered_worlds(catalog)),
        total_motes_label=tr.text(
            "profile.motes",
            found=breakdown.collected_motes,
        ),
        completion_label=tr.text(
            "profile.completion",
            percent=str(breakdown.percent),
        ),
        selected_node_id=selected_node_id,
        save_status_key="save.saved",
    )


__all__ = [
    "ConnectorVM",
    "MapNodeVM",
    "MapWorldVM",
    "NodeState",
    "WorldMapService",
    "WorldMapViewModel",
    "build_world_map_view",
    "format_stage_time",
]
