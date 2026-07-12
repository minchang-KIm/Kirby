"""Release-catalog and runtime integration for deterministic boss encounters."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.helpers.gameplay import make_active_player, make_stage
from windsprig.config import GameConfig
from windsprig.content.loader import load_boss_catalog, load_campaign_catalog
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.bosses import BossCommand, BossState, boss_command_sort_key
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    EnemyAI,
    Facing,
    Health,
    StageGoal,
    Team,
    Transform,
)
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.session import GameSession, SessionAction, SessionPhase
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.systems.stage_goal_system import PROVISIONAL_STAGE_CLEARED_TOPIC
from windsprig.input.commands import InputFrame

CONTENT_DIR = Path("windsprig/content")


def _runtime(stage_id: str = "world_1_stage_5") -> StageRuntime:
    config = GameConfig()
    stage = load_campaign_catalog(CONTENT_DIR).stages[stage_id]
    return StageRuntime(
        config,
        stage,
        create_default_registry(CONTENT_DIR),
        (make_active_player(1, leader=True),),
        seed=20260711,
    )


def test_release_rootjaw_changes_phase_once_and_telegraphs_before_attack() -> None:
    bosses = load_boss_catalog(CONTENT_DIR)
    runtime = _runtime()
    boss_entity, state, health = runtime.world.query(BossState, Health)[0]

    frame = runtime.step(InputFrame.empty())
    health.current = 70
    changed = runtime.step(InputFrame.empty())

    assert state.boss_id == "rootjaw"
    assert frame.events[0].topic == "BossAttackTelegraphed"
    assert frame.events[0].payload["attack_id"] == "rootjaw.burrow_line"
    assert [event.topic for event in changed.events] == ["BossPhaseChanged"]
    assert runtime.world.get_component(boss_entity, BossState).phase_id == "rootjaw.tangled_fury"
    assert bosses["rootjaw"].phases[1].phase_id == "rootjaw.tangled_fury"


def test_boss_runtime_spawns_one_canonical_entity_and_exposes_only_boss_view() -> None:
    runtime = _runtime()
    rows = runtime.world.query(
        BossState,
        Transform,
        Collider,
        Team,
        Health,
        ActorState,
        Facing,
    )

    assert len(rows) == 1
    entity_id, state, transform, collider, team, health, actor, facing = rows[0]
    assert state == BossState(
        boss_id="rootjaw",
        entity_id=entity_id,
        phase_index=0,
        phase_id="rootjaw.buried_hunger",
        attack_index=0,
        mode="ready",
        remaining_ms=0,
        active_attack_id=None,
    )
    assert team.name == "enemy"
    assert (health.current, health.maximum) == (120, 120)
    assert (collider.width, collider.height) == (64, 64)
    assert (actor.name, facing.direction) == ("Idle", -1)
    assert 0 <= transform.x < runtime.stage.pixel_width
    assert 0 <= transform.y < runtime.stage.pixel_height
    assert runtime.world.try_component(entity_id, EnemyAI) is None

    snapshot = runtime.snapshot()
    assert all(enemy.entity_id != entity_id for enemy in snapshot.enemies)
    assert len(snapshot.bosses) == 1
    assert snapshot.bosses[0].entity_id == entity_id
    assert snapshot.bosses[0].telegraph_id is None
    assert snapshot.bosses[0].vulnerability_state == "hidden"


def test_ordered_scheduler_preserves_unsupported_boss_commands_without_duplicates() -> None:
    runtime = _runtime()

    telegraph = runtime.step(InputFrame.empty())
    for _ in range(56):
        runtime.step(InputFrame.empty())
    before_execute = runtime.snapshot()
    execute = runtime.step(InputFrame.empty())

    assert [event.topic for event in telegraph.events] == ["BossAttackTelegraphed"]
    assert telegraph.simulation.event_count == 1
    assert telegraph.view.bosses[0].telegraph_id == "rootjaw.burrow_line"
    assert telegraph.view.bosses[0].telegraph_remaining_ms == 900
    assert before_execute.bosses[0].telegraph_remaining_ms == 4
    assert execute.events == ()
    assert execute.view.bosses[0].telegraph_id is None
    assert runtime.world.resources["boss_commands"] == (
        BossCommand(
            command="execute",
            attack_id="rootjaw.burrow_line",
            parameters=(("lanes", 1), ("speed", 180)),
        ),
    )

    runtime.step(InputFrame.empty())
    assert runtime.world.resources["boss_commands"] == (
        BossCommand(
            command="execute",
            attack_id="rootjaw.burrow_line",
            parameters=(("lanes", 1), ("speed", 180)),
        ),
    )

    for _ in range(600):
        runtime.step(InputFrame.empty())

    retained = runtime.world.resources["boss_commands"]
    assert isinstance(retained, tuple)
    assert retained == tuple(sorted(retained, key=boss_command_sort_key))
    assert len(retained) == len(set(retained))
    assert {command.attack_id for command in retained} == {
        "rootjaw.burrow_line",
        "rootjaw.seed_spit",
    }


def test_undefeated_boss_gates_goal_and_defeat_releases_it_in_the_same_frame() -> None:
    runtime = _runtime()
    player = runtime.player_entities[1]
    player_transform = runtime.world.get_component(player, Transform)
    _, _, goal_transform = runtime.world.query(StageGoal, Transform)[0]
    player_transform.x = goal_transform.x
    player_transform.y = goal_transform.y

    gated = runtime.step(InputFrame.empty())

    assert gated.view.outcome is StageOutcome.RUNNING
    assert PROVISIONAL_STAGE_CLEARED_TOPIC not in [event.topic for event in gated.events]

    _, boss_state, boss_health = runtime.world.query(BossState, Health)[0]
    boss_health.current = 0
    boss_health.dead = True
    released = runtime.step(InputFrame.empty())

    assert boss_state.defeated is False
    assert [event.topic for event in released.events] == [
        "BossDefeated",
        PROVISIONAL_STAGE_CLEARED_TOPIC,
    ]
    assert released.view.bosses[0].hp == 0
    assert released.view.bosses[0].telegraph_id is None
    assert released.view.outcome is StageOutcome.COMPLETED


def test_boss_state_freezes_while_paused_and_retry_matches_a_fresh_runtime() -> None:
    runtime = _runtime()
    session = GameSession(runtime)
    session.dispatch(SessionAction.START)
    session.step(InputFrame.empty())
    session.dispatch(SessionAction.PAUSE)
    before = (
        runtime.world.frame_index,
        runtime.world.world_hash(),
        runtime.world.rng.state_hash(),
        runtime.snapshot(),
    )

    paused = session.step(InputFrame.empty())

    assert paused.phase is SessionPhase.PAUSED
    assert (
        runtime.world.frame_index,
        runtime.world.world_hash(),
        runtime.world.rng.state_hash(),
        runtime.snapshot(),
    ) == before

    reset = session.dispatch(SessionAction.RETRY_STAGE)
    fresh = _runtime()
    assert reset.phase is SessionPhase.PLAYING
    assert reset.stage == fresh.snapshot()
    assert runtime.world.world_hash() == fresh.world.world_hash()
    assert runtime.world.rng.state_hash() == fresh.world.rng.state_hash()


def test_non_boss_stage_never_loads_boss_content() -> None:
    release_config = GameConfig()
    config = replace(release_config, content_dir=Path("does-not-exist"))

    runtime = StageRuntime(
        config,
        make_stage(),
        create_default_registry(release_config.content_dir),
        (make_active_player(1, leader=True),),
        seed=9,
    )

    assert runtime.snapshot().bosses == ()
    assert runtime.world.query(BossState) == []


def test_boss_command_resource_is_strictly_validated_ordered_and_hashed() -> None:
    runtime = _runtime()
    baseline = runtime.world.world_hash()
    command = BossCommand("execute", "rootjaw.burrow_line", (("speed", 180),))
    later = BossCommand("execute", "rootjaw.seed_spit", (("projectiles", 5),))

    runtime.world.resources["boss_commands"] = (command,)
    assert runtime.world.world_hash() != baseline
    runtime.world.resources["boss_commands"] = ()
    assert runtime.world.world_hash() == baseline

    runtime.world.resources["boss_commands"] = [command]
    with pytest.raises(TypeError, match="boss_commands"):
        runtime.world.world_hash()

    runtime.world.resources["boss_commands"] = (later, command)
    with pytest.raises(ValueError, match="sorted"):
        runtime.world.world_hash()
