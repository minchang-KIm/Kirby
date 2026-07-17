"""Deterministic co-op recovery and leader-confirmed goal contracts."""

from __future__ import annotations

import pytest

from tests.helpers.gameplay import (
    defeat_player,
    frame,
    make_active_player,
    make_coop_runtime,
    make_runtime,
    move_player_away_from_goal,
    move_player_to_goal,
    player_view,
    step_count,
)
from windsprig.gameplay.components import ActorState, ControlIntent, Health, PlayerSlot, Respawn, StageGoal, Transform
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.systems.coop_respawn_system import formation_x_for_slot
from windsprig.input.commands import GatherConfirmCommand, InputFrame


def test_gather_confirmation_is_a_single_fixed_step_intent_edge() -> None:
    runtime = make_runtime()
    player_id = runtime.player_entities[1]

    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    intent = runtime.world.get_component(player_id, ControlIntent)
    assert intent.gather_confirmed is True

    runtime.step(InputFrame.empty())
    assert intent.gather_confirmed is False


def test_dead_partner_waits_exact_delay_then_pays_one_life_near_living_anchor() -> None:
    runtime = make_coop_runtime()
    anchor_x = runtime.world.get_component(runtime.player_entities[1], Transform).x

    defeated = defeat_player(runtime, 2)

    assert "PlayerDefeated" in tuple(event.topic for event in defeated.events)
    assert runtime.world.get_component(runtime.player_entities[2], Respawn).timer_ms == 1_800
    penultimate = step_count(runtime, 112)
    assert player_view(runtime, 2).actor_state == "Dead"
    assert runtime.world.get_component(runtime.player_entities[2], Respawn).timer_ms == 8
    assert "PlayerRespawned" not in tuple(event.topic for event in penultimate.events)

    respawned = runtime.step(InputFrame.empty())
    view = player_view(runtime, 2)
    assert view.lives_remaining == 2
    assert view.x == pytest.approx(anchor_x + 18.0)
    assert view.invulnerable is True
    assert tuple(event.topic for event in respawned.events)[-1] == "PlayerRespawned"


def test_one_based_slots_map_to_zero_based_respawn_formation_offsets() -> None:
    runtime = make_coop_runtime(4)
    anchor_x = runtime.world.get_component(runtime.player_entities[1], Transform).x
    for slot in (2, 3, 4):
        entity_id = runtime.player_entities[slot]
        health = runtime.world.get_component(entity_id, Health)
        health.current = 0
        health.dead = True
        runtime.world.get_component(entity_id, ActorState).name = "Dead"
        runtime.world.get_component(entity_id, Respawn).timer_ms = 0

    runtime.step(InputFrame.empty())

    assert tuple(player_view(runtime, slot).x for slot in (2, 3, 4)) == pytest.approx(
        (anchor_x + 18.0, anchor_x + 36.0, anchor_x + 54.0)
    )


@pytest.mark.parametrize(
    ("anchor_x", "slot", "error", "match"),
    (
        ("64", 2, TypeError, "anchor x must be a number"),
        (True, 2, TypeError, "anchor x must be a number"),
        (float("inf"), 2, ValueError, "anchor x must be finite"),
        (64.0, True, TypeError, "slot must be an integer"),
        (64.0, 2.0, TypeError, "slot must be an integer"),
        (64.0, 0, ValueError, r"slot must be in \[1, 4\]"),
        (64.0, 5, ValueError, r"slot must be in \[1, 4\]"),
    ),
)
def test_respawn_formation_rejects_malformed_public_arguments(
    anchor_x: object,
    slot: object,
    error: type[Exception],
    match: str,
) -> None:
    with pytest.raises(error, match=match):
        formation_x_for_slot(anchor_x, slot)  # type: ignore[arg-type]


def test_one_player_at_goal_requires_leader_gather_for_exact_3000_ms() -> None:
    runtime = make_coop_runtime()
    move_player_to_goal(runtime, 1)

    waiting = runtime.step(InputFrame.empty())

    assert waiting.view.outcome is StageOutcome.RUNNING
    assert waiting.view.goal_gather.at_goal_slots == (1,)
    assert waiting.view.goal_gather.required_slots == (1, 2)
    assert waiting.view.goal_gather.leader_slot == 1
    started = runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    assert tuple(event.topic for event in started.events)[-1] == "GatherStarted"
    assert started.view.goal_gather.leader_slot == 1
    assert started.view.goal_gather.leader_confirmed is True
    assert started.view.goal_gather.countdown_remaining_ms == 3_000

    penultimate = step_count(runtime, 187)
    assert penultimate.view.outcome is StageOutcome.RUNNING
    assert penultimate.view.goal_gather.countdown_remaining_ms == 8

    completed = runtime.step(InputFrame.empty())
    assert completed.view.outcome is StageOutcome.COMPLETED
    assert completed.view.goal_gather.leader_confirmed is False
    assert completed.view.goal_gather.countdown_remaining_ms == 0
    assert tuple(event.topic for event in completed.events)[-2:] == ("GatherCompleted", "StageCompleted")


