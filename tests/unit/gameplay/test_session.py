"""Explicit gameplay-session state, reset, and navigation contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from tests.helpers.gameplay import (
    enter_defeat,
    enter_victory,
    make_active_player,
    make_runtime,
    make_session,
)
from windsprig.core.events import GameEvent
from windsprig.gameplay.components import (
    AbilityState,
    CaptureState,
    DefenseState,
    EchoPickup,
    MovementState,
    PlayerSlot,
    StageGoal,
    Transform,
)
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.session import (
    _TRANSITIONS,
    ALLOWED_ACTIONS,
    GameSession,
    SessionAction,
    SessionNavigation,
    SessionPhase,
    SessionSnapshot,
)
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.systems.stage_goal_system import PROVISIONAL_STAGE_CLEARED_TOPIC
from windsprig.input.commands import InputFrame, MoveCommand

EXPECTED_TRANSITIONS = {
    (SessionPhase.INTRO, SessionAction.START): (SessionPhase.PLAYING, None),
    (SessionPhase.INTRO, SessionAction.RETURN_TO_MAP): (
        SessionPhase.CLOSED,
        SessionNavigation.WORLD_MAP,
    ),
    (SessionPhase.PLAYING, SessionAction.PAUSE): (SessionPhase.PAUSED, None),
    (SessionPhase.PAUSED, SessionAction.RESUME): (SessionPhase.PLAYING, None),
    (SessionPhase.PAUSED, SessionAction.RETRY_STAGE): (SessionPhase.PLAYING, None),
    (SessionPhase.PAUSED, SessionAction.RETURN_TO_MAP): (
        SessionPhase.CLOSED,
        SessionNavigation.WORLD_MAP,
    ),
    (SessionPhase.VICTORY, SessionAction.SHOW_RESULTS): (SessionPhase.RESULTS, None),
    (SessionPhase.DEFEAT, SessionAction.RETRY_CHECKPOINT): (SessionPhase.PLAYING, None),
    (SessionPhase.DEFEAT, SessionAction.RETRY_STAGE): (SessionPhase.PLAYING, None),
    (SessionPhase.DEFEAT, SessionAction.RETURN_TO_MAP): (
        SessionPhase.CLOSED,
        SessionNavigation.WORLD_MAP,
    ),
    (SessionPhase.RESULTS, SessionAction.NEXT_STAGE): (
        SessionPhase.CLOSED,
        SessionNavigation.NEXT_STAGE,
    ),
    (SessionPhase.RESULTS, SessionAction.REPLAY_STAGE): (SessionPhase.PLAYING, None),
    (SessionPhase.RESULTS, SessionAction.RETURN_TO_MAP): (
        SessionPhase.CLOSED,
        SessionNavigation.WORLD_MAP,
    ),
}


def _session_for_phase(phase: SessionPhase) -> GameSession:
    session = make_session()
    if phase is SessionPhase.INTRO:
        return session
    if phase is SessionPhase.CLOSED:
        session.dispatch(SessionAction.RETURN_TO_MAP)
        return session
    session.dispatch(SessionAction.START)
    if phase is SessionPhase.PLAYING:
        return session
    if phase is SessionPhase.PAUSED:
        session.dispatch(SessionAction.PAUSE)
        return session
    if phase is SessionPhase.VICTORY:
        enter_victory(session)
        return session
    if phase is SessionPhase.DEFEAT:
        enter_defeat(session)
        return session
    enter_victory(session)
    session.dispatch(SessionAction.SHOW_RESULTS)
    return session


def _fingerprint(session: GameSession) -> tuple[object, ...]:
    return (
        session.phase,
        session.navigation,
        session.runtime.world.frame_index,
        session.runtime.world.world_hash(),
        tuple(session.runtime.world.events.peek()),
        session.last_frame,
        session.snapshot(),
    )


def test_public_enums_snapshot_and_transition_table_are_exact_and_immutable() -> None:
    assert tuple(phase.value for phase in SessionPhase) == (
        "intro",
        "playing",
        "paused",
        "victory",
        "defeat",
        "results",
        "closed",
    )
    assert tuple(action.value for action in SessionAction) == (
        "start",
        "pause",
        "resume",
        "show_results",
        "retry_checkpoint",
        "retry_stage",
        "replay_stage",
        "next_stage",
        "return_to_map",
    )
    assert tuple(item.value for item in SessionNavigation) == ("next_stage", "world_map")
    assert tuple(field.name for field in fields(SessionSnapshot)) == (
        "phase",
        "stage",
        "result",
        "allowed_actions",
        "navigation",
    )
    snapshot = make_session().snapshot()
    assert not hasattr(snapshot, "__dict__")
    with pytest.raises(FrozenInstanceError):
        snapshot.phase = SessionPhase.CLOSED  # type: ignore[misc]
    assert dict(_TRANSITIONS) == EXPECTED_TRANSITIONS
    assert len(_TRANSITIONS) == 13
    with pytest.raises(TypeError):
        _TRANSITIONS[(SessionPhase.CLOSED, SessionAction.START)] = (  # type: ignore[index]
            SessionPhase.PLAYING,
            None,
        )


def test_allowed_actions_are_ordered_by_phase_and_checkpoint_capability() -> None:
    expected = {
        SessionPhase.INTRO: (SessionAction.START, SessionAction.RETURN_TO_MAP),
        SessionPhase.PLAYING: (SessionAction.PAUSE,),
        SessionPhase.PAUSED: (
            SessionAction.RESUME,
            SessionAction.RETRY_STAGE,
            SessionAction.RETURN_TO_MAP,
        ),
        SessionPhase.VICTORY: (SessionAction.SHOW_RESULTS,),
        SessionPhase.DEFEAT: (SessionAction.RETRY_STAGE, SessionAction.RETURN_TO_MAP),
        SessionPhase.RESULTS: (
            SessionAction.NEXT_STAGE,
            SessionAction.REPLAY_STAGE,
            SessionAction.RETURN_TO_MAP,
        ),
        SessionPhase.CLOSED: (),
    }

    assert SessionAction.RETRY_CHECKPOINT in ALLOWED_ACTIONS[SessionPhase.DEFEAT]
    for phase, actions in expected.items():
        assert _session_for_phase(phase).snapshot().allowed_actions == actions


def test_session_snapshot_is_pure_and_does_not_drain_pending_events() -> None:
    session = make_session()
    session.runtime.world.events.publish("pending", {"value": 1})
    frame_index = session.runtime.world.frame_index
    pending = session.runtime.world.events.peek()

    first = session.snapshot()
    second = session.snapshot()

    assert first == second
    assert session.runtime.world.frame_index == frame_index
    assert session.runtime.world.events.peek() == pending
    assert session.last_frame is None


def test_stage_outcome_resource_is_typed_and_has_no_legacy_authority() -> None:
    runtime = make_runtime()
    assert runtime.world.resources["stage_outcome"] is StageOutcome.RUNNING
    assert "stage_cleared" not in runtime.world.resources

    runtime.world.resources["stage_outcome"] = "completed"

    with pytest.raises(TypeError, match="StageOutcome"):
        runtime.snapshot()
    with pytest.raises(TypeError, match="StageOutcome"):
        runtime.world.snapshot()


@pytest.mark.parametrize(
    ("source", "action", "target", "navigation"),
    tuple(
        (source, action, target, navigation) for (source, action), (target, navigation) in EXPECTED_TRANSITIONS.items()
    ),
)
def test_each_transition_pair_is_explicit(
    source: SessionPhase,
    action: SessionAction,
    target: SessionPhase,
    navigation: SessionNavigation | None,
) -> None:
    session = _session_for_phase(source)
    if action is SessionAction.RETRY_CHECKPOINT:
        with pytest.raises(ValueError, match="checkpoint"):
            session.dispatch(action)
        assert session.phase is source
        return

    snapshot = session.dispatch(action)

    assert snapshot.phase is target
    assert snapshot.navigation is navigation


@pytest.mark.parametrize("phase", tuple(SessionPhase))
def test_invalid_types_and_actions_are_exception_atomic_in_every_phase(
    phase: SessionPhase,
) -> None:
    session = _session_for_phase(phase)
    before = _fingerprint(session)
    invalid_action = {
        SessionPhase.INTRO: SessionAction.PAUSE,
        SessionPhase.PLAYING: SessionAction.START,
        SessionPhase.PAUSED: SessionAction.START,
        SessionPhase.VICTORY: SessionAction.PAUSE,
        SessionPhase.DEFEAT: SessionAction.SHOW_RESULTS,
        SessionPhase.RESULTS: SessionAction.PAUSE,
        SessionPhase.CLOSED: SessionAction.START,
    }[phase]

    with pytest.raises(TypeError, match="SessionAction"):
        session.dispatch("start")  # type: ignore[arg-type]
    assert _fingerprint(session) == before
    with pytest.raises(ValueError, match="not allowed"):
        session.dispatch(invalid_action)
    assert _fingerprint(session) == before


def test_retry_side_effect_failure_does_not_commit_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_for_phase(SessionPhase.PAUSED)
    before = _fingerprint(session)

    def fail_reset() -> object:
        raise RuntimeError("reset failed")

    monkeypatch.setattr(session.runtime, "reset_stage", fail_reset)

    with pytest.raises(RuntimeError, match="reset failed"):
        session.dispatch(SessionAction.RETRY_STAGE)

    assert _fingerprint(session) == before


def test_dispatch_snapshot_failure_does_not_commit_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = make_session()
    before = (
        session.phase,
        session.navigation,
        session.runtime.world.frame_index,
        session.runtime.world.world_hash(),
        tuple(session.runtime.world.events.peek()),
        session.last_frame,
    )

    def fail_snapshot() -> object:
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(session.runtime, "snapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="snapshot failed"):
        session.dispatch(SessionAction.START)

    assert (
        session.phase,
        session.navigation,
        session.runtime.world.frame_index,
        session.runtime.world.world_hash(),
        tuple(session.runtime.world.events.peek()),
        session.last_frame,
    ) == before


def test_reset_construction_failure_preserves_runtime_and_pending_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_for_phase(SessionPhase.PAUSED)
    session.runtime.world.events.publish("pending", {"value": 1})
    before = _fingerprint(session)

    def fail_spawn(_runtime: StageRuntime) -> None:
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(StageRuntime, "_spawn_stage_entities", fail_spawn)

    with pytest.raises(RuntimeError, match="spawn failed"):
        session.dispatch(SessionAction.RETRY_STAGE)

    assert _fingerprint(session) == before


@pytest.mark.parametrize(
    "phase",
    (
        SessionPhase.INTRO,
        SessionPhase.PAUSED,
        SessionPhase.VICTORY,
        SessionPhase.DEFEAT,
        SessionPhase.RESULTS,
        SessionPhase.CLOSED,
    ),
)
def test_non_playing_step_never_advances_the_runtime(phase: SessionPhase) -> None:
    session = _session_for_phase(phase)
    player = session.runtime.player_entities[1]
    movement = session.runtime.world.get_component(player, MovementState)
    defense = session.runtime.world.get_component(player, DefenseState)
    capture = session.runtime.world.get_component(player, CaptureState)
    ability = session.runtime.world.get_component(player, AbilityState)
    movement.coyote_remaining_ms = 73
    movement.jump_buffer_remaining_ms = 61
    defense.guarding = True
    defense.dodge_remaining_ms = 96
    defense.dodge_cooldown_ms = 312
    capture.phase = "drawing"
    capture.draw_elapsed_ms = 47
    ability.charge_ms = 83
    ability.meter = 29
    session.runtime.factory.spawn_echo_pickup("cinder", 400.0, 300.0)
    before = _fingerprint(session)

    returned = session.step(InputFrame.empty())

    assert returned == session.snapshot()
    assert _fingerprint(session) == before


def test_playing_step_advances_exactly_once_and_retains_last_frame() -> None:
    session = make_session()
    session.dispatch(SessionAction.START)
    before = session.runtime.world.frame_index

    snapshot = session.step(InputFrame.empty())

    assert session.runtime.world.frame_index == before + 1
    assert snapshot.phase is SessionPhase.PLAYING
    assert session.last_frame is not None
    assert session.last_frame.view == snapshot.stage
    with pytest.raises(FrozenInstanceError):
        session.last_frame.events = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        session.last_frame = None  # type: ignore[misc]


def test_completed_step_enters_victory_and_retains_semantic_events() -> None:
    session = make_session()
    session.dispatch(SessionAction.START)
    player = session.runtime.player_entities[1]
    player_transform = session.runtime.world.get_component(player, Transform)
    _, _, goal_transform = session.runtime.world.query(StageGoal, Transform)[0]
    player_transform.x = goal_transform.x
    player_transform.y = goal_transform.y

    snapshot = session.step(InputFrame.empty())

    assert snapshot.phase is SessionPhase.VICTORY
    assert snapshot.stage.outcome is StageOutcome.COMPLETED
    assert session.last_frame is not None
    assert [event.topic for event in session.last_frame.events] == [PROVISIONAL_STAGE_CLEARED_TOPIC]
    retained_event = session.last_frame.events[0]
    with pytest.raises(TypeError):
        retained_event.payload["stage_id"] = "mutated"  # type: ignore[index]
    assert retained_event.payload["stage_id"] == "test_stage"
    frame_index = session.runtime.world.frame_index
    retained = session.last_frame
    session.step(InputFrame.empty())
    assert session.runtime.world.frame_index == frame_index
    assert session.last_frame is retained


def test_failed_step_enters_defeat_from_the_typed_outcome() -> None:
    session = make_session()
    session.dispatch(SessionAction.START)
    session.runtime.world.resources["stage_outcome"] = StageOutcome.FAILED

    snapshot = session.step(InputFrame.empty())

    assert snapshot.phase is SessionPhase.DEFEAT
    assert snapshot.stage.outcome is StageOutcome.FAILED
    assert session.last_frame is not None


def test_victory_and_results_wait_for_explicit_choices() -> None:
    session = _session_for_phase(SessionPhase.VICTORY)
    frame_index = session.runtime.world.frame_index

    assert session.step(InputFrame.empty()).phase is SessionPhase.VICTORY
    assert session.runtime.world.frame_index == frame_index
    results = session.dispatch(SessionAction.SHOW_RESULTS)
    assert results.phase is SessionPhase.RESULTS
    assert session.step(InputFrame.empty()).phase is SessionPhase.RESULTS
    assert session.runtime.world.frame_index == frame_index


@pytest.mark.parametrize(
    ("source", "action", "navigation"),
    (
        (SessionPhase.INTRO, SessionAction.RETURN_TO_MAP, SessionNavigation.WORLD_MAP),
        (SessionPhase.RESULTS, SessionAction.NEXT_STAGE, SessionNavigation.NEXT_STAGE),
        (SessionPhase.RESULTS, SessionAction.RETURN_TO_MAP, SessionNavigation.WORLD_MAP),
    ),
)
def test_navigation_is_frozen_when_the_session_closes(
    source: SessionPhase,
    action: SessionAction,
    navigation: SessionNavigation,
) -> None:
    session = _session_for_phase(source)

    closed = session.dispatch(action)

    assert closed.phase is SessionPhase.CLOSED
    assert closed.navigation is navigation
    with pytest.raises(ValueError, match="not allowed"):
        session.dispatch(SessionAction.START)
    assert session.snapshot() == closed


def test_unavailable_checkpoint_retry_is_atomic_and_explicit() -> None:
    session = _session_for_phase(SessionPhase.DEFEAT)
    assert session.runtime.can_retry_checkpoint is False
    player = session.runtime.player_entities[1]
    defense = session.runtime.world.get_component(player, DefenseState)
    defense.guarding = True
    defense.dodge_cooldown_ms = 320
    before = _fingerprint(session)

    with pytest.raises(ValueError, match="checkpoint"):
        session.dispatch(SessionAction.RETRY_CHECKPOINT)
    assert _fingerprint(session) == before
    with pytest.raises(ValueError, match="checkpoint"):
        session.runtime.retry_from_checkpoint()
    assert _fingerprint(session) == before


def test_runtime_reset_matches_fresh_world_and_preserves_subscribers_once() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2, leader=True)
    p3 = make_active_player(3)
    runtime = make_runtime(players=(p3, p1))
    observed: list[GameEvent] = []
    runtime.world.events.subscribe("*", observed.append)
    runtime.sync_active_players((p3, p2))
    runtime.step(InputFrame.empty())
    runtime.step(InputFrame.empty())
    mutated_player = runtime.player_entities[2]
    runtime.world.get_component(mutated_player, MovementState).hover_remaining_ms = 17
    runtime.world.get_component(mutated_player, DefenseState).dodge_cooldown_ms = 311
    runtime.world.get_component(mutated_player, CaptureState).draw_elapsed_ms = 37
    runtime.world.get_component(mutated_player, AbilityState).current_id = "cinder"
    runtime.factory.spawn_echo_pickup("galehook", 90.0, 80.0)
    runtime.world.resources["discovered_ability_ids"] = {"cinder", "galehook"}
    runtime.world.resources["attack_requests"] = [object()]
    runtime.world.events.publish("obsolete_pending", {"value": 1})
    observed.clear()
    event_bus = runtime.world.events

    reset = runtime.reset_stage()
    fresh = make_runtime(players=(p2, p3))

    assert runtime.world.events is event_bus
    assert observed == []
    assert runtime.world.events.peek() == []
    assert runtime.world.frame_index == 0
    assert reset.frame_index == reset.elapsed_ms == 0
    assert reset.outcome is StageOutcome.RUNNING
    assert runtime.result is None
    assert runtime.player_entities == fresh.player_entities == {2: 1, 3: 2}
    assert runtime.world.world_hash() == fresh.world.world_hash()
    assert runtime.world.snapshot() == fresh.world.snapshot()
    assert reset == fresh.snapshot()
    assert runtime.world.get_component(runtime.player_entities[2], MovementState) == MovementState()
    assert runtime.world.get_component(runtime.player_entities[2], DefenseState) == DefenseState()
    assert runtime.world.get_component(runtime.player_entities[2], CaptureState) == CaptureState()
    assert runtime.world.get_component(runtime.player_entities[2], AbilityState) == AbilityState()
    assert runtime.world.query(EchoPickup) == []
    assert runtime.world.resources["discovered_ability_ids"] == set()
    assert runtime.world.resources["attack_requests"] == []

    player_transform = runtime.world.get_component(runtime.player_entities[2], Transform)
    _, _, goal_transform = runtime.world.query(StageGoal, Transform)[0]
    player_transform.x = goal_transform.x
    player_transform.y = goal_transform.y
    frame = runtime.step(InputFrame.empty())
    assert [event.topic for event in observed] == [PROVISIONAL_STAGE_CLEARED_TOPIC]
    assert [event.topic for event in frame.events] == [PROVISIONAL_STAGE_CLEARED_TOPIC]
    assert frame.simulation.event_count == 1


def test_reset_uses_hashed_leader_authority_when_roster_metadata_is_stale() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1, p2))
    canonical_players = (
        make_active_player(1, leader=False),
        make_active_player(2, leader=True),
    )
    runtime.sync_active_players(canonical_players)
    assert runtime.snapshot().goal_gather.leader_slot == 2
    runtime.world.resources["active_players"] = (p1, p2)

    reset = runtime.reset_stage()
    fresh = make_runtime(players=canonical_players)

    assert reset.goal_gather.leader_slot == 2
    assert [(slot.slot, slot.is_leader) for _, slot in runtime.world.query(PlayerSlot)] == [
        (1, False),
        (2, True),
    ]
    assert runtime.world.resources["active_players"] == canonical_players
    assert runtime.world.world_hash() == fresh.world.world_hash()


def test_gameplay_resources_are_hashed_but_presentation_resources_are_not() -> None:
    runtime = make_runtime()
    baseline = runtime.world.snapshot().world_state_hash

    runtime.world.resources["camera_target"] = (999.0, -999.0)
    assert runtime.world.snapshot().world_state_hash == baseline

    runtime.world.resources["stage_outcome"] = StageOutcome.COMPLETED
    assert runtime.world.snapshot().world_state_hash != baseline
    runtime.world.resources["stage_outcome"] = StageOutcome.RUNNING
    assert runtime.world.snapshot().world_state_hash == baseline

    runtime.world.resources["run_energy_spheres"] = 1
    assert runtime.world.snapshot().world_state_hash != baseline
    runtime.world.resources["run_energy_spheres"] = 0
    assert runtime.world.snapshot().world_state_hash == baseline

    runtime.world.resources["collected_mote_ids"] = {
        "test_stage:mote:2",
        "test_stage:mote:1",
    }
    collected_hash = runtime.world.snapshot().world_state_hash
    assert collected_hash != baseline
    runtime.world.resources["collected_mote_ids"] = {
        "test_stage:mote:1",
        "test_stage:mote:2",
    }
    assert runtime.world.snapshot().world_state_hash == collected_hash

    runtime.world.resources["discovered_ability_ids"] = {"galehook", "cinder"}
    discovery_hash = runtime.world.snapshot().world_state_hash
    assert discovery_hash != collected_hash
    runtime.world.resources["discovered_ability_ids"] = ["cinder", "galehook", "cinder"]
    assert runtime.world.snapshot().world_state_hash == discovery_hash


@pytest.mark.parametrize("source", (SessionPhase.PAUSED, SessionPhase.RESULTS))
def test_stage_retry_and_replay_reset_before_returning_to_play(source: SessionPhase) -> None:
    session = make_session()
    session.dispatch(SessionAction.START)
    session.step(InputFrame.empty())
    if source is SessionPhase.PAUSED:
        session.dispatch(SessionAction.PAUSE)
        action = SessionAction.RETRY_STAGE
    else:
        enter_victory(session)
        session.dispatch(SessionAction.SHOW_RESULTS)
        action = SessionAction.REPLAY_STAGE
    session.runtime.world.resources["run_energy_spheres"] = 2
    previous_frame = session.last_frame

    snapshot = session.dispatch(action)
    fresh = make_runtime()

    assert snapshot.phase is SessionPhase.PLAYING
    assert snapshot.navigation is None
    assert session.last_frame is None
    assert previous_frame is not session.last_frame
    assert session.runtime.world.frame_index == 0
    assert snapshot.stage.elapsed_ms == 0
    assert snapshot.stage.outcome is StageOutcome.RUNNING
    assert session.runtime.world.world_hash() == fresh.world.world_hash()


type ScriptItem = SessionAction | InputFrame


@pytest.mark.parametrize(
    "script",
    (
        (
            SessionAction.START,
            InputFrame(commands_by_slot={1: [MoveCommand(player_slot=1, axis=1)]}),
            SessionAction.PAUSE,
            SessionAction.RESUME,
            InputFrame.empty(),
        ),
        (
            SessionAction.START,
            InputFrame.empty(),
            SessionAction.PAUSE,
            SessionAction.RETRY_STAGE,
            InputFrame.empty(),
            SessionAction.PAUSE,
            SessionAction.RETURN_TO_MAP,
        ),
    ),
)
def test_identical_action_scripts_are_deterministic(script: tuple[ScriptItem, ...]) -> None:
    first = make_session()
    second = make_session()

    for item in script:
        if isinstance(item, SessionAction):
            first_snapshot = first.dispatch(item)
            second_snapshot = second.dispatch(item)
        else:
            first_snapshot = first.step(item)
            second_snapshot = second.step(item)
        assert first_snapshot == second_snapshot
        assert first.runtime.world.world_hash() == second.runtime.world.world_hash()
        assert first.last_frame == second.last_frame
