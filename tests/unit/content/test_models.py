"""Strict immutable campaign model and loader contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import cast

import pytest

from tests.helpers.catalog import minimal_documents, write_minimal_bundle
from windsprig.content import loader, models
from windsprig.content.loader import (
    ContentError,
    load_asset_manifest,
    load_campaign_catalog,
    load_catalog_bundle,
    load_locales,
)

JsonObject = dict[str, object]
Mutation = Callable[[dict[str, JsonObject]], None]


def _object_at(document: object, path: tuple[str | int, ...]) -> JsonObject:
    current = document
    for component in path:
        if isinstance(component, int):
            current = cast(list[object], current)[component]
        else:
            current = cast(JsonObject, current)[component]
    return cast(JsonObject, current)


def _add_field(document_name: str, path: tuple[str | int, ...]) -> Mutation:
    def mutate(documents: dict[str, JsonObject]) -> None:
        _object_at(documents[document_name], path)["unexpected"] = True

    return mutate


def _remove_field(document_name: str, path: tuple[str | int, ...], field_name: str) -> Mutation:
    def mutate(documents: dict[str, JsonObject]) -> None:
        _object_at(documents[document_name], path).pop(field_name)

    return mutate


def _set_non_finite_player_spawn(documents: dict[str, JsonObject]) -> None:
    stage = _object_at(documents["campaign"], ("stages", 0))
    spawns = cast(list[object], stage["player_spawns"])
    cast(list[object], spawns[0])[0] = float("nan")


def _set_non_finite_interaction_parameter(documents: dict[str, JsonObject]) -> None:
    interaction = _object_at(
        documents["campaign"],
        ("stages", 0, "interactions", 0),
    )
    cast(JsonObject, interaction["params"])["strength"] = float("-inf")


def _asset_document() -> JsonObject:
    return {
        "art": {
            "boss.demo": {
                "path": "generated/boss.png",
                "width": 64,
                "height": 64,
                "frames": 1,
                "pixel_sha256": "a" * 64,
                "mandatory": True,
                "provenance": "procedural-vector-v1",
            }
        },
        "audio": {
            "sfx.boss.demo": {
                "path": "generated/boss.wav",
                "bus": "sfx",
                "mandatory": True,
                "sha256": "b" * 64,
            }
        },
        "font": {
            "path": "fonts/NotoSansKR.ttf",
            "license": "fonts/OFL-NotoSansKR.txt",
            "mandatory": True,
            "sha256": "c" * 64,
        },
        "provenance_files": ["generated/art-provenance.json"],
    }


def test_loader_reexports_the_single_canonical_model_identities() -> None:
    for name in (
        "MoteSpec",
        "CheckpointSpec",
        "InteractionSpec",
        "EnemySpawn",
        "StageSpec",
        "WorldNode",
        "CampaignCatalog",
        "CatalogBundle",
    ):
        assert getattr(loader, name) is getattr(models, name)


def test_campaign_fields_append_to_the_frozen_gameplay_prefix() -> None:
    assert tuple(field.name for field in fields(models.MoteSpec))[:3] == (
        "mote_id",
        "tile_x",
        "tile_y",
    )
    assert tuple(field.name for field in fields(models.InteractionSpec))[:6] == (
        "interaction_id",
        "kind",
        "tile_x",
        "tile_y",
        "width_tiles",
        "height_tiles",
    )
    assert tuple(field.name for field in fields(models.EnemySpawn))[:6] == (
        "x",
        "y",
        "kind",
        "ability_id",
        "patrol_left",
        "patrol_right",
    )
    assert tuple(field.name for field in fields(models.StageSpec))[:16] == (
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
    )


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (_add_field("campaign", ()), "campaign.unexpected"),
        (_add_field("campaign", ("worlds", 0)), "campaign.worlds[0].unexpected"),
        (
            _add_field("campaign", ("worlds", 0, "nodes", 0)),
            "campaign.worlds[0].nodes[0].unexpected",
        ),
        (_add_field("campaign", ("stages", 0)), "campaign.stages[0].unexpected"),
        (
            _add_field("campaign", ("stages", 0, "enemy_spawns", 0)),
            "campaign.stages[0].enemy_spawns[0].unexpected",
        ),
        (
            _add_field("campaign", ("stages", 0, "motes", 0)),
            "campaign.stages[0].motes[0].unexpected",
        ),
        (
            _add_field("campaign", ("stages", 0, "checkpoints", 0)),
            "campaign.stages[0].checkpoints[0].unexpected",
        ),
        (
            _add_field("campaign", ("stages", 0, "interactions", 0)),
            "campaign.stages[0].interactions[0].unexpected",
        ),
        (
            _add_field("campaign", ("stages", 0, "navigation")),
            "campaign.stages[0].navigation.unexpected",
        ),
        (
            _add_field("campaign", ("stages", 0, "navigation", "nodes", 0)),
            "campaign.stages[0].navigation.nodes[0].unexpected",
        ),
        (_add_field("bosses", ()), "bosses.unexpected"),
        (_add_field("bosses", ("bosses", 0)), "bosses.bosses[0].unexpected"),
        (
            _add_field("bosses", ("bosses", 0, "phases", 0)),
            "bosses.bosses[0].phases[0].unexpected",
        ),
        (
            _add_field("bosses", ("bosses", 0, "phases", 0, "attacks", 0)),
            "bosses.bosses[0].phases[0].attacks[0].unexpected",
        ),
        (_add_field("rewards", ()), "rewards.unexpected"),
        (
            _add_field("rewards", ("mote_thresholds", 0)),
            "rewards.mote_thresholds[0].unexpected",
        ),
    ],
)
def test_loader_reports_exact_unknown_fields_for_every_object_family(
    tmp_path: Path,
    mutate: Mutation,
    path: str,
) -> None:
    documents = minimal_documents()
    mutate(documents)
    write_minimal_bundle(tmp_path, documents)

    with pytest.raises(ContentError, match=rf"^{re.escape(path)}: unknown field$"):
        load_catalog_bundle(tmp_path)


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (_remove_field("campaign", (), "worlds"), "campaign.worlds"),
        (_remove_field("campaign", ("worlds", 0), "world_id"), "campaign.worlds[0].world_id"),
        (
            _remove_field("campaign", ("worlds", 0, "nodes", 0), "node_id"),
            "campaign.worlds[0].nodes[0].node_id",
        ),
        (_remove_field("campaign", ("stages", 0), "stage_id"), "campaign.stages[0].stage_id"),
        (
            _remove_field("campaign", ("stages", 0, "enemy_spawns", 0), "x"),
            "campaign.stages[0].enemy_spawns[0].x",
        ),
        (
            _remove_field("campaign", ("stages", 0, "motes", 0), "mote_id"),
            "campaign.stages[0].motes[0].mote_id",
        ),
        (
            _remove_field("campaign", ("stages", 0, "checkpoints", 0), "checkpoint_id"),
            "campaign.stages[0].checkpoints[0].checkpoint_id",
        ),
        (
            _remove_field("campaign", ("stages", 0, "interactions", 0), "interaction_id"),
            "campaign.stages[0].interactions[0].interaction_id",
        ),
        (
            _remove_field("campaign", ("stages", 0, "navigation"), "start"),
            "campaign.stages[0].navigation.start",
        ),
        (
            _remove_field("campaign", ("stages", 0, "navigation", "nodes", 0), "nav_id"),
            "campaign.stages[0].navigation.nodes[0].nav_id",
        ),
        (_remove_field("bosses", (), "bosses"), "bosses.bosses"),
        (_remove_field("bosses", ("bosses", 0), "boss_id"), "bosses.bosses[0].boss_id"),
        (
            _remove_field("bosses", ("bosses", 0, "phases", 0), "phase_id"),
            "bosses.bosses[0].phases[0].phase_id",
        ),
        (
            _remove_field("bosses", ("bosses", 0, "phases", 0, "attacks", 0), "attack_id"),
            "bosses.bosses[0].phases[0].attacks[0].attack_id",
        ),
        (_remove_field("rewards", (), "mote_thresholds"), "rewards.mote_thresholds"),
        (
            _remove_field("rewards", ("mote_thresholds", 0), "threshold"),
            "rewards.mote_thresholds[0].threshold",
        ),
    ],
)
def test_loader_reports_exact_missing_fields_for_every_object_family(
    tmp_path: Path,
    mutate: Mutation,
    path: str,
) -> None:
    documents = minimal_documents()
    mutate(documents)
    write_minimal_bundle(tmp_path, documents)

    with pytest.raises(ContentError, match=rf"^{re.escape(path)}: missing field$"):
        load_catalog_bundle(tmp_path)


@pytest.mark.parametrize(
    ("mutate", "path", "message"),
    [
        (
            lambda documents: _object_at(documents["campaign"], ("stages", 0)).__setitem__("width_tiles", True),
            "campaign.stages[0].width_tiles",
            "must be an integer",
        ),
        (
            lambda documents: _object_at(documents["campaign"], ("stages", 0, "enemy_spawns", 0)).__setitem__(
                "x", True
            ),
            "campaign.stages[0].enemy_spawns[0].x",
            "must be a number",
        ),
        (
            _set_non_finite_player_spawn,
            "campaign.stages[0].player_spawns[0][0]",
            "must be finite",
        ),
        (
            lambda documents: _object_at(documents["bosses"], ("bosses", 0, "phases", 0)).__setitem__(
                "enter_at_hp_ratio", float("inf")
            ),
            "bosses.bosses[0].phases[0].enter_at_hp_ratio",
            "must be finite",
        ),
        (
            _set_non_finite_interaction_parameter,
            "campaign.stages[0].interactions[0].params.strength",
            "must be finite",
        ),
    ],
)
def test_loader_rejects_boolean_numbers_and_non_finite_values_with_full_paths(
    tmp_path: Path,
    mutate: Mutation,
    path: str,
    message: str,
) -> None:
    documents = minimal_documents()
    mutate(documents)
    write_minimal_bundle(tmp_path, documents)

    with pytest.raises(
        ContentError,
        match=rf"^{re.escape(path)}: {re.escape(message)}$",
    ):
        load_catalog_bundle(tmp_path)


@pytest.mark.parametrize(
    ("legacy_field", "canonical_field", "value", "path"),
    [
        ("energy_spheres", "motes", [[2, 3]], "campaign.stages[0].energy_spheres"),
        (
            "copy_ability",
            "ability_id",
            "fire",
            "campaign.stages[0].enemy_spawns[0].copy_ability",
        ),
    ],
)
def test_loader_and_compatibility_projection_reject_legacy_aliases(
    tmp_path: Path,
    legacy_field: str,
    canonical_field: str,
    value: object,
    path: str,
) -> None:
    documents = minimal_documents()
    stage = _object_at(documents["campaign"], ("stages", 0))
    target = stage if canonical_field == "motes" else _object_at(stage, ("enemy_spawns", 0))
    target.pop(canonical_field)
    target[legacy_field] = value
    write_minimal_bundle(tmp_path, documents)

    with pytest.raises(ContentError, match=rf"^{re.escape(path)}: unknown field$"):
        load_catalog_bundle(tmp_path)
    with pytest.raises(ContentError, match=rf"^{re.escape(path)}: unknown field$"):
        load_campaign_catalog(tmp_path)


@pytest.mark.parametrize(
    "mote_id",
    ["demo_01.mote.1", "other:mote:1", "demo_01:mote:0", "demo_01:mote:01", "demo_01:mote:١"],
)
def test_loader_rejects_non_canonical_mote_syntax(tmp_path: Path, mote_id: str) -> None:
    documents = minimal_documents()
    _object_at(documents["campaign"], ("stages", 0, "motes", 0))["mote_id"] = mote_id
    write_minimal_bundle(tmp_path, documents)

    with pytest.raises(
        ContentError,
        match=r"^campaign\.stages\[0\]\.motes\[0\]\.mote_id: must match demo_01:mote:<positive ASCII integer>$",
    ):
        load_catalog_bundle(tmp_path)


def test_loaded_catalog_is_deeply_immutable(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    stage = bundle.campaign.stages["demo_01"]
    node = bundle.campaign.world_nodes("demo")[0]
    boss = bundle.bosses["demo_boss"]

    with pytest.raises(TypeError):
        bundle.campaign.stages["other"] = stage  # type: ignore[index]
    with pytest.raises(TypeError):
        bundle.campaign.worlds["other"] = ()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        node.requires += ("other",)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        stage.navigation.nodes += ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        stage.interactions[0].params += (("other", 1),)  # type: ignore[misc]
    with pytest.raises(TypeError):
        bundle.bosses["other"] = boss  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        boss.phases[0].attacks[0].parameters += (("other", 1),)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        bundle.rewards.mote_thresholds += ()  # type: ignore[misc]
    assert isinstance(bundle.campaign.world_nodes("missing"), tuple)


def test_compatibility_projection_returns_the_same_canonical_objects(tmp_path: Path) -> None:
    content = write_minimal_bundle(tmp_path)

    assert load_campaign_catalog(content) == load_catalog_bundle(content).campaign
    assert type(load_campaign_catalog(content)) is models.CampaignCatalog


def test_campaign_catalog_rebuilds_all_node_views_from_worlds(tmp_path: Path) -> None:
    campaign = load_catalog_bundle(write_minimal_bundle(tmp_path)).campaign
    replacement_node = replace(campaign.worlds["demo"][0], rewards=("reward.new",))

    rebuilt = replace(campaign, worlds={"demo": (replacement_node,)})

    assert rebuilt.nodes[replacement_node.node_id] is replacement_node
    assert rebuilt.world_specs["demo"].nodes is rebuilt.worlds["demo"]
    assert rebuilt.world_specs["demo"].nodes[0] is replacement_node


def test_world_presentation_metadata_round_trips_without_forking_nodes(
    tmp_path: Path,
) -> None:
    campaign = load_catalog_bundle(write_minimal_bundle(tmp_path)).campaign

    world = campaign.world_specs["demo"]
    assert (
        world.order,
        world.name_key,
        world.identity_key,
        world.mechanic_keys,
        world.palette_id,
    ) == (
        1,
        "world.demo.name",
        "world.demo.identity",
        ("mechanic.gust",),
        "demo",
    )
    assert world.nodes is campaign.worlds["demo"]
    assert world.nodes[0] is campaign.nodes["demo_node_1"]
    with pytest.raises(TypeError):
        campaign.world_specs["other"] = world  # type: ignore[index]


def test_layout_signature_is_order_independent_and_route_sensitive(tmp_path: Path) -> None:
    stage = load_catalog_bundle(write_minimal_bundle(tmp_path)).campaign.stages["demo_01"]
    reordered = replace(stage, solids=tuple(reversed(stage.solids)))
    changed_route = replace(
        stage,
        motes=(replace(stage.motes[0], route="optional"), *stage.motes[1:]),
    )

    assert stage.layout_signature() == reordered.layout_signature()
    assert len(stage.layout_signature()) == 20
    assert stage.layout_signature() != changed_route.layout_signature()


def test_duplicate_json_keys_are_rejected_at_the_nested_path(tmp_path: Path) -> None:
    content = write_minimal_bundle(tmp_path)
    campaign_path = content / "campaign.json"
    source = campaign_path.read_text(encoding="utf-8")
    marker = '"stage_id": "demo_01",'
    index = source.rfind(marker)
    source = source[: index + len(marker)] + '\n      "stage_id": "other",' + source[index + len(marker) :]
    campaign_path.write_text(source, encoding="utf-8")

    with pytest.raises(ContentError, match=r"^campaign\.stages\[0\]\.stage_id: duplicate field$"):
        load_catalog_bundle(content)


def test_missing_checkpoints_are_not_defaulted(tmp_path: Path) -> None:
    documents = minimal_documents()
    _object_at(documents["campaign"], ("stages", 0)).pop("checkpoints")
    write_minimal_bundle(tmp_path, documents)

    with pytest.raises(ContentError, match=r"^campaign\.stages\[0\]\.checkpoints: missing field$"):
        load_campaign_catalog(tmp_path)


def test_invalid_json_is_reported_as_a_content_error(tmp_path: Path) -> None:
    write_minimal_bundle(tmp_path)
    (tmp_path / "bosses.json").write_text("{", encoding="utf-8")

    with pytest.raises(ContentError, match=r"^bosses: invalid JSON"):
        load_catalog_bundle(tmp_path)


def test_invalid_utf8_is_reported_as_a_content_error(tmp_path: Path) -> None:
    write_minimal_bundle(tmp_path)
    (tmp_path / "bosses.json").write_bytes(b"\xff")

    with pytest.raises(ContentError, match=r"^bosses: invalid UTF-8$"):
        load_catalog_bundle(tmp_path)


def test_bundle_json_is_standard_serializable_fixture(tmp_path: Path) -> None:
    documents = minimal_documents()
    write_minimal_bundle(tmp_path, documents)

    assert json.loads((tmp_path / "campaign.json").read_text(encoding="utf-8"))["version"] == "1.0.0"


def test_asset_and_locale_loaders_return_deeply_immutable_native_models(tmp_path: Path) -> None:
    (tmp_path / "assets.json").write_text(
        json.dumps(
            {
                "art": {
                    "boss.demo": {
                        "path": "generated/boss.png",
                        "width": 64,
                        "height": 64,
                        "frames": 1,
                        "pixel_sha256": "a" * 64,
                        "mandatory": True,
                        "provenance": "procedural-vector-v1",
                    }
                },
                "audio": {
                    "sfx.boss.demo": {
                        "path": "generated/boss.wav",
                        "bus": "sfx",
                        "mandatory": True,
                        "sha256": "b" * 64,
                    }
                },
                "font": {
                    "path": "fonts/NotoSansKR.ttf",
                    "license": "fonts/OFL-NotoSansKR.txt",
                    "mandatory": True,
                    "sha256": "c" * 64,
                },
                "provenance_files": ["generated/art-provenance.json"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "strings.en.json").write_text(json.dumps({"stage.demo.name": "Demo {count}"}), encoding="utf-8")
    (tmp_path / "strings.ko.json").write_text(json.dumps({"stage.demo.name": "데모 {count}"}), encoding="utf-8")

    manifest = load_asset_manifest(tmp_path / "assets.json")
    locales = load_locales(tmp_path)

    assert manifest.art["boss.demo"].width == 64
    assert manifest.audio["sfx.boss.demo"].bus == "sfx"
    assert manifest.font.license == "fonts/OFL-NotoSansKR.txt"
    assert locales.strings["ko"]["stage.demo.name"] == "데모 {count}"
    with pytest.raises(TypeError):
        manifest.art["other"] = manifest.art["boss.demo"]  # type: ignore[index]
    with pytest.raises(TypeError):
        locales.strings["en"]["other"] = "Other"  # type: ignore[index]


def test_asset_loader_reports_nested_schema_and_numeric_errors(tmp_path: Path) -> None:
    (tmp_path / "assets.json").write_text(
        json.dumps(
            {
                "art": {
                    "boss.demo": {
                        "path": "generated/boss.png",
                        "width": True,
                        "height": 64,
                        "frames": 1,
                        "pixel_sha256": "a" * 64,
                        "mandatory": True,
                        "provenance": "procedural-vector-v1",
                    }
                },
                "audio": {},
                "font": {
                    "path": "fonts/NotoSansKR.ttf",
                    "license": "fonts/OFL-NotoSansKR.txt",
                    "mandatory": True,
                    "sha256": "c" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ContentError,
        match=r"^assets\.art\.boss\.demo\.width: must be an integer$",
    ):
        load_asset_manifest(tmp_path / "assets.json")


@pytest.mark.parametrize(
    ("object_path", "field_name", "remove", "expected_path", "reason"),
    [
        ((), "unexpected", False, "assets.unexpected", "unknown field"),
        (("art", "boss.demo"), "unexpected", False, "assets.art.boss.demo.unexpected", "unknown field"),
        (("audio", "sfx.boss.demo"), "unexpected", False, "assets.audio.sfx.boss.demo.unexpected", "unknown field"),
        (("font",), "unexpected", False, "assets.font.unexpected", "unknown field"),
        ((), "art", True, "assets.art", "missing field"),
        (("art", "boss.demo"), "path", True, "assets.art.boss.demo.path", "missing field"),
        (("audio", "sfx.boss.demo"), "path", True, "assets.audio.sfx.boss.demo.path", "missing field"),
        (("font",), "path", True, "assets.font.path", "missing field"),
        (("font",), "sha256", True, "assets.font.sha256", "missing field"),
    ],
)
def test_asset_loader_reports_exact_unknown_and_missing_fields(
    tmp_path: Path,
    object_path: tuple[str, ...],
    field_name: str,
    remove: bool,
    expected_path: str,
    reason: str,
) -> None:
    document = _asset_document()
    target = _object_at(document, object_path)
    if remove:
        target.pop(field_name)
    else:
        target[field_name] = True
    (tmp_path / "assets.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ContentError,
        match=rf"^{re.escape(expected_path)}: {re.escape(reason)}$",
    ):
        load_asset_manifest(tmp_path / "assets.json")


@pytest.mark.parametrize(
    ("object_path", "field_name", "value", "expected_path", "reason"),
    [
        (("art", "boss.demo"), "width", 0, "assets.art.boss.demo.width", "must be positive"),
        (("art", "boss.demo"), "frames", -1, "assets.art.boss.demo.frames", "must be positive"),
        (
            ("art", "boss.demo"),
            "pixel_sha256",
            "A" * 64,
            "assets.art.boss.demo.pixel_sha256",
            "must be 64 lowercase hexadecimal characters",
        ),
        (
            ("audio", "sfx.boss.demo"),
            "sha256",
            "short",
            "assets.audio.sfx.boss.demo.sha256",
            "must be 64 lowercase hexadecimal characters",
        ),
        (("font",), "sha256", "f" * 63, "assets.font.sha256", "must be 64 lowercase hexadecimal characters"),
        (
            ("art", "boss.demo"),
            "path",
            "../escape.png",
            "assets.art.boss.demo.path",
            "must be a safe relative POSIX path",
        ),
        (("font",), "license", "C:\\escape.txt", "assets.font.license", "must be a safe relative POSIX path"),
    ],
)
def test_asset_loader_rejects_invalid_release_integrity_fields(
    tmp_path: Path,
    object_path: tuple[str, ...],
    field_name: str,
    value: object,
    expected_path: str,
    reason: str,
) -> None:
    document = _asset_document()
    _object_at(document, object_path)[field_name] = value
    (tmp_path / "assets.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContentError, match=rf"^{re.escape(expected_path)}: {re.escape(reason)}$"):
        load_asset_manifest(tmp_path / "assets.json")


def test_asset_loader_rejects_an_id_that_does_not_start_with_domain_text(tmp_path: Path) -> None:
    document = _asset_document()
    art = _object_at(document, ("art",))
    art["9boss.demo"] = art.pop("boss.demo")
    (tmp_path / "assets.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ContentError,
        match=r"^assets\.art\.9boss\.demo: must be a lowercase dotted stable ID$",
    ):
        load_asset_manifest(tmp_path / "assets.json")


def test_locale_loader_rejects_duplicate_keys_at_the_language_path(tmp_path: Path) -> None:
    (tmp_path / "strings.en.json").write_text('{"title":"One","title":"Two"}', encoding="utf-8")
    (tmp_path / "strings.ko.json").write_text('{"title":"둘"}', encoding="utf-8")

    with pytest.raises(ContentError, match=r"^locales\.en\.title: duplicate field$"):
        load_locales(tmp_path)


def test_locale_loader_rejects_non_string_values_at_the_language_path(tmp_path: Path) -> None:
    (tmp_path / "strings.en.json").write_text('{"title":true}', encoding="utf-8")
    (tmp_path / "strings.ko.json").write_text('{"title":"둘"}', encoding="utf-8")

    with pytest.raises(ContentError, match=r"^locales\.en\.title: must be a non-empty string$"):
        load_locales(tmp_path)
