"""Apply immutable campaign results and derive catalog-bounded completion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal

from windsprig.content.models import CatalogBundle, WorldNode, WorldSpec
from windsprig.gameplay.snapshot import StageResult

from .save_models import (
    SaveProfile,
    _id_frozenset,
    _identifier,
    _immutable_int_map,
    _strict_int,
)

_PERCENT_QUANTUM = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class CompletionDelta:
    """Facts newly contributed by one valid stage result."""

    first_clear: bool
    new_mote_ids: tuple[str, ...]
    newly_discovered_abilities: tuple[str, ...]
    newly_unlocked_node_ids: tuple[str, ...]
    newly_unlocked_world_ids: tuple[str, ...]
    new_reward_ids: tuple[str, ...]
    previous_best_ms: int | None
    is_new_best: bool


@dataclass(frozen=True, slots=True)
class CompletionBreakdown:
    """Catalog-known completion counts and their weighted percentage."""

    cleared_stages: int
    total_stages: int
    collected_motes: int
    total_motes: int
    cleared_bosses: int
    total_bosses: int
    challenge_rewards: int
    total_challenges: int
    percent: Decimal


def ordered_worlds(catalog: CatalogBundle) -> tuple[WorldSpec, ...]:
    """Return worlds by authored order, rejecting an ambiguous campaign order."""

    worlds = tuple(catalog.campaign.world_specs.values())
    orders = tuple(world.order for world in worlds)
    if len(orders) != len(set(orders)):
        raise ValueError("campaign world orders must be unique")
    return tuple(sorted(worlds, key=lambda world: world.order))


def ordered_nodes(catalog: CatalogBundle) -> tuple[WorldNode, ...]:
    """Return the campaign's canonical cross-world node sequence."""

    return tuple(node for world in ordered_worlds(catalog) for node in world.nodes)


def _known_mote_ids(catalog: CatalogBundle) -> frozenset[str]:
    return frozenset(mote.mote_id for stage in catalog.campaign.stages.values() for mote in stage.motes)


def _known_ability_ids(catalog: CatalogBundle) -> frozenset[str]:
    return frozenset(
        enemy.ability_id
        for stage in catalog.campaign.stages.values()
        for enemy in stage.enemy_spawns
        if enemy.ability_id is not None
    )


