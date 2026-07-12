"""Deterministic whole-catalog semantic validation contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tests.helpers.catalog import write_minimal_bundle
from windsprig.content.loader import load_catalog_bundle
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
