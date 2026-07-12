"""Semantic cue allowlisting and phase-aware music direction contracts."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from tests.helpers.audio import FakeAudioService
from windsprig.audio.catalog import (
    ABILITY_IDS,
    BOSS_PHASES,
    MUSIC_CUE_IDS,
    SFX_CUE_IDS,
)
from windsprig.audio.cues import cue_for_event
from windsprig.audio.music import MusicDirector
from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AudioSettings


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("PlayerDamaged", "sfx.damage"),
        ("PlayerDodged", "sfx.dodge"),
        ("EnemyCaptured", "sfx.draw.start"),
        ("CaptureReleased", "sfx.draw.release"),
        ("EnemyLaunched", "sfx.enemy.launch"),
        ("HarmonizeUnavailable", "sfx.ui.cancel"),
        ("AbilityEquipped", "sfx.harmonize"),
        ("AbilityDropped", "sfx.draw.release"),
        ("AttackHit", "sfx.damage"),
        ("ProjectileCut", "sfx.guard"),
        ("EnemyDefeated", "sfx.damage"),
        ("MoteCollected", "sfx.mote"),
        ("CheckpointReached", "sfx.checkpoint"),
        ("GatherCompleted", "sfx.goal"),
        ("PlayerDefeated", "sfx.defeat"),
        ("PlayerRespawned", "sfx.checkpoint"),
        ("StageCompleted", "sfx.victory"),
        ("StageFailed", "sfx.defeat"),
    ],
)
def test_static_semantic_topics_map_only_to_manifested_cues(topic: str, expected: str) -> None:
    cue = cue_for_event(GameEvent(topic, {"untrusted": "ignored"}))

    assert cue == expected
    assert cue in SFX_CUE_IDS


@pytest.mark.parametrize("topic", ["AbilityUsed", "AttackSpawned"])
@pytest.mark.parametrize("ability_id", sorted(ABILITY_IDS))
def test_ability_events_select_only_the_six_exact_ability_cues(topic: str, ability_id: str) -> None:
    assert cue_for_event(GameEvent(topic, {"ability_id": ability_id})) == f"sfx.ability.{ability_id}"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ability_id": ""},
        {"ability_id": "../damage"},
        {"ability_id": "bloomblade.extra"},
        {"ability_id": True},
        {"ability_id": float("nan")},
    ],
)
def test_dynamic_ability_payloads_fail_closed(payload: dict[str, object]) -> None:
    assert cue_for_event(GameEvent("AbilityUsed", payload)) is None


@pytest.mark.parametrize("boss_id", sorted(BOSS_PHASES))
def test_boss_telegraphs_require_the_exact_cue_for_the_exact_boss(boss_id: str) -> None:
    cue_id = f"sfx.boss.{boss_id}"
    event = GameEvent("BossAttackTelegraphed", {"boss_id": boss_id, "cue_id": cue_id})

    assert cue_for_event(event) == cue_id

    assert cue_for_event(GameEvent("BossAttackTelegraphed", {"boss_id": boss_id, "cue_id": "sfx.boss.unknown"})) is None
    other_boss = next(candidate for candidate in BOSS_PHASES if candidate != boss_id)
    assert cue_for_event(GameEvent("BossAttackTelegraphed", {"boss_id": other_boss, "cue_id": cue_id})) is None


def test_unknown_and_malformed_events_are_safely_ignored_but_wrong_dto_types_are_rejected() -> None:
    assert cue_for_event(GameEvent("UnknownTopic", {"cue_id": "sfx.damage"})) is None
    assert cue_for_event(GameEvent("BossAttackTelegraphed", {"boss_id": 1, "cue_id": "sfx.damage"})) is None

    with pytest.raises(TypeError, match="exact GameEvent"):
        cue_for_event(object())  # type: ignore[arg-type]

    class DerivedEvent(GameEvent):
        pass

    with pytest.raises(TypeError, match="exact GameEvent"):
        cue_for_event(DerivedEvent("PlayerDamaged"))


def test_all_eighteen_boss_phase_events_select_the_exact_variation_once() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    for boss_id, phase_ids in BOSS_PHASES.items():
        for phase_index, phase_id in enumerate(phase_ids, start=1):
            played = director.handle(
                (
                    GameEvent(
                        "BossPhaseChanged",
                        {"boss_id": boss_id, "phase_id": phase_id, "phase_index": phase_index},
                    ),
                )
            )
            cue_id = f"music.boss.{boss_id}.p{phase_index}"
            assert played == (cue_id,)
            assert audio.calls[-1] == (cue_id, "music")

            before = tuple(audio.calls)
            assert (
                director.handle(
                    (
                        GameEvent(
                            "BossPhaseChanged",
                            {"boss_id": boss_id, "phase_id": phase_id, "phase_index": phase_index},
                        ),
                    )
                )
                == ()
            )
            assert tuple(audio.calls) == before


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"boss_id": "volt_roc", "phase_id": "volt_roc.chain_sky", "phase_index": True},
        {"boss_id": "volt_roc", "phase_id": "volt_roc.chain_sky", "phase_index": 0},
        {"boss_id": "volt_roc", "phase_id": "volt_roc.chain_sky", "phase_index": 4},
        {"boss_id": "volt_roc", "phase_id": "volt_roc.wrong", "phase_index": 2},
        {"boss_id": "unknown", "phase_id": "volt_roc.chain_sky", "phase_index": 2},
        {"boss_id": 1, "phase_id": "volt_roc.chain_sky", "phase_index": 2},
        {"boss_id": "volt_roc", "phase_id": "volt_roc.chain_sky", "phase_index": float("inf")},
    ],
)
def test_malformed_boss_phase_events_do_not_mutate_audio_state(payload: dict[str, object]) -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    assert director.handle((GameEvent("BossPhaseChanged", payload),)) == ()
    assert director.current_music is None
    assert audio.calls == []


def test_start_accepts_only_exact_manifest_music_ids_and_is_idempotent() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    assert director.start("music.title") is True
    assert director.start("music.title") is True
    assert audio.calls == [("music.title", "music")]
    assert director.current_music == "music.title"
    assert "music.title" in MUSIC_CUE_IDS

    with pytest.raises(ValueError, match="known music cue"):
        director.start("music.boss.unknown.p1")
    with pytest.raises(TypeError, match="music cue ID must be a string"):
        director.start(True)  # type: ignore[arg-type]
    assert audio.calls == [("music.title", "music")]


def test_failed_music_playback_does_not_update_current_music() -> None:
    audio = FakeAudioService(failed_cues=frozenset({"music.map"}))
    director = MusicDirector(audio)

    assert director.start("music.map") is False
    assert director.current_music is None
    assert director.start("music.results") is True
    assert director.current_music == "music.results"


def test_event_order_is_preserved_and_one_sfx_failure_does_not_suppress_later_events() -> None:
    audio = FakeAudioService(
        failed_cues=frozenset({"sfx.damage"}),
        raised_cues=frozenset({"sfx.draw.start"}),
    )
    director = MusicDirector(audio)
    events = (
        GameEvent("PlayerDamaged"),
        GameEvent("EnemyCaptured"),
        GameEvent("MoteCollected"),
        GameEvent("StageCompleted"),
    )

    before = tuple((event.topic, dict(event.payload)) for event in events)
    assert director.handle(events) == ("sfx.mote", "sfx.victory")
    assert audio.calls == [
        ("sfx.damage", "sfx"),
        ("sfx.draw.start", "sfx"),
        ("sfx.mote", "sfx"),
        ("sfx.victory", "sfx"),
    ]
    assert tuple((event.topic, dict(event.payload)) for event in events) == before


def test_guarded_player_hit_emits_one_guard_cue_from_the_semantic_damage_payload() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)
    events = (
        GameEvent(
            "AttackHit",
            {"frame_index": 17, "target_id": 4, "damage": 1, "guarded": True},
        ),
        GameEvent(
            "PlayerDamaged",
            {"frame_index": 17, "target_id": 4, "amount": 1, "guarded": True},
        ),
    )

    assert cue_for_event(events[1]) == "sfx.guard"
    assert director.handle(events) == ("sfx.guard",)
    assert audio.calls == [("sfx.guard", "sfx")]


def test_ordinary_player_hit_is_deduplicated_to_one_damage_cue() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)
    events = (
        GameEvent(
            "AttackHit",
            {"frame_index": 18, "target_id": 4, "damage": 3, "guarded": False},
        ),
        GameEvent(
            "PlayerDamaged",
            {"frame_index": 18, "target_id": 4, "amount": 3, "guarded": False},
        ),
    )

    assert director.handle(events) == ("sfx.damage",)
    assert audio.calls == [("sfx.damage", "sfx")]


def test_enemy_attack_hit_and_projectile_cut_keep_their_independent_semantics() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    assert director.handle(
        (
            GameEvent(
                "AttackHit",
                {"frame_index": 20, "target_id": 8, "damage": 2, "guarded": False},
            ),
            GameEvent("ProjectileCut", {"frame_index": 20, "projectile_id": 9}),
        )
    ) == ("sfx.damage", "sfx.guard")
    assert audio.calls == [("sfx.damage", "sfx"), ("sfx.guard", "sfx")]


def _forged_audio_settings(master: object, music: object, sfx: object, muted: object) -> AudioSettings:
    settings = object.__new__(AudioSettings)
    object.__setattr__(settings, "master_volume", master)
    object.__setattr__(settings, "music_volume", music)
    object.__setattr__(settings, "sfx_volume", sfx)
    object.__setattr__(settings, "muted", muted)
    return settings


def test_settings_multiply_master_and_bus_volumes_exactly_and_publish_mute_state() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    director.apply_settings(AudioSettings(master_volume=0.5, music_volume=0.4, sfx_volume=0.8, muted=False))
    director.apply_settings(AudioSettings(master_volume=0.5, music_volume=0.4, sfx_volume=0.8, muted=True))

    assert audio.volume_calls == [
        ("music", 0.2),
        ("sfx", 0.4),
        ("music", 0.0),
        ("sfx", 0.0),
    ]
    assert audio.mute_calls == [False, True]
    assert director.status.muted is True


@pytest.mark.parametrize(
    "settings",
    [
        _forged_audio_settings(True, 0.5, 0.5, False),
        _forged_audio_settings(float("nan"), 0.5, 0.5, False),
        _forged_audio_settings(0.5, float("inf"), 0.5, False),
        _forged_audio_settings(0.5, 0.5, -0.1, False),
        _forged_audio_settings(0.5, 0.5, 0.5, 1),
    ],
)
def test_malformed_settings_are_rejected_before_any_audio_state_mutation(settings: AudioSettings) -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    with pytest.raises((TypeError, ValueError)):
        director.apply_settings(settings)

    assert audio.volume_calls == []
    assert audio.mute_calls == []


def test_focus_lifecycle_delegation_is_visible_through_audio_status() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)

    director.pause()
    assert director.status == audio.status
    assert asdict(director.status) == {"ready": True, "muted": True, "error_code": "focus_lost"}
    director.resume()
    assert director.status == audio.status == audio._status  # noqa: SLF001 - verifies the fake boundary exactly.
    assert audio.pause_count == audio.resume_count == 1
