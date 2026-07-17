from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from windsprig.content.loader import CampaignCatalog, load_campaign_catalog
from windsprig.meta.save_migrations import SaveMigrationCatalog, migrate_v1, migration_catalog
from windsprig.meta.save_models import save_data_to_json


def _payload() -> dict[str, object]:
    return {
        "save_version": 1,
        "profiles": [
            {
                "profile_name": "Breeze",
                "unlocked_worlds": ["world_1"],
                "cleared_nodes": ["world_1_node_1"],
                "energy_spheres": {"world_1_stage_1": 2},
                "best_times": {"world_1_stage_1": 9321},
                "challenge_unlocks": ["swift_clear"],
                "settings": {},
            }
        ],
    }


def _catalog() -> SaveMigrationCatalog:
    return SaveMigrationCatalog(
        mote_ids_by_stage={
            "world_1_stage_1": (
                "world_1_stage_1:mote:1",
                "world_1_stage_1:mote:2",
                "world_1_stage_1:mote:3",
            ),
            "world_1_stage_2": (
                "world_1_stage_2:mote:1",
                "world_1_stage_2:mote:2",
                "world_1_stage_2:mote:3",
            ),
        },
        next_node_by_node={"world_1_node_1": "world_1_node_2"},
        stage_id_by_node={
            "world_1_node_1": "world_1_stage_1",
            "world_1_node_2": "world_1_stage_2",
        },
    )


def test_v1_counts_map_to_stable_motes_and_are_clamped() -> None:
    payload = _payload()
    payload["profiles"][0]["energy_spheres"] = {  # type: ignore[index]
        "world_1_stage_1": 99,
        "world_1_stage_2": -4,
    }

    data = migrate_v1(payload, _catalog())

    profile = data.profiles[0]
    assert profile.collected_mote_ids == frozenset(
        {
            "world_1_stage_1:mote:1",
            "world_1_stage_1:mote:2",
            "world_1_stage_1:mote:3",
        }
    )
    assert profile.unlocked_nodes == frozenset({"world_1_node_1", "world_1_node_2"})
    assert profile.best_times_ms == {"world_1_stage_1": 9321}
    assert profile.clear_counts == {"world_1_stage_1": 1}
    assert data.prototype_imported is True


def test_missing_prototype_slots_become_safe_empty_profiles() -> None:
    data = migrate_v1(_payload(), _catalog())

    assert tuple(profile.profile_id for profile in data.profiles) == (
        "profile_1",
        "profile_2",
        "profile_3",
    )
    assert data.profiles[1].display_name == "Sprig 2"
    assert data.profiles[1].unlocked_nodes == frozenset({"world_1_node_1"})


def test_bridge_extensions_preserve_exact_motes_and_replay_counts() -> None:
    payload = _payload()
    payload["profiles"][0].update(  # type: ignore[index,union-attr]
        energy_spheres={"world_1_stage_1": 3},
        collected_mote_ids=["world_1_stage_1:mote:3"],
        clear_counts={"world_1_stage_1": 4},
    )

    profile = migrate_v1(payload, _catalog()).profiles[0]

    assert profile.collected_mote_ids == frozenset({"world_1_stage_1:mote:3"})
    assert profile.clear_counts == {"world_1_stage_1": 4}


def test_migration_is_independent_of_legacy_mapping_and_set_like_list_order() -> None:
    first = _payload()
    first_profile = first["profiles"][0]  # type: ignore[index]
    first_profile["cleared_nodes"] = ["world_1_node_2", "world_1_node_1"]
    first_profile["energy_spheres"] = {"world_1_stage_2": 1, "world_1_stage_1": 2}
    second = _payload()
    second_profile = second["profiles"][0]  # type: ignore[index]
    second_profile["cleared_nodes"] = ["world_1_node_1", "world_1_node_2"]
    second_profile["energy_spheres"] = {"world_1_stage_1": 2, "world_1_stage_2": 1}

    assert save_data_to_json(migrate_v1(first, _catalog())) == save_data_to_json(
        migrate_v1(second, _catalog())
    )


def test_campaign_catalog_freezes_three_content_order_mote_ids_and_next_nodes() -> None:
    campaign = load_campaign_catalog(Path("windsprig/content"))

    catalog = migration_catalog(campaign)

    assert catalog.mote_ids_by_stage["world_1_stage_1"] == (
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
        "world_1_stage_1:mote:3",
    )
    assert catalog.next_node_by_node["world_1_node_1"] == "world_1_node_2"
    assert catalog.next_node_by_node["world_1_node_5"] == "world_2_node_1"
    assert "world_6_node_5" not in catalog.next_node_by_node
    assert catalog.stage_id_by_node["world_1_node_1"] == "world_1_stage_1"
    assert len(catalog.mote_ids_by_stage) == 30
    assert len(catalog.next_node_by_node) == 29
    assert len(catalog.stage_id_by_node) == 30
    assert SaveMigrationCatalog.from_campaign(campaign) == catalog


