"""Release assertions for the six authored Windsprig boss encounters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from windsprig.content.loader import load_boss_catalog, load_catalog_bundle

CONTENT_DIR = Path("windsprig/content")
EXPECTED_BOSS_IDS = (
    "rootjaw",
    "crucible_crab",
    "luma_eel",
    "volt_roc",
    "prism_warden",
    "the_stillness",
)


def test_six_bosses_have_three_unique_phase_signatures() -> None:
    """Every world culminates in one mechanically distinct three-phase boss."""

    bosses = load_catalog_bundle(CONTENT_DIR).bosses

    assert tuple(bosses) == EXPECTED_BOSS_IDS
    signatures: set[tuple[tuple[str, tuple[str, ...]], ...]] = set()
    for boss in bosses.values():
        assert len(boss.phases) == 3
        assert [phase.enter_at_hp_ratio for phase in boss.phases] == [1.0, 0.66, 0.33]
        assert all(attack.telegraph_ms >= 600 for phase in boss.phases for attack in phase.attacks)
        assert all(len(phase.attacks) == 2 for phase in boss.phases)
        signatures.add(
            tuple(
                (
                    phase.arena_rule,
                    tuple(attack.attack_id for attack in phase.attacks),
                )
                for phase in boss.phases
            )
        )

    assert len(signatures) == 6


def test_boss_stage_ids_map_one_to_one_to_authored_boss_order() -> None:
    """Campaign boss nodes and the boss catalog share one stable public order."""

    bundle = load_catalog_bundle(CONTENT_DIR)
    stage_bosses = tuple(stage.boss_id for stage in bundle.campaign.stages.values() if stage.boss_id is not None)

    assert stage_bosses == EXPECTED_BOSS_IDS
    assert stage_bosses == tuple(bundle.bosses)


def test_generated_boss_document_retains_authored_order_and_object_parameters() -> None:
    """The checked-in release document stays canonical and schema-correct."""

    payload = json.loads((CONTENT_DIR / "bosses.json").read_text(encoding="utf-8"))

    assert tuple(boss["boss_id"] for boss in payload["bosses"]) == EXPECTED_BOSS_IDS
    assert all(
        isinstance(attack["parameters"], dict)
        for boss in payload["bosses"]
        for phase in boss["phases"]
        for attack in phase["attacks"]
    )


def test_boss_projection_is_strict_immutable_and_authored_ordered() -> None:
    bosses = load_boss_catalog(CONTENT_DIR)

    assert tuple(bosses) == EXPECTED_BOSS_IDS
    with pytest.raises(TypeError):
        bosses["other"] = bosses["rootjaw"]  # type: ignore[index]
    with pytest.raises(TypeError, match="pathlib.Path"):
        load_boss_catalog("windsprig/content")  # type: ignore[arg-type]
