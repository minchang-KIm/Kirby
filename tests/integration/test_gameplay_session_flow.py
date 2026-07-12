"""End-to-end session ownership for stage outcomes, retries, and results."""

from __future__ import annotations

import pytest

from tests.helpers.gameplay import frame, make_active_player, make_session, make_stage, move_player_to_goal
from windsprig.config import GameConfig
from windsprig.content import load_catalog_bundle
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.components import Checkpoint, DamageRecord, Health, PlayerSlot, StageGoal, Transform
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.session import (
    GameSession,
    SessionAction,
    SessionNavigation,
    SessionPhase,
)
from windsprig.input.commands import GatherConfirmCommand, InputFrame


def _start(session: GameSession) -> None:
    started = session.dispatch(SessionAction.START)
    assert started.phase is SessionPhase.PLAYING


def _complete(session: GameSession) -> None:
    player_id = session.runtime.player_entities[1]
    _, _, goal = session.runtime.world.query(StageGoal, Transform)[0]
    transform = session.runtime.world.get_component(player_id, Transform)
    transform.x, transform.y = goal.x, goal.y
    session.step(InputFrame.empty())


def _defeat(session: GameSession) -> None:
    player_id = session.runtime.player_entities[1]
    health = session.runtime.world.get_component(player_id, Health)
    queue = session.runtime.world.resources["damage_queue"]
    assert isinstance(queue, list)
    queue.append(DamageRecord(0, player_id, health.maximum, 0.0, -220.0, True))
    session.step(InputFrame.empty())


def test_victory_requires_results_before_frozen_navigation() -> None:
    session = make_session()
    _start(session)
    _complete(session)

    victory = session.snapshot()
    result = session.runtime.result
    assert victory.phase is SessionPhase.VICTORY
    assert victory.result is result
    assert victory.allowed_actions == (SessionAction.SHOW_RESULTS,)
    with pytest.raises(ValueError, match="not allowed from victory"):
        session.dispatch(SessionAction.NEXT_STAGE)

    results = session.dispatch(SessionAction.SHOW_RESULTS)
    assert results.phase is SessionPhase.RESULTS
    assert results.result is result
    closed = session.dispatch(SessionAction.NEXT_STAGE)
    assert closed.phase is SessionPhase.CLOSED
    assert closed.navigation is SessionNavigation.NEXT_STAGE
    assert closed.result is result
    assert session.snapshot().result is result


def test_defeat_exposes_legal_checkpoint_retry_and_commits_effect_first() -> None:
    session = make_session()
    _start(session)
    _defeat(session)

    defeated = session.snapshot()
    player_id = session.runtime.player_entities[1]
    assert defeated.phase is SessionPhase.DEFEAT
    assert SessionAction.RETRY_CHECKPOINT in defeated.allowed_actions
    before = session.runtime.world.get_component(player_id, PlayerSlot).lives

    retried = session.dispatch(SessionAction.RETRY_CHECKPOINT)

    assert retried.phase is SessionPhase.PLAYING
    assert retried.result is None
    assert session.runtime.world.get_component(player_id, PlayerSlot).lives == before - 1
    assert session.last_frame is None


def test_failed_retry_effect_leaves_session_phase_and_navigation_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = make_session()
    _start(session)
    _defeat(session)
    before = session.snapshot()

    def fail_retry():
        raise RuntimeError("retry failed before commit")

    monkeypatch.setattr(session.runtime, "retry_from_checkpoint", fail_retry)
    with pytest.raises(RuntimeError, match="before commit"):
        session.dispatch(SessionAction.RETRY_CHECKPOINT)

    after = session.snapshot()
    assert after.phase is before.phase is SessionPhase.DEFEAT
    assert after.navigation is before.navigation is None
    assert after.result is before.result


def test_replay_resets_result_only_after_results_choice() -> None:
    session = make_session()
    _start(session)
    _complete(session)
    result = session.runtime.result
    session.dispatch(SessionAction.SHOW_RESULTS)

    replayed = session.dispatch(SessionAction.REPLAY_STAGE)

    assert result is not None
    assert replayed.phase is SessionPhase.PLAYING
    assert replayed.result is None
    assert session.runtime.result is None
    assert replayed.stage.frame_index == 0


def test_every_campaign_stage_spawns_its_exact_checkpoint_catalog() -> None:
    config = GameConfig()
    bundle = load_catalog_bundle(config.content_dir)
    registry = create_default_registry(config.content_dir)

    for stage in sorted(bundle.campaign.stages.values(), key=lambda item: item.order):
        runtime = StageRuntime(
            config,
            stage,
            registry,
            (make_active_player(1, leader=True),),
            seed=77,
        )
        expected = tuple(
            (
                checkpoint.checkpoint_id,
                float(checkpoint.tile_x * stage.tile_size),
                float(checkpoint.tile_y * stage.tile_size),
                index == 0,
            )
            for index, checkpoint in enumerate(stage.checkpoints)
        )

        assert (
            tuple((view.checkpoint_id, view.x, view.y, view.is_active) for view in runtime.snapshot().checkpoints)
            == expected
        )
        assert len(runtime.world.query(Checkpoint)) == len(stage.checkpoints)
        assert runtime.world.resources["active_checkpoint_id"] == stage.checkpoints[0].checkpoint_id


def test_coop_leader_gather_transitions_session_on_the_188th_followup_step() -> None:
    config = GameConfig()
    session = GameSession.create(
        config,
        make_stage(player_spawns=((64.0, 160.0), (112.0, 160.0))),
        create_default_registry(config.content_dir),
        (make_active_player(1, leader=True), make_active_player(2)),
        seed=77,
    )
    _start(session)
    move_player_to_goal(session.runtime, 1)

    started = session.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    assert started.phase is SessionPhase.PLAYING
    assert started.stage.goal_gather.countdown_remaining_ms == 3_000
    for _ in range(187):
        penultimate = session.step(InputFrame.empty())
    assert penultimate.phase is SessionPhase.PLAYING
    assert penultimate.stage.goal_gather.countdown_remaining_ms == 8

    victory = session.step(InputFrame.empty())

    assert victory.phase is SessionPhase.VICTORY
    assert victory.result is not None
    assert victory.result.active_slots == (1, 2)
    assert session.last_frame is not None
    assert tuple(event.topic for event in session.last_frame.events)[-2:] == (
        "GatherCompleted",
        "StageCompleted",
    )