def test_campaign_catalog_generation_does_not_depend_on_mapping_insertion_order() -> None:
    campaign = load_campaign_catalog(Path("windsprig/content"))
    reordered = CampaignCatalog(
        worlds=dict(reversed(tuple(campaign.worlds.items()))),
        stages=dict(reversed(tuple(campaign.stages.items()))),
    )

    assert migration_catalog(reordered) == migration_catalog(campaign)


def test_campaign_catalog_rejects_node_and_stage_identity_mismatch() -> None:
    campaign = load_campaign_catalog(Path("windsprig/content"))
    stage_id = "world_1_stage_1"
    mismatched_stages = dict(campaign.stages)
    mismatched_stages[stage_id] = replace(mismatched_stages[stage_id], node_id="wrong_node")

    with pytest.raises(ValueError, match="node_id.*world_1_node_1"):
        migration_catalog(CampaignCatalog(worlds=campaign.worlds, stages=mismatched_stages))


def test_campaign_catalog_rejects_orphan_stage() -> None:
    campaign = load_campaign_catalog(Path("windsprig/content"))
    stages = dict(campaign.stages)
    stages["orphan_stage"] = replace(
        stages["world_1_stage_1"],
        stage_id="orphan_stage",
        node_id="orphan_node",
    )

    with pytest.raises(ValueError, match="orphan stage.*orphan_stage"):
        migration_catalog(CampaignCatalog(worlds=campaign.worlds, stages=stages))


def test_campaign_catalog_rejects_stage_referenced_by_multiple_nodes() -> None:
    campaign = load_campaign_catalog(Path("windsprig/content"))
    worlds = {world_id: list(nodes) for world_id, nodes in campaign.worlds.items()}
    worlds["world_1"].append(replace(worlds["world_1"][0], node_id="duplicate_stage_node"))

    with pytest.raises(ValueError, match="stage referenced more than once.*world_1_stage_1"):
        migration_catalog(CampaignCatalog(worlds=worlds, stages=campaign.stages))


def test_migration_catalog_owns_immutable_mapping_copies() -> None:
    motes = {"stage": ("stage:mote:1",)}
    next_nodes = {"node": "next"}
    stages = {"node": "stage"}
    catalog = SaveMigrationCatalog(motes, next_nodes, stages)
    motes["stage"] = ("changed",)
    next_nodes["node"] = "changed"
    stages["node"] = "changed"

    assert catalog.mote_ids_by_stage["stage"] == ("stage:mote:1",)
    assert catalog.next_node_by_node["node"] == "next"
    assert catalog.stage_id_by_node["node"] == "stage"
    with pytest.raises(TypeError):
        catalog.next_node_by_node["node"] = "other"  # type: ignore[index]
    with pytest.raises(TypeError):
        catalog.stage_id_by_node["node"] = "other"  # type: ignore[index]


def test_migration_rejects_cleared_nodes_without_stage_identity_mapping() -> None:
    catalog = SaveMigrationCatalog(
        mote_ids_by_stage={"world_1_stage_1": ("world_1_stage_1:mote:1",)},
        next_node_by_node={"world_1_node_1": "world_1_node_2"},
        stage_id_by_node={},
    )

    with pytest.raises(ValueError, match="stage mapping.*world_1_node_1"):
        migrate_v1(_payload(), catalog)


def test_migration_catalog_requires_explicit_node_to_stage_mapping() -> None:
    with pytest.raises(TypeError, match="stage_id_by_node"):
        SaveMigrationCatalog(  # type: ignore[call-arg]
            mote_ids_by_stage={"world_1_stage_1": ("world_1_stage_1:mote:1",)},
            next_node_by_node={},
        )


def test_node_keyed_prototype_times_normalize_to_stable_stage_metrics() -> None:
    payload = _payload()
    payload["profiles"][0]["best_times"] = {  # type: ignore[index]
        "world_1_stage_1": 10000,
        "world_1_node_1": 9000,
    }

    profile = migrate_v1(payload, _catalog()).profiles[0]

    assert profile.best_times_ms == {"world_1_stage_1": 9000}
    assert profile.clear_counts == {"world_1_stage_1": 1}


def test_first_prototype_profile_supplies_recognized_global_settings() -> None:
    payload = _payload()
    payload["profiles"].append(  # type: ignore[union-attr]
        {"profile_name": "Gust", "settings": {"language": "en", "fullscreen": False}}
    )
    payload["profiles"][0]["settings"] = {  # type: ignore[index]
        "fullscreen": True,
        "integer_scaling": True,
        "master_volume": 0.25,
        "music_volume": 0.5,
        "sfx_volume": 0.75,
        "muted": True,
        "screen_shake": False,
        "reduced_motion": True,
        "draw_toggle": True,
        "guard_toggle": True,
        "language": "ko",
        "keyboard_p1_preset": "ijkl",
        "keyboard_p2_preset": "arrows",
        "gamepad_mapping": "southpaw",
    }

    settings = migrate_v1(payload, _catalog()).settings

    assert settings.display.fullscreen is True
    assert settings.display.integer_scaling is True
    assert settings.audio.master_volume == 0.25
    assert settings.audio.muted is True
    assert settings.accessibility.reduced_motion is True
    assert settings.accessibility.draw_toggle is True
    assert settings.language == "ko"
    assert settings.controls.keyboard_p1_preset == "ijkl"
    assert settings.controls.gamepad_mapping == "southpaw"


