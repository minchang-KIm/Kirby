"""Active-roster and immutable-frame contracts for the production runtime."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from tests.helpers.gameplay import make_active_player, make_runtime, make_stage
from windsprig.config import GameConfig
from windsprig.content.loader import CheckpointSpec, EnemySpawn
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AbilityState,
    AttackRequest,
    CameraFocus,
    CaptureState,
    Collider,
    ControlIntent,
    DefenseState,
    Health,
    MovementState,
    PlayerSlot,
    Projectile,
    StageGoal,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.factory import EntityFactory
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.gameplay.systems.stage_goal_system import PROVISIONAL_STAGE_CLEARED_TOPIC
from windsprig.input.commands import InputFrame
from windsprig.input.roster import DeviceRef


def assert_view_and_hash_reject(
    runtime: StageRuntime,
    error: type[Exception],
    match: str,
) -> None:
    """Require the presentation and deterministic boundaries to reject alike."""
    for read in (runtime.snapshot, runtime.world.snapshot, runtime.world.world_hash):
        with pytest.raises(error, match=match):
            read()


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
    initial_hash = runtime.world.world_hash()

    events = runtime.sync_active_players((p4, p2))

    assert [(event.topic, event.payload["slot"]) for event in events] == [
        ("PlayerLeft", 1),
        ("PlayerLeft", 3),
        ("PlayerJoined", 2),
        ("PlayerJoined", 4),
    ]
    assert [slot.slot for _, slot in runtime.world.query(PlayerSlot)] == [2, 4]
    assert tuple(runtime.player_entities) == (2, 4)
    assert runtime.world.world_hash() != initial_hash


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


def test_leader_authority_updates_snapshot_and_hash_without_reallocation() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1, p2))
    entity_ids = dict(runtime.player_entities)
    initial_hash = runtime.world.world_hash()

    events = runtime.sync_active_players((replace(p1, is_leader=False), replace(p2, is_leader=True)))

    assert events == ()
    assert runtime.player_entities == entity_ids
    assert [(slot.slot, slot.is_leader) for _, slot in runtime.world.query(PlayerSlot)] == [
        (1, False),
        (2, True),
    ]
    assert runtime.snapshot().goal_gather.leader_slot == 2
    assert runtime.world.world_hash() != initial_hash
    canonical_hash = runtime.world.world_hash()
    runtime.world.resources["active_players"] = (p1, p2)
    assert runtime.snapshot().goal_gather.leader_slot == 2
    assert runtime.world.world_hash() == canonical_hash


def test_device_and_visual_metadata_do_not_change_gameplay_hash() -> None:
    p1 = make_active_player(1, leader=True)
    runtime = make_runtime(players=(p1,))
    initial_hash = runtime.world.world_hash()
    entity_id = runtime.player_entities[1]
    cosmetic_update = replace(
        p1,
        device=DeviceRef("keyboard", "replacement-uid", "Replacement Label"),
        color_token="replacement-color",
        icon_token="replacement-icon",
    )

    assert runtime.sync_active_players((cosmetic_update,)) == ()

    assert runtime.player_entities == {1: entity_id}
    assert runtime.world.world_hash() == initial_hash
    assert runtime.snapshot().goal_gather.leader_slot == 1


def test_factory_uses_configured_player_maximum_health() -> None:
    config = GameConfig(player_max_hp=17)
    world = World()
    world.resources["config"] = config

    entity_id = EntityFactory(world).spawn_player(
        make_active_player(1, leader=True),
        64.0,
        160.0,
    )

    health = world.get_component(entity_id, Health)
    assert (health.current, health.maximum) == (17, 17)


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


@pytest.mark.parametrize(
    ("case", "error", "match"),
    (
        ("list", TypeError, "active_players must be a sorted tuple of ActivePlayer values"),
        ("non-player", TypeError, "active_players must be a sorted tuple of ActivePlayer values"),
        ("unsorted", ValueError, "active_players must be sorted by slot"),
        ("mismatched", ValueError, "active_players slots must match player_entities"),
    ),
)
def test_malformed_active_player_resource_is_rejected_by_view_and_hash(
    case: str,
    error: type[Exception],
    match: str,
) -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1, p2))
    malformed: object = {
        "list": [p1, p2],
        "non-player": (p1, object()),
        "unsorted": (p2, p1),
        "mismatched": (p1,),
    }[case]
    runtime.world.resources["active_players"] = malformed

    assert_view_and_hash_reject(runtime, error, match)


@pytest.mark.parametrize(
    ("value", "error", "match"),
    (
        (True, TypeError, "run_energy_spheres must be an integer"),
        (1.5, TypeError, "run_energy_spheres must be an integer"),
        ("1", TypeError, "run_energy_spheres must be an integer"),
        (-1, ValueError, "run_energy_spheres must be non-negative"),
    ),
)
def test_invalid_run_mote_count_is_rejected_by_view_and_hash(
    value: object,
    error: type[Exception],
    match: str,
) -> None:
    runtime = make_runtime()
    runtime.world.resources["run_energy_spheres"] = value

    assert_view_and_hash_reject(runtime, error, match)


@pytest.mark.parametrize(
    "value",
    (
        "test_stage:mote:1",
        {"test_stage:mote:1": True},
        ["test_stage:mote:1", 2],
    ),
)
def test_invalid_collected_mote_collection_is_rejected_by_view_and_hash(
    value: object,
) -> None:
    runtime = make_runtime()
    runtime.world.resources["collected_mote_ids"] = value

    assert_view_and_hash_reject(
        runtime,
        TypeError,
        "collected_mote_ids must be a collection of strings",
    )


def test_arbitrary_collected_mote_ids_share_one_canonical_view_and_hash() -> None:
    runtime = make_runtime()
    runtime.world.resources["collected_mote_ids"] = ["external:mote", "external:mote"]

    snapshot = runtime.snapshot()
    duplicate_hash = runtime.world.world_hash()
    runtime.world.resources["collected_mote_ids"] = {"external:mote"}

    assert snapshot.collected_mote_ids == ("external:mote",)
    assert runtime.world.world_hash() == duplicate_hash


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

    assert [event.topic for event in completed.events] == [PROVISIONAL_STAGE_CLEARED_TOPIC]
    assert completed.simulation.event_count == len(completed.events) == 1
    assert completed.view.outcome is StageOutcome.COMPLETED
    assert following.events == ()
    assert following.simulation.event_count == 0


def test_step_returns_prequeued_and_in_step_events_once_in_queue_order() -> None:
    runtime = make_runtime()
    runtime.world.events.publish("QueuedBeforeStep", {"order": 1})
    player_transform = runtime.world.get_component(runtime.player_entities[1], Transform)
    _, _, goal_transform = runtime.world.query(StageGoal, Transform)[0]
    player_transform.x = goal_transform.x
    player_transform.y = goal_transform.y

    frame = runtime.step(InputFrame.empty())

    assert [event.topic for event in frame.events] == [
        "QueuedBeforeStep",
        PROVISIONAL_STAGE_CLEARED_TOPIC,
    ]
    assert len(frame.events) == frame.simulation.event_count == 2
    assert runtime.world.events.peek() == []
    following = runtime.step(InputFrame.empty())
    assert following.events == ()
    assert following.simulation.event_count == 0


def test_base_scheduler_has_one_collision_and_no_prototype_systems() -> None:
    runtime = make_runtime(players=(make_active_player(1, leader=True),))

    assert tuple(type(system).__name__ for system in runtime.world.scheduler.systems) == (
        "InputCommandSystem",
        "DefenseSystem",
        "MovementSystem",
        "EnemyAISystem",
        "CollisionSystem",
        "CaptureSystem",
        "AbilitySystem",
        "CombatSystem",
        "DamageSystem",
        "PickupSystem",
        "CoopRespawnSystem",
        "StageGoalSystem",
        "CameraSystem",
    )


def test_player_factory_adds_hashed_gameplay_defaults_for_initial_and_joined_players() -> None:
    first = make_active_player(1, leader=True)
    joined = make_active_player(3)
    runtime = make_runtime(players=(first,))
    runtime.sync_active_players((first, joined))

    for slot in (1, 3):
        entity_id = runtime.player_entities[slot]
        assert runtime.world.get_component(entity_id, MovementState) == MovementState(
            hover_remaining_ms=runtime.config.hover_duration_ms
        )
        assert runtime.world.get_component(entity_id, DefenseState) == DefenseState()
        assert runtime.world.get_component(entity_id, CaptureState) == CaptureState()
        assert runtime.world.get_component(entity_id, AbilityState) == AbilityState()

    baseline = runtime.world.world_hash()
    runtime.world.get_component(runtime.player_entities[1], MovementState).coyote_remaining_ms = 9
    assert runtime.world.world_hash() != baseline


@pytest.mark.parametrize(
    ("value", "error"),
    ((None, TypeError), ({"cinder", 7}, TypeError)),
)
def test_invalid_discovered_ability_collection_is_rejected_by_view_and_hash(
    value: object,
    error: type[Exception],
) -> None:
    runtime = make_runtime()
    runtime.world.resources["discovered_ability_ids"] = value

    assert_view_and_hash_reject(
        runtime,
        error,
        "discovered_ability_ids must be a collection of strings",
    )


def test_persisted_attack_requests_are_strictly_hashed() -> None:
    runtime = make_runtime()
    baseline = runtime.world.world_hash()
    request = AttackRequest(
        owner_entity_id=runtime.player_entities[1],
        team="player",
        ability_id="none",
        attack_kind="launched_enemy",
        visual_id="wind_launch",
        x=12.0,
        y=34.0,
        width=26,
        height=26,
        vx=520.0,
        vy=-40.0,
        damage=4,
        knockback_x=260.0,
        knockback_y=-120.0,
        ttl_ms=480,
    )

    runtime.world.resources["attack_requests"] = [request]
    request_hash = runtime.world.world_hash()

    assert request_hash != baseline
    runtime.world.resources["attack_requests"] = [replace(request, damage=5)]
    assert runtime.world.world_hash() != request_hash


@pytest.mark.parametrize("value", (None, (), [object()]))
def test_invalid_attack_request_queue_is_rejected_by_view_and_hash(value: object) -> None:
    runtime = make_runtime()
    runtime.world.resources["attack_requests"] = value

    assert_view_and_hash_reject(
        runtime,
        TypeError,
        "attack_requests must be a list of AttackRequest values",
    )


def test_player_view_uses_component_guard_dodge_iframe_and_hover_state() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    intent = runtime.world.get_component(player, ControlIntent)
    movement = runtime.world.get_component(player, MovementState)
    defense = runtime.world.get_component(player, DefenseState)
    health = runtime.world.get_component(player, Health)
    intent.guard_held = False
    movement.hover_remaining_ms = 123
    defense.guarding = True
    defense.dodge_remaining_ms = 48
    health.invulnerable_ms = 0

    view = runtime.snapshot().players[0]

    assert (view.guard_active, view.dodge_active, view.invulnerable) == (True, True, True)
    assert (view.hover_remaining_ms, view.hover_max_ms) == (123, 850)

    defense.dodge_remaining_ms = 32
    view = runtime.snapshot().players[0]
    assert (view.dodge_active, view.invulnerable) == (True, False)


def test_collision_moves_actor_and_combat_moves_legacy_projectile_exactly_once() -> None:
    runtime = make_runtime()
    actor = runtime.world.create_entity()
    runtime.world.add_component(actor, Transform(300.0, 100.0))
    runtime.world.add_component(actor, Velocity(100.0, 0.0))
    runtime.world.add_component(actor, Collider(10, 10))
    attack = runtime.world.create_entity()
    runtime.world.add_component(attack, Projectile(owner=actor, tag="probe", damage=1, ttl_ms=100))
    runtime.world.add_component(attack, Transform(400.0, 100.0))
    runtime.world.add_component(attack, Velocity(100.0, 0.0))
    runtime.world.add_component(attack, Collider(8, 8, solid=False))
    runtime.world.add_component(attack, Team("neutral"))

    runtime.step(InputFrame.empty())

    actor_transform = runtime.world.get_component(actor, Transform)
    attack_transform = runtime.world.get_component(attack, Transform)
    assert (actor_transform.x, actor_transform.y) == pytest.approx((301.6, 100.64))
    assert (attack_transform.x, attack_transform.y) == pytest.approx((401.6, 100.0))
    assert runtime.world.get_component(attack, Velocity) == Velocity(100.0, 0.0)


def test_snapshot_builds_sorted_immutable_views_for_current_runtime_entities() -> None:
    stage = make_stage(
        enemy_spawns=(EnemySpawn(200.0, 160.0, "grunt", "cinder", 180.0, 240.0),),
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
    runtime.sync_active_players((p1,))
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
    assert first.snapshot().goal_gather.leader_slot == 1
    assert second.snapshot().goal_gather.leader_slot == 1
    first_frame = first.step(InputFrame.empty())
    second_frame = second.step(InputFrame.empty())
    assert first_frame.simulation.world_state_hash == second_frame.simulation.world_state_hash
    assert first_frame.view == second_frame.view
    assert first.result is second.result is None