def _strict_id_tuple(name: str, values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple of IDs")
    result = tuple(_identifier(f"{name} ID", value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicate IDs")
    return result


def _validate_team_result(result: StageResult) -> None:
    slots = result.active_slots
    if not isinstance(slots, tuple):
        raise ValueError("active_slots must be a tuple")
    if not slots:
        raise ValueError("active_slots must contain at least one slot")
    if any(type(slot) is not int or not 1 <= slot <= 4 for slot in slots):
        raise ValueError("active_slots must contain integer slots from 1 to 4")
    if len(slots) != len(set(slots)):
        raise ValueError("active_slots must not contain duplicate slots")
    if slots != tuple(sorted(slots)):
        raise ValueError("active_slots must use canonical ascending order")

    deaths = result.deaths_by_slot
    if not isinstance(deaths, tuple):
        raise ValueError("deaths_by_slot must be a tuple")
    death_slots: list[int] = []
    for item in deaths:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("deaths_by_slot entries must be slot/count pairs")
        slot, count = item
        if type(slot) is not int or not 1 <= slot <= 4:
            raise ValueError("death slots must be integers from 1 to 4")
        if type(count) is not int or count < 0:
            raise ValueError("death counts must be non-negative integers")
        death_slots.append(slot)
    if len(death_slots) != len(set(death_slots)):
        raise ValueError("deaths_by_slot must not contain duplicate slots")
    if tuple(death_slots) != slots:
        raise ValueError("deaths_by_slot must exactly match active_slots")


def validate_stage_result(
    profile: SaveProfile,
    result: StageResult,
    catalog: CatalogBundle,
    *,
    require_unlocked: bool = True,
) -> None:
    """Reject forged or malformed stage facts before they reach progression."""

    if not isinstance(profile, SaveProfile):
        raise ValueError("profile must be SaveProfile")
    if not isinstance(result, StageResult):
        raise ValueError("result must be StageResult")
    if not isinstance(catalog, CatalogBundle):
        raise ValueError("catalog must be CatalogBundle")

    stage_id = _identifier("stage_id", result.stage_id)
    world_id = _identifier("world_id", result.world_id)
    node_id = _identifier("node_id", result.node_id)
    stage = catalog.campaign.stages.get(stage_id)
    if stage is None:
        raise ValueError(f"unknown stage_id: {stage_id}")
    if world_id not in catalog.campaign.world_specs:
        raise ValueError(f"unknown world_id: {world_id}")
    if node_id not in catalog.campaign.nodes:
        raise ValueError(f"unknown node_id: {node_id}")
    if stage.world_id != world_id or stage.node_id != node_id:
        raise ValueError("stage result identity does not match catalog")
    if require_unlocked and (node_id not in profile.unlocked_nodes or world_id not in profile.unlocked_worlds):
        raise ValueError(f"stage is locked: {stage_id}")

    if type(result.clear_time_ms) is not int or result.clear_time_ms <= 0:
        raise ValueError("clear_time_ms must be a positive integer")

    mote_ids = _strict_id_tuple("collected_mote_ids", result.collected_mote_ids)
    allowed_motes = {mote.mote_id for mote in stage.motes}
    for mote_id in mote_ids:
        if mote_id not in allowed_motes:
            raise ValueError(f"{mote_id} is not in {stage_id}")

    ability_ids = _strict_id_tuple(
        "discovered_ability_ids",
        result.discovered_ability_ids,
    )
    known_abilities = _known_ability_ids(catalog)
    for ability_id in ability_ids:
        if ability_id not in known_abilities:
            raise ValueError(f"unknown ability_id: {ability_id}")
    _validate_team_result(result)


def _advanced_stage_maps(
    best_times_ms: Mapping[str, int],
    clear_counts: Mapping[str, int],
    stage_id: str,
    elapsed_ms: int,
) -> tuple[dict[str, int], dict[str, int], int | None]:
    previous_best = best_times_ms.get(stage_id)
    best_times = dict(best_times_ms)
    best_times[stage_id] = elapsed_ms if previous_best is None else min(previous_best, elapsed_ms)
    counts = dict(clear_counts)
    counts[stage_id] = counts.get(stage_id, 0) + 1
    return best_times, counts, previous_best


def _ratio(completed: int, total: int) -> Decimal:
    if total == 0:
        return Decimal(0)
    return Decimal(completed) / Decimal(total)


def completion_breakdown(
    profile: SaveProfile,
    catalog: CatalogBundle,
) -> CompletionBreakdown:
    """Calculate the documented weighted completion from catalog-known facts."""

    if not isinstance(profile, SaveProfile):
        raise ValueError("profile must be SaveProfile")
    if not isinstance(catalog, CatalogBundle):
        raise ValueError("catalog must be CatalogBundle")

    stage_ids = frozenset(catalog.campaign.stages)
    cleared_stage_ids = frozenset(
        stage_id for stage_id, count in profile.clear_counts.items() if stage_id in stage_ids and count > 0
    )
    mote_ids = _known_mote_ids(catalog)
    collected_mote_ids = profile.collected_mote_ids & mote_ids
    boss_stage_ids = frozenset(
        stage.stage_id for stage in catalog.campaign.stages.values() if stage.boss_id is not None
    )
    challenge_ids = frozenset(
        reward.reward_id for reward in catalog.rewards.mote_thresholds if reward.kind == "challenge"
    )
    earned_challenges = profile.challenge_rewards & challenge_ids

    score = Decimal(100) * (
        Decimal("0.50") * _ratio(len(cleared_stage_ids), len(stage_ids))
        + Decimal("0.30") * _ratio(len(collected_mote_ids), len(mote_ids))
        + Decimal("0.10") * _ratio(len(cleared_stage_ids & boss_stage_ids), len(boss_stage_ids))
        + Decimal("0.10") * _ratio(len(earned_challenges), len(challenge_ids))
    )
    bounded = max(Decimal("0.0"), min(Decimal("100.0"), score))
    percent = bounded.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
    return CompletionBreakdown(
        cleared_stages=len(cleared_stage_ids),
        total_stages=len(stage_ids),
        collected_motes=len(collected_mote_ids),
        total_motes=len(mote_ids),
        cleared_bosses=len(cleared_stage_ids & boss_stage_ids),
        total_bosses=len(boss_stage_ids),
        challenge_rewards=len(earned_challenges),
        total_challenges=len(challenge_ids),
        percent=percent,
    )


def completion_percent(profile: SaveProfile, catalog: CatalogBundle) -> Decimal:
    """Return completion rounded half-up to one decimal in ``0.0..100.0``."""

    return completion_breakdown(profile, catalog).percent


def apply_stage_result(
    profile: SaveProfile,
    result: StageResult,
    catalog: CatalogBundle,
) -> tuple[SaveProfile, CompletionDelta]:
    """Apply one catalog-valid result without duplicating permanent facts."""

    validate_stage_result(profile, result, catalog)
    stage = catalog.campaign.stages[result.stage_id]
    best_times, clear_counts, previous_best = _advanced_stage_maps(
        profile.best_times_ms,
        profile.clear_counts,
        result.stage_id,
        result.clear_time_ms,
    )
    first_clear = profile.clear_counts.get(result.stage_id, 0) == 0

    result_mote_ids = frozenset(result.collected_mote_ids)
    all_motes = profile.collected_mote_ids | result_mote_ids
    # Delta ordering follows the stage contract, never set or lexical ordering.
    new_motes = tuple(
        mote.mote_id
        for mote in stage.motes
        if mote.mote_id in result_mote_ids and mote.mote_id not in profile.collected_mote_ids
    )
    new_abilities = tuple(
        ability_id for ability_id in result.discovered_ability_ids if ability_id not in profile.discovered_abilities
    )

    nodes = ordered_nodes(catalog)
    node_index = next(
        (index for index, node in enumerate(nodes) if node.node_id == result.node_id),
        None,
    )
    if node_index is None:
        raise ValueError(f"stage node is absent from canonical campaign order: {result.node_id}")
    unlocked_nodes = set(profile.unlocked_nodes)
    unlocked_worlds = set(profile.unlocked_worlds)
    new_node_ids: tuple[str, ...] = ()
    new_world_ids: tuple[str, ...] = ()
    if node_index + 1 < len(nodes):
        next_node = nodes[node_index + 1]
        if next_node.node_id not in unlocked_nodes:
            unlocked_nodes.add(next_node.node_id)
            new_node_ids = (next_node.node_id,)
        if next_node.world_id not in unlocked_worlds:
            unlocked_worlds.add(next_node.world_id)
            new_world_ids = (next_node.world_id,)

    known_motes = _known_mote_ids(catalog)
    collected_catalog_motes = len(all_motes & known_motes)
    earned_reward_ids = tuple(
        reward.reward_id for reward in catalog.rewards.mote_thresholds if reward.threshold <= collected_catalog_motes
    )
    new_reward_ids = tuple(reward_id for reward_id in earned_reward_ids if reward_id not in profile.challenge_rewards)

    updated = replace(
        profile,
        unlocked_nodes=frozenset(unlocked_nodes),
        unlocked_worlds=frozenset(unlocked_worlds),
        collected_mote_ids=all_motes,
        best_times_ms=best_times,
        clear_counts=clear_counts,
        discovered_abilities=profile.discovered_abilities | frozenset(result.discovered_ability_ids),
        challenge_rewards=profile.challenge_rewards | frozenset(earned_reward_ids),
        last_played_stage=result.stage_id,
    )
    delta = CompletionDelta(
        first_clear=first_clear,
        new_mote_ids=new_motes,
        newly_discovered_abilities=new_abilities,
        newly_unlocked_node_ids=new_node_ids,
        newly_unlocked_world_ids=new_world_ids,
        new_reward_ids=new_reward_ids,
        previous_best_ms=previous_best,
        is_new_best=previous_best is None or result.clear_time_ms < previous_best,
    )
    return updated, delta


@dataclass(slots=True)
class CompletionTracker:
    """Compatibility facade for the foundation screen's mutable session view."""

    cleared_nodes: set[str] = field(default_factory=set)
    collected_mote_ids: set[str] = field(default_factory=set)
    challenge_rewards: set[str] = field(default_factory=set)
    best_times_ms: dict[str, int] = field(default_factory=dict)
    clear_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cleared_nodes = set(_id_frozenset(self.cleared_nodes, "cleared_nodes"))
        self.collected_mote_ids = set(_id_frozenset(self.collected_mote_ids, "collected_mote_ids"))
        self.challenge_rewards = set(_id_frozenset(self.challenge_rewards, "challenge_rewards"))
        self.best_times_ms = self._mutable_int_map(self.best_times_ms, "best_times_ms")
        self.clear_counts = self._mutable_int_map(self.clear_counts, "clear_counts")

    @staticmethod
    def _mutable_int_map(payload: Mapping[str, int], name: str) -> dict[str, int]:
        return dict(_immutable_int_map(payload, name))

    def mark_stage_clear(self, node_id: str, stage_id: str, elapsed_ms: int) -> None:
        """Record the foundation session through the canonical time/count helper."""

        node_id = _identifier("node_id", node_id)
        stage_id = _identifier("stage_id", stage_id)
        elapsed_ms = _strict_int("elapsed_ms", elapsed_ms)
        best_times, clear_counts, _ = _advanced_stage_maps(
            self.best_times_ms,
            self.clear_counts,
            stage_id,
            elapsed_ms,
        )
        self.cleared_nodes.add(node_id)
        self.best_times_ms = best_times
        self.clear_counts = clear_counts

    def collect_mote(self, mote_id: str) -> None:
        """Record one stable mote ID idempotently."""

        self.collected_mote_ids.add(_identifier("mote_id", mote_id))


__all__ = [
    "CompletionBreakdown",
    "CompletionDelta",
    "CompletionTracker",
    "apply_stage_result",
    "completion_breakdown",
    "completion_percent",
]
