"""Immutable localized HUD adapter contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from windsprig.content import load_catalog_bundle
from windsprig.content.models import StageSpec
from windsprig.gameplay.snapshot import (
    BossView,
    CameraTargetView,
    GoalGatherView,
    PlayerView,
    StageOutcome,
    StageSnapshot,
)
from windsprig.input.roster import SLOT_VISUALS, ActivePlayer, DeviceRef
from windsprig.localization import Localizer
from windsprig.platform.services import AudioStatus
from windsprig.render.camera import CameraView
from windsprig.render.hud import HudBossVM, build_hud_view

ROOT = Path(__file__).resolve().parents[3]
CONTENT = ROOT / "windsprig/content"


def _active_player(slot: int) -> ActivePlayer:
    color, icon = SLOT_VISUALS[slot]
    return ActivePlayer(
        slot=slot,
        device=DeviceRef("keyboard", f"hud-kb-{slot}", f"HUD Keyboard {slot}"),
        color_token=color,
        icon_token=icon,
        is_leader=slot == 1,
    )


def _player(slot: int) -> PlayerView:
    ability_ids = ("bloomblade", "cinder", "voltsong", "galehook")
    return PlayerView(
        entity_id=100 + slot,
        slot=slot,
        x=120.0 + slot * 50,
        y=500.0,
        width=42,
        height=58,
        facing=1,
        actor_state="Idle",
        hp=5 - slot,
        maximum_hp=5,
        lives_remaining=4 - slot,
        ability_id=ability_ids[slot - 1],
        ability_meter=slot * 20,
        ability_charge_ms=0,
        guard_active=slot == 2,
        dodge_active=slot == 3,
        invulnerable=slot == 4,
        hover_remaining_ms=850 - slot * 100,
        hover_max_ms=850,
        captured_ability_id="cinder" if slot == 1 else None,
        captured_visual_id="cinderling" if slot == 1 else None,
    )


def _snapshot(
    stage: StageSpec,
    players: tuple[PlayerView, ...],
    *,
    boss: BossView | None = None,
) -> StageSnapshot:
    required = tuple(sorted(player.slot for player in players))
    return StageSnapshot(
        frame_index=99,
        elapsed_ms=16_000,
        stage_id=stage.stage_id,
        world_id=stage.world_id,
        node_id=stage.node_id,
        outcome=StageOutcome.RUNNING,
        players=players,
        enemies=(),
        attacks=(),
        echo_pickups=(),
        interactions=(),
        checkpoints=(),
        goal_gather=GoalGatherView(
            goal_x=stage.goal_tile[0] * stage.tile_size,
            goal_y=stage.goal_tile[1] * stage.tile_size,
            at_goal_slots=required[:2],
            required_slots=required,
            leader_slot=1,
            leader_confirmed=True,
            countdown_remaining_ms=1_900,
        ),
        camera_targets=tuple(
            CameraTargetView(player.entity_id, player.slot, player.x, player.y, 1.0, True) for player in players
        ),
        bosses=() if boss is None else (boss,),
        collected_mote_ids=(stage.motes[0].mote_id, stage.motes[2].mote_id),
    )


def test_hud_builds_four_canonical_redundant_player_panels() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    players = tuple(_player(slot) for slot in range(4, 0, -1))
    active = tuple(_active_player(slot) for slot in range(4, 0, -1))

    hud = build_hud_view(
        _snapshot(stage, players),
        stage,
        active,
        CameraView(0, 0, 0, 0, 0, (4,)),
        AudioStatus(ready=True, muted=False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )

    assert tuple(player.slot for player in hud.players) == (1, 2, 3, 4)
    assert tuple(player.label for player in hud.players) == ("1", "2", "3", "4")
    assert tuple(player.pattern_token for player in hud.players) == (
        "pattern.slot-1",
        "pattern.slot-2",
        "pattern.slot-3",
        "pattern.slot-4",
    )
    assert len({(player.icon_token, player.color_token, player.pattern_token) for player in hud.players}) == 4
    assert hud.players[0].hp_segments == (True, True, True, True, False)
    assert hud.players[0].captured_icon == "cinder"
    assert hud.players[2].dodge_active is True
    assert hud.players[2].status_labels == ()
    assert hud.mote_icons == (True, False, True)
    assert hud.catch_up_slots == (4,)


def test_korean_hud_localizes_gather_boss_audio_save_and_player_facts() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_5"]
    player = _player(1)
    boss = BossView(
        entity_id=800,
        boss_id="rootjaw",
        phase_id="rootjaw.tangled_fury",
        x=700.0,
        y=420.0,
        width=128,
        height=128,
        facing=-1,
        actor_state="Attack",
        hp=61,
        maximum_hp=120,
        telegraph_id="rootjaw.bramble_sweep",
        telegraph_remaining_ms=350,
        vulnerability_state="vulnerable",
    )

    hud = build_hud_view(
        _snapshot(stage, (player,), boss=boss),
        stage,
        (_active_player(1),),
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(ready=False, muted=True, error_code="audio_init_failed"),
        "retry_required",
        Localizer.load(CONTENT, "ko"),
    )

    assert hud.players[0].hp_label == "체력 4/5"
    assert hud.players[0].lives_label == "목숨 3"
    assert hud.players[0].ability_label == "꽃날"
    assert hud.players[0].captured_label == "보유 메아리: 불씨"
    assert hud.gather_label == "집결 2"
    assert hud.boss is not None
    assert (hud.boss.name, hud.boss.phase_label) == ("뿌리턱", "단계 2/3")
    assert hud.boss.vulnerability_pattern == "pattern.boss.vulnerable"
    assert (hud.boss.telegraph_icon, hud.boss.telegraph_label, hud.boss.telegraph_pattern) == (
        "attack",
        "준비 중",
        "stripes",
    )
    assert hud.muted_indicator is True
    assert hud.muted_label == "오디오를 사용할 수 없어 음소거됨"
    assert hud.save_status_key == "save.failed"
    assert hud.save_status_label == "저장 실패 — 다시 시도"


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Held echo: Moonjelly"), ("ko", "보유 메아리: 달해파리")],
)
def test_abilityless_capture_uses_the_localized_enemy_name(language: str, expected: str) -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_3_stage_1"]
    player = replace(
        _player(1),
        captured_ability_id=None,
        captured_visual_id="moonjelly",
    )

    hud = build_hud_view(
        _snapshot(stage, (player,)),
        stage,
        (_active_player(1),),
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, language),  # type: ignore[arg-type]
    )

    assert hud.players[0].captured_label == expected


def test_boss_telegraph_adds_redundant_localized_icon_text_and_pattern_state() -> None:
    bundle = load_catalog_bundle(CONTENT)
    stage = bundle.campaign.stages["world_1_stage_5"]
    spec = bundle.bosses["rootjaw"]
    base = BossView(
        800,
        "rootjaw",
        spec.phases[0].phase_id,
        700,
        420,
        128,
        128,
        -1,
        "Idle",
        100,
        spec.max_hp,
        None,
        0,
        spec.phases[0].vulnerability,
    )
    common = (
        stage,
        (_active_player(1),),
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )

    idle = build_hud_view(_snapshot(stage, (_player(1),), boss=base), *common).boss
    warning = build_hud_view(
        _snapshot(
            stage,
            (_player(1),),
            boss=replace(base, telegraph_id=spec.phases[0].attacks[0].attack_id, telegraph_remaining_ms=400),
        ),
        *common,
    ).boss

    assert idle is not None and warning is not None
    assert idle.vulnerability_pattern == warning.vulnerability_pattern
    assert idle.phase_label == warning.phase_label
    assert (idle.telegraph_icon, idle.telegraph_label, idle.telegraph_pattern) == (None, None, None)
    assert (warning.telegraph_icon, warning.telegraph_label, warning.telegraph_pattern) == (
        "attack",
        "Incoming attack",
        "stripes",
    )


def test_catch_up_cues_point_inward_and_clamp_vertical_edge_positions() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    players = (_player(1), _player(2))
    snapshot = replace(
        _snapshot(stage, players),
        camera_targets=(
            CameraTargetView(players[0].entity_id, 1, 0.0, -2_000.0, 1.0, True),
            CameraTargetView(players[1].entity_id, 2, 1_200.0, 3_000.0, 1.0, True),
        ),
    )
    hud = build_hud_view(
        snapshot,
        stage,
        (_active_player(1), _active_player(2)),
        CameraView(0, 0, 0, 0, 0, (1, 2)),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )

    assert tuple((cue.slot, cue.edge, cue.arrow, cue.edge_y) for cue in hud.catch_up_cues) == (
        (1, "left", "->", 150),
        (2, "right", "<-", 600),
    )
    assert all(32 <= ord(character) <= 126 for cue in hud.catch_up_cues for character in cue.arrow)


def test_catch_up_cues_separate_three_players_at_the_same_canvas_edge() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    players = tuple(_player(slot) for slot in range(1, 5))
    snapshot = replace(
        _snapshot(stage, players),
        camera_targets=(
            CameraTargetView(players[0].entity_id, 1, 0.0, 3_000.0, 1.0, True),
            CameraTargetView(players[1].entity_id, 2, 20.0, 3_000.0, 1.0, True),
            CameraTargetView(players[2].entity_id, 3, 40.0, 3_000.0, 1.0, True),
            CameraTargetView(players[3].entity_id, 4, 1_200.0, 3_000.0, 10.0, True),
        ),
    )

    hud = build_hud_view(
        snapshot,
        stage,
        tuple(_active_player(slot) for slot in range(1, 5)),
        CameraView(0, 0, 0, 0, 0, (1, 2, 3)),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )

    assert tuple(cue.edge_y for cue in hud.catch_up_cues) == (600, 546, 492)


def test_hud_is_deeply_immutable_and_does_not_mutate_snapshot_or_inputs() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage, (_player(1),))
    before = snapshot
    active = (_active_player(1),)

    hud = build_hud_view(
        snapshot,
        stage,
        active,
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(ready=True, muted=False),
        "ready",
        Localizer.load(CONTENT, "en"),
    )

    assert snapshot == before
    assert isinstance(hud.players[0].status_labels, tuple)
    with pytest.raises(FrozenInstanceError):
        hud.players[0].label = "changed"  # type: ignore[misc]


def test_hud_rejects_noncanonical_stage_motes_and_cross_stage_collection() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    malformed_stage = replace(
        stage,
        motes=(replace(stage.motes[0], mote_id="wrong:mote:1"), *stage.motes[1:]),
    )
    snapshot = _snapshot(stage, (_player(1),))
    common = (
        (_active_player(1),),
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(ready=True, muted=False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )

    with pytest.raises(ValueError, match="stable mote"):
        build_hud_view(replace(snapshot, stage_id=malformed_stage.stage_id), malformed_stage, *common)
    with pytest.raises(ValueError, match="collected mote"):
        build_hud_view(
            replace(snapshot, collected_mote_ids=("world_2_stage_1:mote:1",)),
            stage,
            *common,
        )


@pytest.mark.parametrize("save_status", ["", "unknown", True])
def test_hud_rejects_unsupported_save_status_tokens(save_status: object) -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]

    with pytest.raises((TypeError, ValueError), match="save status"):
        build_hud_view(
            _snapshot(stage, (_player(1),)),
            stage,
            (_active_player(1),),
            CameraView(0, 0, 0, 0, 0, ()),
            AudioStatus(ready=True, muted=False),
            save_status,  # type: ignore[arg-type]
            Localizer.load(CONTENT, "en"),
        )


def test_hud_rejects_duplicate_or_mismatched_active_slots() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage, (_player(1), _player(2)))
    common = (
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(ready=True, muted=False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )

    with pytest.raises(ValueError, match="active player slots"):
        build_hud_view(snapshot, stage, (_active_player(1), _active_player(1)), *common)
    with pytest.raises(ValueError, match="snapshot player slots"):
        build_hud_view(snapshot, stage, (_active_player(1),), *common)


def test_hud_value_models_reject_malformed_nested_values() -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage, (_player(1),))
    hud = build_hud_view(
        snapshot,
        stage,
        (_active_player(1),),
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, "en"),
    )
    player = hud.players[0]
    invalid_players = (
        (lambda: replace(player, slot=5), ValueError),
        (lambda: replace(player, label=True), TypeError),  # type: ignore[arg-type]
        (lambda: replace(player, label=""), ValueError),
        (lambda: replace(player, hp_segments=()), ValueError),
        (lambda: replace(player, hp_segments=(1,)), TypeError),  # type: ignore[arg-type]
        (lambda: replace(player, ability_meter_ratio=float("inf")), ValueError),
        (lambda: replace(player, guard_active=1), TypeError),  # type: ignore[arg-type]
        (lambda: replace(player, status_labels=[]), TypeError),  # type: ignore[arg-type]
    )
    for factory, exception in invalid_players:
        with pytest.raises(exception):
            factory()

    with pytest.raises(ValueError, match="telegraph icon"):
        HudBossVM("Boss", "Phase", 0.5, "pattern.boss.vulnerable", "")
    with pytest.raises(TypeError, match="HUD players"):
        replace(hud, players=[player])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="one through four"):
        replace(hud, players=())
    with pytest.raises(ValueError, match="canonical slot"):
        replace(hud, players=(player, player))
    with pytest.raises(ValueError, match="exactly three"):
        replace(hud, mote_icons=(True, False))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="mote icons"):
        replace(hud, mote_icons=(True, False, 1))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="catch-up slots"):
        replace(hud, catch_up_slots=[1])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="canonical order"):
        replace(hud, catch_up_slots=(1, 1))
    with pytest.raises(ValueError, match="visible players"):
        replace(hud, catch_up_slots=(2,))
    with pytest.raises(TypeError, match="HUD boss"):
        replace(hud, boss=object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"entity_id": True}, "entity ID"),
        ({"slot": 5}, "snapshot player slot"),
        ({"hp": 6}, "cannot exceed"),
        ({"ability_meter": 101}, "ability meter"),
        ({"hover_remaining_ms": 851}, "remaining hover"),
        ({"ability_id": "unknown"}, "ability ID"),
        ({"captured_ability_id": "unknown"}, "captured ability"),
        ({"captured_visual_id": ""}, "captured visual"),
        ({"invulnerable": 1}, "boolean"),
    ],
)
def test_hud_rejects_invalid_snapshot_player_facts(changes: dict[str, object], message: str) -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    player = replace(_player(1), **changes)

    with pytest.raises((TypeError, ValueError), match=message):
        build_hud_view(
            _snapshot(stage, (player,)),
            stage,
            (_active_player(1),),
            CameraView(0, 0, 0, 0, 0, ()),
            AudioStatus(True, False),
            "saved",
            Localizer.load(CONTENT, "en"),
        )


def test_hud_validates_active_goal_boss_and_public_boundary_inputs() -> None:
    bundle = load_catalog_bundle(CONTENT)
    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage, (_player(1),))
    camera = CameraView(0, 0, 0, 0, 0, ())
    audio = AudioStatus(True, False)
    tr = Localizer.load(CONTENT, "en")

    with pytest.raises(TypeError, match="active players"):
        build_hud_view(snapshot, stage, object(), camera, audio, "saved", tr)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must not be empty"):
        build_hud_view(snapshot, stage, (), camera, audio, "saved", tr)
    with pytest.raises(TypeError, match="ActivePlayer"):
        build_hud_view(snapshot, stage, (object(),), camera, audio, "saved", tr)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="leader state"):
        active = replace(_active_player(1), is_leader=1)  # type: ignore[arg-type]
        build_hud_view(snapshot, stage, (active,), camera, audio, "saved", tr)

    invalid_gathers = (
        replace(snapshot.goal_gather, required_slots=(1, 1)),
        replace(snapshot.goal_gather, required_slots=(2,)),
        replace(snapshot.goal_gather, at_goal_slots=(1, 1)),
        replace(snapshot.goal_gather, at_goal_slots=(2,)),
        replace(snapshot.goal_gather, leader_slot=2),
        replace(snapshot.goal_gather, leader_confirmed=1),  # type: ignore[arg-type]
    )
    for gather in invalid_gathers:
        with pytest.raises((TypeError, ValueError), match="goal"):
            build_hud_view(
                replace(snapshot, goal_gather=gather), stage, (_active_player(1),), camera, audio, "saved", tr
            )

    boss_stage = bundle.campaign.stages["world_1_stage_5"]
    boss_spec = bundle.bosses["rootjaw"]
    base_boss = BossView(
        800,
        "rootjaw",
        boss_spec.phases[0].phase_id,
        700,
        420,
        128,
        128,
        -1,
        "Idle",
        100,
        boss_spec.max_hp,
        None,
        0,
        boss_spec.phases[0].vulnerability,
    )
    invalid_bosses = (
        replace(base_boss, boss_id="crucible_crab"),
        replace(base_boss, hp=boss_spec.max_hp + 1),
        replace(base_boss, phase_id="rootjaw.unknown"),
        replace(base_boss, vulnerability_state="unknown"),  # type: ignore[arg-type]
        replace(base_boss, telegraph_remaining_ms=-1),
        replace(base_boss, telegraph_id=""),
    )
    for boss in invalid_bosses:
        boss_snapshot = _snapshot(boss_stage, (_player(1),), boss=boss)
        with pytest.raises((TypeError, ValueError)):
            build_hud_view(
                boss_snapshot,
                boss_stage,
                (_active_player(1),),
                camera,
                audio,
                "saved",
                tr,
            )

    with pytest.raises(TypeError, match="snapshot boss"):
        build_hud_view(
            replace(_snapshot(boss_stage, (_player(1),)), bosses=(object(),)),  # type: ignore[arg-type]
            boss_stage,
            (_active_player(1),),
            camera,
            audio,
            "saved",
            tr,
        )


@pytest.mark.parametrize("argument", ["snapshot", "stage", "camera", "audio", "localizer"])
def test_hud_rejects_wrong_public_boundary_types(argument: str) -> None:
    stage = load_catalog_bundle(CONTENT).campaign.stages["world_1_stage_1"]
    values: list[object] = [
        _snapshot(stage, (_player(1),)),
        stage,
        (_active_player(1),),
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, "en"),
    ]
    index = {"snapshot": 0, "stage": 1, "camera": 3, "audio": 4, "localizer": 6}[argument]
    values[index] = object()

    with pytest.raises(TypeError):
        build_hud_view(*values)  # type: ignore[arg-type]
