"""Active-roster and immutable-frame contracts for the production runtime."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from tests.helpers.gameplay import make_active_player, make_runtime, make_stage
from windsprig.content.loader import CheckpointSpec, EnemySpawn
from windsprig.gameplay.components import (
    CameraFocus,
    Collider,
    Health,
    PlayerSlot,
    Projectile,
    StageGoal,
    Transform,
    Velocity,
)
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.input.commands import InputFrame
from windsprig.input.roster import DeviceRef


def test_runtime_spawns_only_sorted_active_players_before_stage_entities() -> None:
    p1 = make_active_player(1, leader=True)
    p3 = make_active_player(3)

    runtime = make_runtime(players=(p3, p1))

    assert runtime.player_entities == {1: 1, 3: 2}
    assert [(entity, slot.slot) for entity, slot in runtime.world.query(PlayerSlot)] == [
        (1, 1),
        (2, 3),
    ]
    assert tuple(view.slot for view in runtime.snapshot().players) == (1, 3)
    assert tuple(view.slot for view in runtime.snapshot().camera_targets) == (1, 3)


def test_runtime_can_represent_an_empty_pause_lobby_roster() -> None:
    runtime = make_runtime(players=())

    assert runtime.player_entities == {}
    assert runtime.snapshot().players == ()
    assert runtime.snapshot().camera_targets == ()


def test_pause_lobby_sync_leaves_then_joins_in_sorted_slot_order() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2, leader=True)
    p3 = make_active_player(3)
    p4 = make_active_player(4)
    runtime = make_runtime(players=(p3, p1))

    events = runtime.sync_active_players((p4, p2))

    assert [(event.topic, event.payload["slot"]) for event in events] == [
        ("PlayerLeft", 1),
        ("PlayerLeft", 3),
        ("PlayerJoined", 2),
        ("PlayerJoined", 4),
    ]
    assert [slot.slot for _, slot in runtime.world.query(PlayerSlot)] == [2, 4]
    assert tuple(runtime.player_entities) == (2, 4)


def test_sync_is_idempotent_and_metadata_updates_do_not_reallocate_entity() -> None:
    p1 = make_active_player(1, leader=True)
    runtime = make_runtime(players=(p1,))
    entity_id = runtime.player_entities[1]
    reassigned = replace(
        p1,
        device=DeviceRef("keyboard", "replacement", "Replacement Keyboard"),
        color_token="new-color",
        icon_token="new-icon",
        is_leader=False,
    )

    assert runtime.sync_active_players((p1,)) == ()
    assert runtime.sync_active_players((reassigned,)) == ()

    assert runtime.player_entities == {1: entity_id}
    assert runtime.world.resources["active_players"] == (reassigned,)


def test_rejoining_a_slot_allocates_a_fresh_monotonic_entity_id() -> None:
    p1 = make_active_player(1, leader=True)
    runtime = make_runtime(players=(p1,))
    first_id = runtime.player_entities[1]

    runtime.sync_active_players(())
    runtime.sync_active_players((p1,))

    assert runtime.player_entities[1] > first_id
    assert first_id not in runtime.world.alive_entities


@pytest.mark.parametrize("slot", [0, 5, True])
def test_sync_rejects_out_of_range_player_slots_without_mutation(slot: object) -> None:
    p1 = make_active_player(1, leader=True)
    runtime = make_runtime(players=(p1,))
    invalid = replace(p1, slot=slot)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="slot"):
        runtime.sync_active_players((invalid,))

    assert runtime.player_entities == {1: 1}
    assert runtime.world.resources["active_players"] == (p1,)


def test_sync_rejects_duplicate_slots_without_mutation() -> None:
    p1 = make_active_player(1, leader=True)
    runtime = make_runtime(players=(p1,))

    with pytest.raises(ValueError, match="duplicate"):
        runtime.sync_active_players((p1, replace(p1, is_leader=False)))

    assert runtime.player_entities == {1: 1}
    assert runtime.world.resources["active_players"] == (p1,)


def test_runtime_rejects_stage_without_player_spawn() -> None:
    with pytest.raises(ValueError, match="player spawn"):
        make_runtime(stage=make_stage(player_spawns=()))


def test_sync_events_are_published_once_and_do_not_leak_into_step_frames() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1,))

    assert runtime.world.events.peek() == []
    joined = runtime.sync_active_players((p1, p2))

    assert [event.topic for event in joined] == ["PlayerJoined"]
    assert [event.topic for event in runtime.test_events] == ["PlayerJoined"]
    assert runtime.world.events.peek() == []

    first = runtime.step(InputFrame.empty())
    second = runtime.step(InputFrame.empty())

    assert first.events == second.events == ()
    assert first.simulation.event_count == second.simulation.event_count == 0
    assert first.simulation.frame_index == first.view.frame_index
    assert second.simulation.frame_index == second.view.frame_index


def test_sync_preserves_unrelated_events_already_waiting_on_the_bus() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1,))
    runtime.world.events.publish("Unrelated", {"value": 7})
    unrelated = runtime.world.events.peek()[0]
    runtime.test_events.clear()

    joined = runtime.sync_active_players((p1, p2))

    assert [event.topic for event in joined] == ["PlayerJoined"]
    assert [event.topic for event in runtime.test_events] == ["PlayerJoined"]
    assert runtime.world.events.peek() == [unrelated]


def test_step_captures_each_system_event_in_its_matching_frame_only() -> None:
    runtime = make_runtime()
    player_transform = runtime.world.get_component(runtime.player_entities[1], Transform)
    _, _, goal_transform = runtime.world.query(StageGoal, Transform)[0]
    player_transform.x = goal_transform.x
    player_transform.y = goal_transform.y

    completed = runtime.step(InputFrame.empty())
    following = runtime.step(InputFrame.empty())

    assert [event.topic for event in completed.events] == ["stage_cleared"]
    assert completed.simulation.event_count == len(completed.events) == 1
    assert completed.view.outcome is StageOutcome.COMPLETED
    assert following.events == ()
    assert following.simulation.event_count == 0


def test_base_scheduler_has_one_collision_and_no_prototype_systems() -> None:
    runtime = make_runtime(players=(make_active_player(1, leader=True),))

    assert tuple(type(system).__name__ for system in runtime.world.scheduler.systems) == (
        "InputCommandSystem",
        "EnemyAISystem",
        "MovementSystem",
        "CollisionSystem",
        "AbilitySystem",
        "CombatSystem",
        "DamageSystem",
        "PickupSystem",
        "CoopRespawnSystem",
        "StageGoalSystem",
        "CameraSystem",
    )


def test_snapshot_builds_sorted_immutable_views_for_current_runtime_entities() -> None:
    stage = make_stage(
        enemy_spawns=(
            EnemySpawn(200.0, 160.0, "grunt", "cinder", 180.0, 240.0),
        ),
        checkpoints=(CheckpointSpec("test_stage.start", 2, 5),),
    )
    runtime = make_runtime(
        players=(make_active_player(3), make_active_player(1, leader=True)),
        stage=stage,
    )
    attack_id = runtime.world.create_entity()
    runtime.world.add_component(attack_id, Projectile(owner=1, tag="gust", damage=2, ttl_ms=96))
    runtime.world.add_component(attack_id, Transform(120.0, 90.0))
    runtime.world.add_component(attack_id, Collider(10, 12, solid=False))
    runtime.world.add_component(attack_id, Velocity(-40.0, 0.0))
    runtime.world.resources["collected_mote_ids"] = {
        "test_stage:mote:2",
        "test_stage:mote:1",
    }

    snapshot = runtime.snapshot()

    assert tuple(view.slot for view in snapshot.players) == (1, 3)
    assert tuple(view.entity_id for view in snapshot.enemies) == tuple(
        sorted(view.entity_id for view in snapshot.enemies)
    )
    assert [(view.entity_id, view.attack_kind, view.facing) for view in snapshot.attacks] == [
        (attack_id, "gust", -1),
    ]
    assert [(view.checkpoint_id, view.x, view.y) for view in snapshot.checkpoints] == [
        ("test_stage.start", 64.0, 160.0),
    ]
    assert snapshot.goal_gather.required_slots == (1, 3)
    assert snapshot.goal_gather.leader_slot == 1
    assert snapshot.collected_mote_ids == (
        "test_stage:mote:1",
        "test_stage:mote:2",
    )
    assert snapshot.outcome is StageOutcome.RUNNING
    with pytest.raises(FrozenInstanceError):
        snapshot.elapsed_ms = 7  # type: ignore[misc]


def test_camera_snapshot_and_system_ignore_inactive_dead_and_disabled_targets() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1, p2))
    runtime.step(InputFrame.empty())
    assert runtime.world.resources["camera_target"] is not None

    runtime.world.get_component(runtime.player_entities[1], Health).dead = True
    runtime.world.get_component(runtime.player_entities[1], PlayerSlot).lives = 0
    runtime.world.get_component(runtime.player_entities[2], CameraFocus).enabled = False
    runtime.step(InputFrame.empty())

    assert runtime.snapshot().camera_targets == ()
    assert runtime.world.resources["camera_target"] is None
    runtime.world.resources["active_players"] = (p1,)
    runtime.world.get_component(runtime.player_entities[1], Health).dead = False
    runtime.world.get_component(runtime.player_entities[1], CameraFocus).enabled = True
    assert tuple(view.slot for view in runtime.snapshot().camera_targets) == (1,)


@pytest.mark.parametrize("ineligible_weight", [0.0, -1.0])
def test_camera_ignores_non_positive_focus_weights(ineligible_weight: float) -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1, p2))
    runtime.world.get_component(runtime.player_entities[1], CameraFocus).weight = ineligible_weight
    runtime.world.get_component(runtime.player_entities[1], Transform).x = 900.0
    runtime.world.get_component(runtime.player_entities[2], Transform).x = 120.0

    runtime.step(InputFrame.empty())

    assert tuple(view.slot for view in runtime.snapshot().camera_targets) == (2,)
    target = runtime.snapshot().camera_targets[0]
    assert runtime.world.resources["camera_target"] == (target.x, target.y)


def test_fresh_runtimes_have_identical_initial_and_stepped_hashes() -> None:
    players = (make_active_player(2), make_active_player(1, leader=True))
    first = make_runtime(players=players)
    second = make_runtime(players=tuple(reversed(players)))

    assert first.world.world_hash() == second.world.world_hash()
    first_frame = first.step(InputFrame.empty())
    second_frame = second.step(InputFrame.empty())
    assert first_frame.simulation.world_state_hash == second_frame.simulation.world_state_hash
    assert first_frame.view == second_frame.view
    assert first.result is second.result is None