def test_v1_settings_migration_converts_huge_volume_overflow_to_field_value_error() -> None:
    payload = _payload()
    payload["profiles"][0]["settings"] = {"master_volume": 10**10000}  # type: ignore[index]

    with pytest.raises(ValueError, match="master_volume"):
        migrate_v1(payload, _catalog())


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"unknown": True}, "unknown prototype settings fields"),
        ({"fullscreen": 1}, "fullscreen"),
        ({"master_volume": float("nan")}, "master_volume"),
        ({"language": "jp"}, "language"),
    ],
)
def test_malformed_or_unknown_prototype_settings_are_rejected(
    settings: dict[str, object], message: str
) -> None:
    payload = _payload()
    payload["profiles"][0]["settings"] = settings  # type: ignore[index]

    with pytest.raises(ValueError, match=message):
        migrate_v1(payload, _catalog())


@pytest.mark.parametrize(
    ("motes", "message"),
    [
        ({"": ("stage:mote:1",)}, "stage"),
        ({"stage": ("",)}, "mote"),
        ({"stage": ("stage:mote:1", "stage:mote:1")}, "duplicate"),
        ({"stage": ("shared",), "other": ("shared",)}, "duplicate"),
    ],
)
def test_migration_catalog_rejects_blank_or_duplicate_stable_ids(
    motes: dict[str, tuple[str, ...]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        SaveMigrationCatalog(motes, {}, {})


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update(unknown=True), "unknown prototype save fields"),
        (
            lambda payload: payload["profiles"][0].update(unknown=True),  # type: ignore[index,union-attr]
            "unknown prototype profile fields",
        ),
        (lambda payload: payload.pop("save_version"), "save_version is required"),
        (lambda payload: payload.update(save_version=True), "save_version"),
        (lambda payload: payload.update(save_version=2), "save_version must be 1"),
        (lambda payload: payload.update(profiles={}), "profiles must be a list"),
        (lambda payload: payload.update(profiles=[]), "at least one profile"),
        (
            lambda payload: payload.update(
                profiles=[
                    {"profile_name": "One"},
                    {"profile_name": "Two"},
                    {"profile_name": "Three"},
                    {"profile_name": "Four"},
                ]
            ),
            "at most three profiles",
        ),
        (lambda payload: payload.update(profiles=[[]]), "profile must be an object"),
        (lambda payload: payload["profiles"][0].pop("profile_name"), "profile_name is required"),  # type: ignore[index,union-attr]
        (lambda payload: payload["profiles"][0].update(profile_name=" "), "profile_name"),  # type: ignore[index,union-attr]
        (lambda payload: payload["profiles"][0].update(cleared_nodes={}), "cleared_nodes"),  # type: ignore[index,union-attr]
        (
            lambda payload: payload["profiles"][0].update(cleared_nodes=["node", "node"]),  # type: ignore[index,union-attr]
            "cleared_nodes",
        ),
        (
            lambda payload: payload["profiles"][0].update(energy_spheres=[]),  # type: ignore[index,union-attr]
            "energy_spheres must be an object",
        ),
        (
            lambda payload: payload["profiles"][0].update(energy_spheres={"stage": True}),  # type: ignore[index,union-attr]
            "energy_spheres",
        ),
        (
            lambda payload: payload["profiles"][0].update(best_times={"stage": -1}),  # type: ignore[index,union-attr]
            "best_times",
        ),
        (
            lambda payload: payload["profiles"][0].update(best_times={"stage": True}),  # type: ignore[index,union-attr]
            "best_times",
        ),
        (
            lambda payload: payload["profiles"][0].update(challenge_unlocks=[""]),  # type: ignore[index,union-attr]
            "challenge_unlocks",
        ),
        (lambda payload: payload["profiles"][0].update(settings=[]), "settings"),  # type: ignore[index,union-attr]
        (
            lambda payload: payload["profiles"][0].update(  # type: ignore[index,union-attr]
                collected_mote_ids=["world_1_stage_1:mote:1", "world_1_stage_1:mote:1"]
            ),
            "collected_mote_ids",
        ),
        (
            lambda payload: payload["profiles"][0].update(  # type: ignore[index,union-attr]
                clear_counts={"world_1_stage_1": True}
            ),
            "clear_counts",
        ),
    ],
)
def test_malformed_v1_payloads_are_rejected(
    mutate: Callable[[dict[str, object]], object], message: str
) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        migrate_v1(payload, _catalog())


@pytest.mark.parametrize("payload", [None, [], "save", 1, True])
def test_non_object_v1_payloads_are_actionable_value_errors(payload: object) -> None:
    with pytest.raises(ValueError, match="prototype save must be an object"):
        migrate_v1(payload, _catalog())
