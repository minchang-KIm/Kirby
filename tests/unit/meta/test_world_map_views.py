from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from windsprig.content import CampaignCatalog, CatalogBundle, load_catalog_bundle
from windsprig.localization import Localizer
from windsprig.meta.completion import CompletionTracker
from windsprig.meta.save_models import SaveProfile
from windsprig.meta.unlock_rules import UnlockRules
from windsprig.meta.world_map import (
    NodeState,
    WorldMapService,
    build_world_map_view,
    format_stage_time,
)

CONTENT_DIR = Path("windsprig/content")


def _bundle() -> CatalogBundle:
    return load_catalog_bundle(CONTENT_DIR)


def _localizer(language: str = "en") -> Localizer:
    return Localizer.load(CONTENT_DIR, language)  # type: ignore[arg-type]


def test_map_exposes_shape_icon_text_selection_and_locked_connectors() -> None:
    vm = build_world_map_view(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _bundle(),
        "world_1_node_1",
        _localizer(),
    )

    first, second, *_, boss = vm.worlds[0].nodes
    assert (first.state, first.shape_token, first.icon_token, first.selected) == (
        NodeState.AVAILABLE,
        "node.round",
        "stage.leaf",
        True,
    )
    assert first.label == "First Flight"
    assert first.mote_states == (False, False, False)
    assert first.best_time_label == ""
    assert second.state is NodeState.LOCKED
    assert boss.is_boss is True
    assert (boss.shape_token, boss.icon_token) == ("node.hex-boss", "boss.crown")
    assert vm.worlds[0].connectors[0].unlocked is False
    assert vm.worlds[1].locked is True
    assert all(node.state is NodeState.LOCKED for node in vm.worlds[1].nodes)
    assert vm.total_motes_label == "Wind Motes 0 / 90"
    assert vm.completion_label == "Completion 0.0%"
    assert vm.save_status_key == "save.saved"


def test_map_uses_stable_mote_order_best_time_and_both_endpoint_connector_rule() -> None:
    profile = replace(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        unlocked_nodes=frozenset({"world_1_node_1", "world_1_node_2"}),
        clear_counts={"world_1_stage_1": 1},
        collected_mote_ids=frozenset({"world_1_stage_1:mote:2"}),
        best_times_ms={"world_1_stage_1": 90_000},
    )

    vm = build_world_map_view(profile, _bundle(), "world_1_node_2", _localizer())
    first, second = vm.worlds[0].nodes[:2]

    assert first.state is NodeState.CLEARED
    assert first.mote_states == (False, True, False)
    assert first.best_time_label == "Best 01:30.000"
    assert second.state is NodeState.AVAILABLE
    assert second.selected is True
    assert vm.worlds[0].connectors[0].unlocked is True
    assert vm.worlds[0].connectors[1].unlocked is False


def test_map_uses_authored_world_order_instead_of_mapping_key_order() -> None:
    bundle = _bundle()
    specs = dict(bundle.campaign.world_specs)
    specs["world_1"] = replace(specs["world_1"], order=2)
    specs["world_2"] = replace(specs["world_2"], order=1)
    reordered_campaign = CampaignCatalog(
        worlds=bundle.campaign.worlds,
        stages=bundle.campaign.stages,
        version=bundle.campaign.version,
        world_specs=specs,
    )
    reordered = CatalogBundle(reordered_campaign, bundle.bosses, bundle.rewards)

    vm = build_world_map_view(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        reordered,
        "world_1_node_1",
        _localizer(),
    )

    assert tuple(world.world_id for world in vm.worlds[:2]) == ("world_2", "world_1")


def test_map_localizes_world_stage_and_summary_copy_in_korean() -> None:
    vm = build_world_map_view(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _bundle(),
        "world_1_node_1",
        _localizer("ko"),
    )

    assert vm.worlds[0].label == "햇잎 골짜기"
    assert vm.worlds[0].nodes[0].label == "첫 비행"
    assert vm.total_motes_label == "바람 티끌 0 / 90"
    assert vm.completion_label == "달성도 0.0%"


def test_map_rejects_unknown_selection_at_the_catalog_boundary() -> None:
    with pytest.raises(ValueError, match="unknown selected_node_id: missing_node"):
        build_world_map_view(
            SaveProfile(profile_id="profile_1", display_name="Sprig"),
            _bundle(),
            "missing_node",
            _localizer(),
        )


def test_map_view_models_are_frozen_slotted_and_deeply_immutable() -> None:
    vm = build_world_map_view(
        SaveProfile(profile_id="profile_1", display_name="Sprig"),
        _bundle(),
        "world_1_node_1",
        _localizer(),
    )

    assert not hasattr(vm, "__dict__")
    assert isinstance(vm.worlds, tuple)
    assert isinstance(vm.worlds[0].nodes, tuple)
    assert isinstance(vm.worlds[0].connectors, tuple)
    with pytest.raises(FrozenInstanceError):
        vm.selected_node_id = "world_1_node_2"  # type: ignore[misc]


@pytest.mark.parametrize("milliseconds", [-1, True, 1.5])
def test_stage_time_format_rejects_invalid_numeric_values(milliseconds: object) -> None:
    with pytest.raises(ValueError, match="stage time must be a non-negative integer"):
        format_stage_time(milliseconds)  # type: ignore[arg-type]


def test_compatibility_map_service_returns_first_playable_or_none_in_authored_order() -> None:
    campaign = _bundle().campaign
    service = WorldMapService(campaign, UnlockRules(campaign))
    tracker = CompletionTracker()

    assert service.first_playable_node(tracker, {"world_1"}) == campaign.nodes["world_1_node_1"]

    for node in campaign.worlds["world_1"]:
        tracker.mark_stage_clear(node.node_id, node.stage_id, 1_000)

    assert service.first_playable_node(tracker, {"world_1"}) is None