def test_nonleader_is_ignored_and_leader_leaving_goal_cancels() -> None:
    runtime = make_coop_runtime()
    move_player_to_goal(runtime, 1)

    ignored = runtime.step(frame(2, GatherConfirmCommand(player_slot=2, pressed=True)))
    assert "GatherStarted" not in tuple(event.topic for event in ignored.events)
    assert ignored.view.goal_gather.countdown_remaining_ms == 0

    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    move_player_away_from_goal(runtime, 1)
    cancelled = runtime.step(InputFrame.empty())

    assert tuple(event.topic for event in cancelled.events)[-1] == "GatherCancelled"
    assert cancelled.events[-1].payload["reason"] == "leader_left_goal"
    assert cancelled.view.goal_gather.leader_slot == 1
    assert cancelled.view.goal_gather.leader_confirmed is False
    assert cancelled.view.goal_gather.countdown_remaining_ms == 0


def test_player_slot_leadership_is_the_only_deterministic_gather_authority() -> None:
    runtime = make_coop_runtime()
    move_player_to_goal(runtime, 1)
    runtime.world.get_component(runtime.player_entities[1], PlayerSlot).is_leader = False
    runtime.world.get_component(runtime.player_entities[2], PlayerSlot).is_leader = True

    ignored = runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))

    assert ignored.view.goal_gather.leader_slot == 2
    assert "GatherStarted" not in tuple(event.topic for event in ignored.events)
    move_player_away_from_goal(runtime, 1)
    move_player_to_goal(runtime, 2)
    started = runtime.step(frame(2, GatherConfirmCommand(player_slot=2, pressed=True)))
    assert started.events[-1].topic == "GatherStarted"
    assert started.events[-1].payload["leader_slot"] == 2


def test_everyone_arriving_during_countdown_completes_the_active_gather() -> None:
    runtime = make_coop_runtime()
    move_player_to_goal(runtime, 1)
    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    move_player_to_goal(runtime, 2)

    completed = runtime.step(InputFrame.empty())

    assert completed.view.outcome is StageOutcome.COMPLETED
    assert completed.view.goal_gather.countdown_remaining_ms == 0
    assert tuple(event.topic for event in completed.events)[-2:] == ("GatherCompleted", "StageCompleted")
    assert completed.events[-2].payload["gathered_slots"] == ()


def test_leader_defeat_cancels_gather_while_partner_remains_alive() -> None:
    runtime = make_coop_runtime()
    move_player_to_goal(runtime, 1)
    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))

    cancelled = defeat_player(runtime, 1)

    assert tuple(event.topic for event in cancelled.events)[-1] == "GatherCancelled"
    assert cancelled.events[-1].payload["reason"] == "leader_defeated"
    assert cancelled.view.goal_gather.countdown_remaining_ms == 0


def test_roster_change_cancels_before_membership_mutation() -> None:
    runtime = make_coop_runtime()
    move_player_to_goal(runtime, 1)
    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))

    events = runtime.sync_active_players((make_active_player(1, leader=True),))

    assert tuple(event.topic for event in events) == ("GatherCancelled", "PlayerLeft")
    assert events[0].payload["reason"] == "roster_changed"
    assert runtime.snapshot().goal_gather.countdown_remaining_ms == 0
    assert tuple(runtime.player_entities) == (1,)


def test_gather_teleports_living_waiters_and_revives_dead_waiters_with_cost() -> None:
    runtime = make_coop_runtime(3)
    move_player_to_goal(runtime, 1)
    dead_id = runtime.player_entities[3]
    dead_health = runtime.world.get_component(dead_id, Health)
    dead_health.current = 0
    dead_health.dead = True
    runtime.world.get_component(dead_id, ActorState).name = "Dead"
    runtime.world.get_component(dead_id, Respawn).timer_ms = 5_000
    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    step_count(runtime, 187)

    completed = runtime.step(InputFrame.empty())

    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    second = runtime.world.get_component(runtime.player_entities[2], Transform)
    third = runtime.world.get_component(dead_id, Transform)
    assert (second.x, second.y) == pytest.approx((goal.x + 6.0, goal.y))
    assert (third.x, third.y) == pytest.approx((goal.x + 12.0, goal.y))
    assert runtime.world.get_component(dead_id, PlayerSlot).lives == 2
    assert (dead_health.dead, dead_health.current, dead_health.invulnerable_ms) == (
        False,
        max(1, dead_health.maximum // 2),
        1_200,
    )
    topics = tuple(event.topic for event in completed.events)
    assert topics[-3:] == ("PlayerRespawned", "GatherCompleted", "StageCompleted")
    assert completed.events[-2].payload["gathered_slots"] == (2, 3)
    assert completed.view.goal_gather.at_goal_slots == (1, 2, 3)


def test_exhausted_dead_player_is_not_required_for_ordinary_team_completion() -> None:
    runtime = make_coop_runtime()
    exhausted_id = runtime.player_entities[2]
    exhausted_health = runtime.world.get_component(exhausted_id, Health)
    exhausted_health.current = 0
    exhausted_health.dead = True
    runtime.world.get_component(exhausted_id, PlayerSlot).lives = 0
    runtime.world.get_component(exhausted_id, ActorState).name = "Dead"
    move_player_to_goal(runtime, 1)

    completed = runtime.step(InputFrame.empty())

    assert completed.view.outcome is StageOutcome.COMPLETED
    assert completed.view.goal_gather.required_slots == (1,)
    assert completed.view.goal_gather.at_goal_slots == (1,)
    assert "GatherStarted" not in tuple(event.topic for event in completed.events)
