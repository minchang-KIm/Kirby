"""Deterministic whole-catalog semantic validation contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pytest

from tests.helpers.catalog import minimal_documents, write_minimal_bundle, write_release_bundle
from windsprig.content.loader import load_asset_manifest, load_catalog_bundle, load_locales
from windsprig.content.models import (
    ArtAssetSpec,
    AssetManifest,
    AudioAssetSpec,
    FontAssetSpec,
    LocaleCatalog,
    ValidationIssue,
)
from windsprig.content.validator import validate_bundle


def _context() -> tuple[AssetManifest, LocaleCatalog]:
    return (
        AssetManifest(
            art={},
            audio={},
            font=FontAssetSpec(
                path="fonts/NotoSansKR.ttf",
                license="fonts/OFL-NotoSansKR.txt",
                mandatory=True,
                sha256="f" * 64,
            ),
        ),
        LocaleCatalog(
            {
                "en": {
                    "world.demo.name": "Demo",
                    "world.demo.identity": "A proving ground",
                    "mechanic.gust": "Gust lifts",
                    "stage.demo_01.name": "Demo",
                    "stage.demo_01.intro": "Begin",
                    "boss.demo.name": "Demo Boss",
                    "reward.gallery.demo": "Demo Gallery",
                },
                "ko": {
                    "world.demo.name": "데모",
                    "world.demo.identity": "시험장",
                    "mechanic.gust": "돌풍 상승",
                    "stage.demo_01.name": "데모",
                    "stage.demo_01.intro": "시작",
                    "boss.demo.name": "데모 보스",
                    "reward.gallery.demo": "데모 갤러리",
                },
            }
        ),
    )


def _selected(report_codes: tuple[str, ...], report: object) -> list[tuple[str, str]]:
    errors = report.errors  # type: ignore[attr-defined]
    return [(issue.code, issue.path) for issue in errors if issue.code in report_codes]


def _first_stage_document(documents: dict[str, dict[str, object]]) -> dict[str, object]:
    stages = cast(list[object], documents["campaign"]["stages"])
    return cast(dict[str, object], stages[0])


def test_validator_orders_duplicate_identity_navigation_and_layout_categories(
    tmp_path: Path,
) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    stage = bundle.campaign.stages["demo_01"]
    second_navigation = replace(
        stage.navigation,
        edges=tuple(edge for edge in stage.navigation.edges if edge[1] != "goal"),
    )
    second = replace(
        stage,
        stage_id="demo_02",
        node_id="demo_node_2",
        motes=(
            stage.motes[0],
            replace(stage.motes[1], mote_id="demo_02:mote:2"),
            replace(stage.motes[2], mote_id="demo_02:mote:3"),
        ),
        navigation=second_navigation,
    )
    first_node = bundle.campaign.worlds["demo"][0]
    second_node = replace(
        first_node,
        node_id="demo_node_2",
        stage_id="demo_02",
        requires=(first_node.node_id,),
        is_boss=False,
    )
    campaign = replace(
        bundle.campaign,
        worlds={"demo": (first_node, second_node)},
        stages={"demo_01": stage, "demo_02": second},
        nodes={},
    )
    bundle = replace(bundle, campaign=campaign)
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert _selected(("duplicate_mote_id", "unreachable_goal", "duplicate_layout"), report) == [
        ("duplicate_mote_id", "campaign.stages.demo_02.motes[0]"),
        ("unreachable_goal", "campaign.stages.demo_02.navigation.goal"),
        ("duplicate_layout", "campaign.stages.demo_02"),
    ]


def test_navigation_reports_missing_edge_nodes_and_disconnected_targets(
    tmp_path: Path,
) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    stage = bundle.campaign.stages["demo_01"]
    navigation = replace(stage.navigation, edges=(("start", "missing"),))
    disconnected_checkpoint = replace(stage.checkpoints[0], tile_x=3, tile_y=4)
    stage = replace(
        stage,
        navigation=navigation,
        checkpoints=(disconnected_checkpoint,),
    )
    bundle = replace(
        bundle,
        campaign=replace(bundle.campaign, stages={stage.stage_id: stage}),
    )
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert _selected(
        (
            "missing_navigation_node",
            "unreachable_checkpoint",
            "unreachable_goal",
            "unreachable_mote",
        ),
        report,
    ) == [
        ("unreachable_checkpoint", "campaign.stages.demo_01.checkpoints[0]"),
        ("unreachable_mote", "campaign.stages.demo_01.motes[0]"),
        ("unreachable_mote", "campaign.stages.demo_01.motes[1]"),
        ("unreachable_mote", "campaign.stages.demo_01.motes[2]"),
        ("missing_navigation_node", "campaign.stages.demo_01.navigation.edges[0][1]"),
        ("unreachable_goal", "campaign.stages.demo_01.navigation.goal"),
    ]


def test_validator_rejects_duplicate_checkpoint_geometry(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    stage = bundle.campaign.stages["demo_01"]
    first = stage.checkpoints[0]
    duplicate_geometry = replace(
        first,
        checkpoint_id=f"{first.checkpoint_id}.duplicate-geometry",
    )
    stage = replace(
        stage,
        checkpoints=(first, duplicate_geometry),
    )
    bundle = replace(
        bundle,
        campaign=replace(bundle.campaign, stages={stage.stage_id: stage}),
    )
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert _selected(("duplicate_checkpoint_geometry",), report) == [
        (
            "duplicate_checkpoint_geometry",
            "campaign.stages.demo_01.checkpoints[1]",
        )
    ]


def test_validator_checks_ground_row_against_stage_bounds(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    stage = bundle.campaign.stages["demo_01"]
    stage = replace(stage, ground_y_tile=stage.height_tiles)
    bundle = replace(
        bundle,
        campaign=replace(bundle.campaign, stages={stage.stage_id: stage}),
    )
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert _selected(("out_of_bounds",), report) == [("out_of_bounds", "campaign.stages.demo_01.ground_y_tile")]


def test_validator_rejects_stage_without_a_player_spawn(tmp_path: Path) -> None:
    documents = minimal_documents()
    _first_stage_document(documents)["player_spawns"] = []
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path, documents))
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert bundle.campaign.stages["demo_01"].player_spawns == ()
    assert _selected(("missing_player_spawn",), report) == [
        ("missing_player_spawn", "campaign.stages.demo_01.player_spawns")
    ]


@pytest.mark.parametrize(
    ("patrol_left", "patrol_right", "code", "path"),
    [
        (-1.0, 224.0, "out_of_bounds", "campaign.stages.demo_01.enemy_spawns[0].patrol_left"),
        (160.0, 384.0, "out_of_bounds", "campaign.stages.demo_01.enemy_spawns[0].patrol_right"),
        (225.0, 224.0, "invalid_patrol_range", "campaign.stages.demo_01.enemy_spawns[0]"),
    ],
)
def test_validator_rejects_unordered_or_out_of_bounds_enemy_patrol(
    tmp_path: Path,
    patrol_left: float,
    patrol_right: float,
    code: str,
    path: str,
) -> None:
    documents = minimal_documents()
    stage = _first_stage_document(documents)
    enemies = cast(list[object], stage["enemy_spawns"])
    enemy = cast(dict[str, object], enemies[0])
    enemy["patrol_left"] = patrol_left
    enemy["patrol_right"] = patrol_right
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path, documents))
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    loaded = bundle.campaign.stages["demo_01"].enemy_spawns[0]
    assert (loaded.patrol_left, loaded.patrol_right) == (patrol_left, patrol_right)
    assert _selected((code,), report) == [(code, path)]


def test_validator_binds_reachable_navigation_goal_to_gameplay_goal_tile(tmp_path: Path) -> None:
    documents = minimal_documents()
    stage = _first_stage_document(documents)
    navigation = cast(dict[str, object], stage["navigation"])
    nodes = cast(list[object], navigation["nodes"])
    goal = next(cast(dict[str, object], node) for node in nodes if cast(dict[str, object], node)["nav_id"] == "goal")
    goal["tile_x"] = 2
    goal["tile_y"] = 2
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path, documents))
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert _selected(("navigation_goal_mismatch",), report) == [
        ("navigation_goal_mismatch", "campaign.stages.demo_01.navigation.goal")
    ]


def test_validation_order_is_independent_of_mapping_insertion_order(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    assets, locales = _context()
    reversed_campaign = replace(
        bundle.campaign,
        worlds=dict(reversed(tuple(bundle.campaign.worlds.items()))),
        stages=dict(reversed(tuple(bundle.campaign.stages.items()))),
        nodes={},
    )

    assert validate_bundle(bundle, assets, locales) == validate_bundle(
        replace(bundle, campaign=reversed_campaign), assets, locales
    )


def test_validation_issues_reports_and_counts_are_deeply_frozen(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert isinstance(report.errors, tuple)
    assert report.counts["stages"] == 1
    with pytest.raises(TypeError):
        report.counts["stages"] = 30  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        report.errors[0].message = "changed"  # type: ignore[misc]
    assert isinstance(report.errors[0], ValidationIssue)


def test_complete_release_fixture_has_no_validation_issues(tmp_path: Path) -> None:
    content, asset_root = write_release_bundle(tmp_path)

    report = validate_bundle(
        load_catalog_bundle(content),
        load_asset_manifest(content / "assets.json"),
        load_locales(content),
        asset_root=asset_root,
    )

    assert report.errors == ()
    assert report.warnings == ()
    assert dict(report.counts) == {
        "bosses": 6,
        "duplicate_layouts": 0,
        "locales": 2,
        "motes": 90,
        "music": 28,
        "sfx": 29,
        "stages": 30,
        "worlds": 6,
    }


def test_validator_reports_reference_reward_and_locale_contracts(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    node = replace(bundle.campaign.worlds["demo"][0], stage_id="missing")
    campaign = replace(bundle.campaign, worlds={"demo": (node,)}, nodes={})
    rewards = replace(
        bundle.rewards,
        mote_thresholds=(
            replace(bundle.rewards.mote_thresholds[0], threshold=6),
            replace(
                bundle.rewards.mote_thresholds[0],
                threshold=3,
                reward_id="gallery.other",
            ),
        ),
    )
    bundle = replace(bundle, campaign=campaign, rewards=rewards)
    assets, locales = _context()
    locales = LocaleCatalog(
        {
            "en": {**locales.strings["en"], "formatted": "Found {count}"},
            "ko": {**locales.strings["ko"], "formatted": "발견 {total}"},
        }
    )

    report = validate_bundle(bundle, assets, locales)

    selected = _selected(
        ("missing_stage", "reward_threshold_order", "locale_placeholder_mismatch"),
        report,
    )
    assert selected == [
        ("missing_stage", "campaign.worlds.demo.nodes.demo_node_1.stage_id"),
        ("reward_threshold_order", "rewards.mote_thresholds[1].threshold"),
        ("locale_placeholder_mismatch", "locales.ko.formatted"),
    ]


def test_validator_preserves_anonymous_placeholder_multiplicity(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    assets, locales = _context()
    locales = LocaleCatalog(
        {
            "en": {**locales.strings["en"], "formatted": "Found {} and {}"},
            "ko": {**locales.strings["ko"], "formatted": "발견 {}"},
        }
    )

    report = validate_bundle(bundle, assets, locales)

    assert _selected(("locale_placeholder_mismatch",), report) == [
        ("locale_placeholder_mismatch", "locales.ko.formatted")
    ]


def test_validator_requires_world_presentation_locale_keys(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    assets, locales = _context()
    locales = LocaleCatalog(
        {
            language: {key: text for key, text in table.items() if key != "world.demo.name"}
            for language, table in locales.strings.items()
        }
    )

    report = validate_bundle(bundle, assets, locales)

    assert _selected(("missing_locale_key",), report) == [("missing_locale_key", "locales.en.world.demo.name")]


def test_validator_reports_boss_phase_ratio_and_attack_timing_contracts(
    tmp_path: Path,
) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    boss = bundle.bosses["demo_boss"]
    first_phase = boss.phases[0]
    attack = replace(first_phase.attacks[0], telegraph_ms=0, active_ms=-1)
    invalid_phase = replace(
        first_phase,
        phase_id="demo_boss.p2",
        enter_at_hp_ratio=1.1,
        attacks=(attack,),
    )
    bundle = replace(
        bundle,
        bosses={boss.boss_id: replace(boss, max_hp=0, phases=(first_phase, invalid_phase))},
    )
    assets, locales = _context()

    report = validate_bundle(bundle, assets, locales)

    assert _selected(
        ("invalid_boss_hp", "invalid_phase_order", "invalid_phase_ratio", "invalid_attack_timing"),
        report,
    ) == [
        ("invalid_boss_hp", "bosses.demo_boss.max_hp"),
        ("invalid_attack_timing", "bosses.demo_boss.phases[1].attacks[0].active_ms"),
        ("invalid_attack_timing", "bosses.demo_boss.phases[1].attacks[0].telegraph_ms"),
        ("invalid_phase_order", "bosses.demo_boss.phases[1].enter_at_hp_ratio"),
        ("invalid_phase_ratio", "bosses.demo_boss.phases[1].enter_at_hp_ratio"),
    ]


def test_validator_reports_safe_missing_and_provenance_asset_paths(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path / "content"))
    asset_root = tmp_path / "assets"
    (asset_root / "audio").mkdir(parents=True)
    (asset_root / "fonts").mkdir()
    (asset_root / "records").mkdir()
    (asset_root / "audio" / "boss.wav").write_bytes(b"audio")
    (asset_root / "fonts" / "NotoSansKR.ttf").write_bytes(b"font")
    (asset_root / "records" / "art.json").write_text("{}", encoding="utf-8")
    assets = AssetManifest(
        art={
            "boss.demo": ArtAssetSpec(
                path="art/missing.png",
                width=64,
                height=64,
                frames=1,
                pixel_sha256="a" * 64,
                mandatory=True,
                provenance="procedural-vector-v1",
            ),
            "unsafe": ArtAssetSpec(
                path="../escape.png",
                width=1,
                height=1,
                frames=1,
                pixel_sha256="b" * 64,
                mandatory=False,
                provenance="procedural-vector-v1",
            ),
        },
        audio={
            "sfx.boss.demo": AudioAssetSpec(
                path="audio/boss.wav",
                bus="sfx",
                mandatory=True,
                sha256="c" * 64,
            )
        },
        font=FontAssetSpec(
            path="fonts/NotoSansKR.ttf",
            license="fonts/missing-license.txt",
            mandatory=True,
            sha256="f" * 64,
        ),
        provenance_files=("records/art.json", "records/missing.json"),
    )
    _, locales = _context()

    report = validate_bundle(bundle, assets, locales, asset_root=asset_root)

    assert _selected(
        ("missing_asset_file", "unsafe_asset_path", "missing_font_license", "missing_provenance"),
        report,
    ) == [
        ("missing_asset_file", "assets.art.boss.demo.path"),
        ("unsafe_asset_path", "assets.art.unsafe.path"),
        ("missing_font_license", "assets.font.license"),
        ("missing_provenance", "assets.provenance_files[1]"),
    ]


def test_validator_reports_exact_art_inventory_frames_and_mandatory_flags(tmp_path: Path) -> None:
    content, asset_root = write_release_bundle(tmp_path)
    bundle = load_catalog_bundle(content)
    locales = load_locales(content)
    loaded = load_asset_manifest(content / "assets.json")
    art = dict(loaded.art)
    art.pop("player.sprig")
    enemy_id = next(asset_id for asset_id in art if asset_id.startswith("enemy."))
    boss_id = next(asset_id for asset_id in art if asset_id.startswith("boss."))
    art[enemy_id] = replace(art[enemy_id], mandatory=False)
    art[boss_id] = replace(art[boss_id], frames=17)
    assets = replace(loaded, art=art)

    report = validate_bundle(bundle, assets, locales, asset_root=asset_root)

    assert _selected(
        ("art_inventory_count", "missing_asset_id", "art_not_mandatory", "invalid_art_frames"),
        report,
    ) == [
        ("art_inventory_count", "assets.art"),
        ("invalid_art_frames", f"assets.art.{boss_id}.frames"),
        ("art_not_mandatory", f"assets.art.{enemy_id}.mandatory"),
        ("missing_asset_id", "assets.art.player.sprig"),
    ]


def test_validator_rejects_substituted_art_ids_even_when_category_counts_match(tmp_path: Path) -> None:
    content, asset_root = write_release_bundle(tmp_path)
    bundle = load_catalog_bundle(content)
    locales = load_locales(content)
    loaded = load_asset_manifest(content / "assets.json")
    art = dict(loaded.art)
    art["ui.surprise"] = art.pop("ui.favicon")

    report = validate_bundle(bundle, replace(loaded, art=art), locales, asset_root=asset_root)

    assert _selected(("missing_asset_id", "unexpected_asset_id"), report) == [
        ("missing_asset_id", "assets.art.ui.favicon"),
        ("unexpected_asset_id", "assets.art.ui.surprise"),
    ]


def test_validator_rejects_audio_aliases_wrong_buses_and_nonmandatory_cues_at_the_exact_count(
    tmp_path: Path,
) -> None:
    content, asset_root = write_release_bundle(tmp_path)
    bundle = load_catalog_bundle(content)
    locales = load_locales(content)
    loaded = load_asset_manifest(content / "assets.json")
    audio = dict(loaded.audio)
    audio["music.alias"] = audio.pop("music.title")
    audio["sfx.damage"] = replace(audio["sfx.damage"], bus="music", mandatory=False)

    report = validate_bundle(bundle, replace(loaded, audio=audio), locales, asset_root=asset_root)

    assert report.counts["music"] == 29
    assert report.counts["sfx"] == 28
    assert _selected(
        ("missing_audio_cue", "unexpected_audio_cue", "audio_bus_mismatch", "audio_not_mandatory"),
        report,
    ) == [
        ("unexpected_audio_cue", "assets.audio.music.alias"),
        ("missing_audio_cue", "assets.audio.music.title"),
        ("audio_bus_mismatch", "assets.audio.sfx.damage.bus"),
        ("audio_not_mandatory", "assets.audio.sfx.damage.mandatory"),
    ]
