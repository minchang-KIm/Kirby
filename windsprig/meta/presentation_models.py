"""Frozen localized profile and stage-results presentation models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from windsprig.content.models import CatalogBundle
from windsprig.gameplay.snapshot import StageResult
from windsprig.localization import Localizer

from .completion import (
    CompletionDelta,
    completion_breakdown,
    ordered_nodes,
    ordered_worlds,
    validate_stage_result,
)
from .save_models import SaveData, SaveProfile
from .world_map import format_stage_time


@dataclass(frozen=True, slots=True)
class ProfileCardVM:
    """Localized summary for one of the three fixed profile slots."""

    slot_index: int
    profile_id: str
    display_name: str
    completion_label: str
    mote_label: str
    last_stage_label: str
    play_time_label: str
    is_empty: bool


@dataclass(frozen=True, slots=True)
class ResultMoteVM:
    """One stable stage mote and its before/current-run collection state."""

    mote_id: str
    collected_before: bool
    collected_this_run: bool


@dataclass(frozen=True, slots=True)
class UnlockVM:
    """Localized stage, world, or threshold reward unlocked by a result."""

    reward_id: str
    label: str
    kind: str


@dataclass(frozen=True, slots=True)
class ResultsViewModel:
    """Complete immutable results-screen data for one applied stage result."""

    stage_name: str
    clear_time_label: str
    best_time_label: str
    comparison_label: str
    new_best: bool
    motes: tuple[ResultMoteVM, ResultMoteVM, ResultMoteVM]
    ability_labels: tuple[str, ...]
    unlocks: tuple[UnlockVM, ...]
    completion_label: str
    can_next_stage: bool
    next_stage_id: str | None


def _format_play_time(milliseconds: int) -> str:
    if type(milliseconds) is not int or milliseconds < 0:
        raise ValueError("play_time_ms must be a non-negative integer")
    total_seconds = milliseconds // 1_000
    hours, within_hour = divmod(total_seconds, 3_600)
    minutes, seconds = divmod(within_hour, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _known_reward_ids(catalog: CatalogBundle) -> frozenset[str]:
    return frozenset(reward.reward_id for reward in catalog.rewards.mote_thresholds)


def _known_ability_ids(catalog: CatalogBundle) -> frozenset[str]:
    return frozenset(
        enemy.ability_id
        for stage in catalog.campaign.stages.values()
        for enemy in stage.enemy_spawns
        if enemy.ability_id is not None
    )


def _profile_is_empty(profile: SaveProfile, catalog: CatalogBundle) -> bool:
    stage_ids = frozenset(catalog.campaign.stages)
    mote_ids = frozenset(mote.mote_id for stage in catalog.campaign.stages.values() for mote in stage.motes)
    return (
        not any(stage_id in stage_ids and count > 0 for stage_id, count in profile.clear_counts.items())
        and not (profile.collected_mote_ids & mote_ids)
        and not (profile.challenge_rewards & _known_reward_ids(catalog))
        and not (profile.discovered_abilities & _known_ability_ids(catalog))
        and profile.play_time_ms == 0
        and profile.last_played_stage is None
    )


def build_profile_cards(
    save: SaveData,
    catalog: CatalogBundle,
    tr: Localizer,
) -> tuple[ProfileCardVM, ...]:
    """Build the fixed three profile cards from catalog-known save facts."""

    if not isinstance(save, SaveData):
        raise ValueError("save must be SaveData")
    if not isinstance(catalog, CatalogBundle):
        raise ValueError("catalog must be CatalogBundle")
    cards: list[ProfileCardVM] = []
    for slot_index, profile in enumerate(save.profiles, start=1):
        breakdown = completion_breakdown(profile, catalog)
        last_stage = (
            catalog.campaign.stages.get(profile.last_played_stage) if profile.last_played_stage is not None else None
        )
        if profile.last_played_stage is not None and last_stage is None:
            raise ValueError(f"unknown last_played_stage: {profile.last_played_stage}")
        last_stage_label = tr.text(last_stage.name_key) if last_stage is not None else tr.text("profile.no_stage")
        cards.append(
            ProfileCardVM(
                slot_index=slot_index,
                profile_id=profile.profile_id,
                display_name=profile.display_name,
                completion_label=tr.text(
                    "profile.completion",
                    percent=str(breakdown.percent),
                ),
                mote_label=tr.text(
                    "profile.motes",
                    found=breakdown.collected_motes,
                ),
                last_stage_label=last_stage_label,
                play_time_label=tr.text(
                    "profile.play_time",
                    time=_format_play_time(profile.play_time_ms),
                ),
                is_empty=_profile_is_empty(profile, catalog),
            )
        )
    return tuple(cards)


def _strict_delta_ids(name: str, values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple of IDs")
    if any(not isinstance(value, str) or not value or value != value.strip() for value in values):
        raise ValueError(f"{name} must contain non-blank trimmed IDs")
    result = cast(tuple[str, ...], values)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicate IDs")
    return result


def _validate_delta(
    result: StageResult,
    delta: CompletionDelta,
    profile: SaveProfile,
    catalog: CatalogBundle,
) -> None:
    if not isinstance(delta, CompletionDelta):
        raise ValueError("delta must be CompletionDelta")
    if type(delta.first_clear) is not bool or type(delta.is_new_best) is not bool:
        raise ValueError("completion delta flags must be booleans")
    if delta.previous_best_ms is not None and (type(delta.previous_best_ms) is not int or delta.previous_best_ms < 0):
        raise ValueError("previous_best_ms must be a non-negative integer or None")

    stage = catalog.campaign.stages[result.stage_id]
    stage_mote_ids = frozenset(mote.mote_id for mote in stage.motes)
    result_mote_ids = frozenset(result.collected_mote_ids)
    for mote_id in _strict_delta_ids("new_mote_ids", delta.new_mote_ids):
        if mote_id not in stage_mote_ids or mote_id not in result_mote_ids:
            raise ValueError(f"unknown result mote_id: {mote_id}")

    result_abilities = frozenset(result.discovered_ability_ids)
    known_abilities = _known_ability_ids(catalog)
    for ability_id in _strict_delta_ids(
        "newly_discovered_abilities",
        delta.newly_discovered_abilities,
    ):
        if ability_id not in known_abilities or ability_id not in result_abilities:
            raise ValueError(f"unknown result ability_id: {ability_id}")

    for node_id in _strict_delta_ids(
        "newly_unlocked_node_ids",
        delta.newly_unlocked_node_ids,
    ):
        if node_id not in catalog.campaign.nodes:
            raise ValueError(f"unknown unlocked node_id: {node_id}")
    for world_id in _strict_delta_ids(
        "newly_unlocked_world_ids",
        delta.newly_unlocked_world_ids,
    ):
        if world_id not in catalog.campaign.world_specs:
            raise ValueError(f"unknown unlocked world_id: {world_id}")
    known_rewards = _known_reward_ids(catalog)
    for reward_id in _strict_delta_ids("new_reward_ids", delta.new_reward_ids):
        if reward_id not in known_rewards:
            raise ValueError(f"unknown reward_id: {reward_id}")

    expected_new_best = delta.previous_best_ms is None or result.clear_time_ms < delta.previous_best_ms
    if delta.is_new_best is not expected_new_best:
        raise ValueError("is_new_best does not match the result comparison")

    _validate_post_profile(result, delta, profile, catalog)
    _validate_progression_delta(result, delta, profile, catalog)


def _validate_post_profile(
    result: StageResult,
    delta: CompletionDelta,
    profile: SaveProfile,
    catalog: CatalogBundle,
) -> None:
    clear_count = profile.clear_counts.get(result.stage_id, 0)
    if clear_count <= 0:
        raise ValueError("post profile is missing the applied stage clear")
    if delta.first_clear is not (clear_count == 1):
        raise ValueError("completion delta first_clear does not match post clear count")
    if delta.first_clear is not (delta.previous_best_ms is None):
        raise ValueError("completion delta first_clear does not match previous best")

    best_time = profile.best_times_ms.get(result.stage_id)
    if best_time is None:
        raise ValueError(f"profile is missing best time for result stage: {result.stage_id}")
    expected_best = (
        result.clear_time_ms if delta.previous_best_ms is None else min(delta.previous_best_ms, result.clear_time_ms)
    )
    if best_time != expected_best:
        raise ValueError("post profile best time does not match result comparison")

    for mote_id in result.collected_mote_ids:
        if mote_id not in profile.collected_mote_ids:
            raise ValueError(f"post profile is missing result mote: {mote_id}")
    for ability_id in result.discovered_ability_ids:
        if ability_id not in profile.discovered_abilities:
            raise ValueError(f"post profile is missing result ability: {ability_id}")
    if profile.last_played_stage != result.stage_id:
        raise ValueError("post profile last_played_stage does not match result")
    if result.node_id not in profile.unlocked_nodes:
        raise ValueError(f"post profile is missing result node: {result.node_id}")
    if result.world_id not in profile.unlocked_worlds:
        raise ValueError(f"post profile is missing result world: {result.world_id}")

    for node_id in delta.newly_unlocked_node_ids:
        if node_id not in profile.unlocked_nodes:
            raise ValueError(f"newly unlocked node is missing from post profile: {node_id}")
    for world_id in delta.newly_unlocked_world_ids:
        if world_id not in profile.unlocked_worlds:
            raise ValueError(f"newly unlocked world is missing from post profile: {world_id}")
    for reward_id in delta.new_reward_ids:
        if reward_id not in profile.challenge_rewards:
            raise ValueError(f"new reward is missing from post profile: {reward_id}")


def _validate_progression_delta(
    result: StageResult,
    delta: CompletionDelta,
    profile: SaveProfile,
    catalog: CatalogBundle,
) -> None:
    nodes = ordered_nodes(catalog)
    current_index = next(index for index, node in enumerate(nodes) if node.node_id == result.node_id)
    following = nodes[current_index + 1] if current_index + 1 < len(nodes) else None
    expected_node_ids = (following.node_id,) if following is not None else ()
    if delta.newly_unlocked_node_ids not in ((), expected_node_ids):
        raise ValueError("newly_unlocked_node_ids must be the canonical following node")

    expected_world_ids = (
        (following.world_id,) if following is not None and following.world_id != result.world_id else ()
    )
    if delta.newly_unlocked_world_ids not in ((), expected_world_ids):
        raise ValueError("newly_unlocked_world_ids must be the canonical following world")
    if not delta.first_clear and (delta.newly_unlocked_node_ids or delta.newly_unlocked_world_ids):
        raise ValueError("replay results cannot report new progression unlocks")
    if delta.newly_unlocked_world_ids and (following is None or delta.newly_unlocked_node_ids != (following.node_id,)):
        raise ValueError("a new world requires its canonical following node")

    catalog_mote_ids = frozenset(mote.mote_id for stage in catalog.campaign.stages.values() for mote in stage.motes)
    collected_count = len(profile.collected_mote_ids & catalog_mote_ids)
    reward_by_id = {reward.reward_id: reward for reward in catalog.rewards.mote_thresholds}
    for reward_id in delta.new_reward_ids:
        if reward_by_id[reward_id].threshold > collected_count:
            raise ValueError(f"reward is not threshold-eligible: {reward_id}")
    canonical_reward_ids = tuple(
        reward.reward_id for reward in catalog.rewards.mote_thresholds if reward.reward_id in delta.new_reward_ids
    )
    if delta.new_reward_ids != canonical_reward_ids:
        raise ValueError("new_reward_ids must follow canonical reward order")


def _comparison_label(
    result: StageResult,
    delta: CompletionDelta,
    tr: Localizer,
) -> str:
    if delta.previous_best_ms is None:
        return tr.text("results.first_clear")
    if result.clear_time_ms < delta.previous_best_ms:
        return tr.text(
            "results.new_best",
            delta=format_stage_time(delta.previous_best_ms - result.clear_time_ms),
        )
    return ""


def _result_motes(
    result: StageResult,
    delta: CompletionDelta,
    profile: SaveProfile,
    catalog: CatalogBundle,
) -> tuple[ResultMoteVM, ResultMoteVM, ResultMoteVM]:
    stage = catalog.campaign.stages[result.stage_id]
    if len(stage.motes) != 3:
        raise ValueError(f"stage {stage.stage_id} must contain exactly three motes")
    new_motes = frozenset(delta.new_mote_ids)
    run_motes = frozenset(result.collected_mote_ids)
    motes = tuple(
        ResultMoteVM(
            mote_id=mote.mote_id,
            collected_before=(mote.mote_id in profile.collected_mote_ids and mote.mote_id not in new_motes),
            collected_this_run=mote.mote_id in run_motes,
        )
        for mote in stage.motes
    )
    return cast(tuple[ResultMoteVM, ResultMoteVM, ResultMoteVM], motes)


def _unlocks(
    delta: CompletionDelta,
    catalog: CatalogBundle,
    tr: Localizer,
) -> tuple[UnlockVM, ...]:
    new_nodes = frozenset(delta.newly_unlocked_node_ids)
    new_worlds = frozenset(delta.newly_unlocked_world_ids)
    new_rewards = frozenset(delta.new_reward_ids)
    node_unlocks = tuple(
        UnlockVM(
            reward_id=node.node_id,
            label=tr.text(catalog.campaign.stages[node.stage_id].name_key),
            kind="stage",
        )
        for node in ordered_nodes(catalog)
        if node.node_id in new_nodes
    )
    world_unlocks = tuple(
        UnlockVM(
            reward_id=world.world_id,
            label=tr.text(world.name_key),
            kind="world",
        )
        for world in ordered_worlds(catalog)
        if world.world_id in new_worlds
    )
    reward_unlocks = tuple(
        UnlockVM(
            reward_id=reward.reward_id,
            label=tr.text(reward.name_key),
            kind=reward.kind,
        )
        for reward in catalog.rewards.mote_thresholds
        if reward.reward_id in new_rewards
    )
    return node_unlocks + world_unlocks + reward_unlocks


def build_results_view(
    result: StageResult,
    delta: CompletionDelta,
    profile: SaveProfile,
    catalog: CatalogBundle,
    tr: Localizer,
) -> ResultsViewModel:
    """Build localized results from an already-applied immutable result."""

    validate_stage_result(profile, result, catalog, require_unlocked=False)
    _validate_delta(result, delta, profile, catalog)
    stage = catalog.campaign.stages[result.stage_id]
    best_time = profile.best_times_ms[result.stage_id]
    nodes = ordered_nodes(catalog)
    node_index = next(index for index, node in enumerate(nodes) if node.node_id == result.node_id)
    following_node = nodes[node_index + 1] if node_index + 1 < len(nodes) else None
    can_next_stage = (
        delta.first_clear and following_node is not None and following_node.node_id in delta.newly_unlocked_node_ids
    )
    breakdown = completion_breakdown(profile, catalog)
    return ResultsViewModel(
        stage_name=tr.text(stage.name_key),
        clear_time_label=tr.text(
            "results.time",
            time=format_stage_time(result.clear_time_ms),
        ),
        best_time_label=tr.text(
            "results.best",
            time=format_stage_time(best_time),
        ),
        comparison_label=_comparison_label(result, delta, tr),
        new_best=delta.is_new_best,
        motes=_result_motes(result, delta, profile, catalog),
        ability_labels=tuple(tr.text(f"ability.{ability_id}.name") for ability_id in result.discovered_ability_ids),
        unlocks=_unlocks(delta, catalog, tr),
        completion_label=tr.text(
            "profile.completion",
            percent=str(breakdown.percent),
        ),
        can_next_stage=can_next_stage,
        next_stage_id=(
            catalog.campaign.nodes[following_node.node_id].stage_id
            if can_next_stage and following_node is not None
            else None
        ),
    )


__all__ = [
    "ProfileCardVM",
    "ResultMoteVM",
    "ResultsViewModel",
    "UnlockVM",
    "build_profile_cards",
    "build_results_view",
]
