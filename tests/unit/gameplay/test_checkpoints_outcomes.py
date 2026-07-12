"""Checkpoint, terminal-outcome, retry, and raw-result contracts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.helpers.gameplay import make_active_player, make_runtime, make_stage
from windsprig.config import GameConfig
from windsprig.content import load_catalog_bundle
from windsprig.content.loader import CheckpointSpec, EnemySpawn, MoteSpec
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.bosses import BossState
from windsprig.gameplay.components import (
    ActorState,
    Attack,
    AttackRequest,
    CapturedBy,
    CaptureState,
    Checkpoint,
    Collider,
    ControlIntent,
    DamageRecord,
    DefenseState,
    Health,
    PendingEnemyLaunch,
    PlayerSlot,
    Respawn,
    StageGoal,
    Transform,
    Velocity,
)
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.snapshot import StageOutcome, StageResult
from windsprig.gameplay.systems import StageGoalSystem
from windsprig.gameplay.validation import validate_deaths_by_slot
from windsprig.input.commands import InputFrame


def _checkpoint_stage():
    return make_stage(
        checkpoints=(
            CheckpointSpec("test_stage:checkpoint:1", 2, 7),
            CheckpointSpec("test_stage:checkpoint:2", 10, 7),
        )
    )


def _queue_lethal(runtime: StageRuntime, player_id: int) -> None:
    health = runtime.world.get_component(player_id, Health)
    queue = runtime.world.resources["damage_queue"]
    assert isinstance(queue, list)
    queue.append(
        DamageRecord(
            source_id=0,
            target_id=player_id,
            amount=health.maximum,
            knockback_x=0.0,
            knockback_y=-220.0,
            guard_break=True,
        )
    )


def test_first_checkpoint_is_active_and_later_activation_is_one_shot() -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    player_id = runtime.player_entities[1]

    initial = runtime.snapshot()
    assert tuple((view.checkpoint_id, view.is_active) for view in initial.checkpoints) == (
        ("test_stage:checkpoint:1", True),
        ("test_stage:checkpoint:2", False),
    )

    transform = runtime.world.get_component(player_id, Transform)
    transform.x = 10 * runtime.stage.tile_size
    transform.y = 7 * runtime.stage.tile_size
    runtime.world.get_component(player_id, Velocity).vx = 0.0
    runtime.world.get_component(player_id, Velocity).vy = 0.0

    activated = runtime.step(InputFrame.empty())
    repeated = runtime.step(InputFrame.empty())

    assert [event.topic for event in activated.events] == ["CheckpointReached"]
    assert dict(activated.events[0].payload) == {
        "frame_index": 0,
        "checkpoint_id": "test_stage:checkpoint:2",
        "player_id": player_id,
        "slot": 1,
    }
    assert tuple((view.checkpoint_id, view.is_active) for view in activated.view.checkpoints) == (
        ("test_stage:checkpoint:1", False),
        ("test_stage:checkpoint:2", True),
    )
    assert repeated.events == ()


def test_solo_goal_creates_exact_result_once_and_freezes_world() -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    player_id = runtime.player_entities[1]
    _, _, goal_transform = runtime.world.query(StageGoal, Transform)[0]
    player = runtime.world.get_component(player_id, Transform)
    player.x = goal_transform.x
    player.y = goal_transform.y

    completed = runtime.step(InputFrame.empty())

    expected = StageResult(
        stage_id="test_stage",
        world_id="test_world",
        node_id="test_node",
        clear_time_ms=16,
        collected_mote_ids=(),
        discovered_ability_ids=(),
        active_slots=(1,),
        deaths_by_slot=((1, 0),),
    )
    assert completed.view.outcome is StageOutcome.COMPLETED
    assert completed.result is expected or completed.result == expected
    assert runtime.result is completed.result
    assert [event.topic for event in completed.events] == ["StageCompleted"]
    assert dict(completed.events[0].payload) == {
        "frame_index": 0,
        "stage_id": "test_stage",
        "node_id": "test_node",
        "clear_time_ms": 16,
        "collected_mote_ids": (),
    }

    frozen_hash = runtime.world.world_hash()
    frozen_rng = runtime.world.rng.state_hash()
    frozen_frame = runtime.world.frame_index
    repeated = runtime.step(InputFrame.empty())

    assert repeated.result is completed.result
    assert repeated.view == completed.view
    assert repeated.events == ()
    assert runtime.world.frame_index == frozen_frame
    assert runtime.world.world_hash() == frozen_hash
    assert runtime.world.rng.state_hash() == frozen_rng


@pytest.mark.parametrize(
    "boundary",
    ("runtime_result", "snapshot", "terminal_step", "world_hash"),
)
def test_forged_clear_time_is_rejected_at_every_frozen_result_boundary(
    boundary: str,
) -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    player = runtime.world.get_component(runtime.player_entities[1], Transform)
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    player.x, player.y = goal.x, goal.y
    completed = runtime.step(InputFrame.empty())
    authentic = completed.result
    assert authentic is not None
    assert authentic.clear_time_ms == 16
    assert runtime.result is authentic
    assert runtime.world.resources["stage_result"] is authentic

    runtime.world.resources["stage_result"] = replace(
        authentic,
        clear_time_ms=160_016,
    )

    with pytest.raises(ValueError, match="clear_time_ms"):
        if boundary == "runtime_result":
            _ = runtime.result
        elif boundary == "snapshot":
            runtime.snapshot()
        elif boundary == "terminal_step":
            runtime.step(InputFrame.empty())
        else:
            runtime.world.world_hash()


def test_completed_result_resource_cannot_replace_the_frozen_authority() -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    player = runtime.world.get_component(runtime.player_entities[1], Transform)
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    player.x, player.y = goal.x, goal.y
    authentic = runtime.step(InputFrame.empty()).result
    assert authentic is not None
    equal_replacement = replace(authentic)
    assert equal_replacement == authentic
    assert equal_replacement is not authentic

    runtime.world.resources["stage_result"] = equal_replacement

    with pytest.raises(ValueError, match="frozen StageResult authority"):
        runtime.snapshot()


def test_final_non_boss_scheduler_matches_canonical_order() -> None:
    runtime = make_runtime(stage=_checkpoint_stage())

    names = tuple(type(system).__name__ for system in runtime.world.scheduler.systems)

    assert names == (
        "InputCommandSystem",
        "DefenseSystem",
        "MovementSystem",
        "EnemyAISystem",
        "CollisionSystem",
        "CaptureSystem",
        "AbilitySystem",
        "AttackSpawnSystem",
        "AttackMotionSystem",
        "CombatSystem",
        "DamageSystem",
        "InteractionSystem",
        "PickupSystem",
        "CheckpointSystem",
        "CoopRespawnSystem",
        "StageGoalSystem",
        "CameraSystem",
    )
    assert names == tuple(system_type.__name__ for system_type in runtime.SYSTEM_ORDER)
    assert names.count("AttackMotionSystem") == 1


def test_all_required_active_players_die_once_and_failure_freezes() -> None:
    players = (make_active_player(1, leader=True), make_active_player(2))
    runtime = make_runtime(players=players, stage=_checkpoint_stage())
    first = runtime.player_entities[1]
    second = runtime.player_entities[2]

    _queue_lethal(runtime, first)
    first_defeat = runtime.step(InputFrame.empty())
    assert first_defeat.view.outcome is StageOutcome.RUNNING

    _queue_lethal(runtime, second)
    failed = runtime.step(InputFrame.empty())

    assert failed.view.outcome is StageOutcome.FAILED
    assert failed.result is None
    assert [event.topic for event in failed.events][-3:] == [
        "PlayerDefeated",
        "actor_dead",
        "StageFailed",
    ]
    assert dict(failed.events[-1].payload) == {
        "frame_index": 1,
        "stage_id": "test_stage",
        "node_id": "test_node",
        "active_slots": (1, 2),
    }
    assert runtime.world.resources["deaths_by_slot"] == {1: 1, 2: 1}
    assert tuple(runtime.world.get_component(runtime.player_entities[slot], PlayerSlot).lives for slot in (1, 2)) == (
        3,
        3,
    )

    frozen_frame = runtime.world.frame_index
    frozen_hash = runtime.world.world_hash()
    repeated = runtime.step(InputFrame.empty())
    assert repeated.events == ()
    assert repeated.view == failed.view
    assert runtime.world.frame_index == frozen_frame
    assert runtime.world.world_hash() == frozen_hash


def test_authored_first_stage_bottom_fall_reaches_failed_instead_of_hanging() -> None:
    config = GameConfig()
    stage = load_catalog_bundle(config.content_dir).campaign.stages["world_1_stage_1"]
    runtime = StageRuntime(
        config,
        stage,
        create_default_registry(config.content_dir),
        (make_active_player(1, leader=True),),
        seed=77,
    )
    player_id = runtime.player_entities[1]
    collider = runtime.world.get_component(player_id, Collider)
    transform = runtime.world.get_component(player_id, Transform)
    transform.x = float(31 * stage.tile_size)
    transform.y = float(stage.pixel_height - collider.height)
    runtime.world.get_component(player_id, Velocity).vy = 160.0

    first = runtime.step(InputFrame.empty())
    second = runtime.step(InputFrame.empty())

    assert first.view.outcome is StageOutcome.RUNNING
    assert second.view.outcome is StageOutcome.FAILED
    assert [event.topic for event in second.events][-3:] == [
        "PlayerDefeated",
        "actor_dead",
        "StageFailed",
    ]
    assert runtime.can_retry_checkpoint is True

    retried = runtime.retry_from_checkpoint()
    assert retried.outcome is StageOutcome.RUNNING
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    transform.x, transform.y = goal.x, goal.y
    cleared = runtime.step(InputFrame.empty())
    assert cleared.view.outcome is StageOutcome.COMPLETED
    assert cleared.result is not None
    assert cleared.result.clear_time_ms == 48
    assert cleared.result.deaths_by_slot == ((1, 1),)
    assert runtime.world.get_component(player_id, PlayerSlot).lives == 2


def test_checkpoint_retry_charges_one_life_and_restores_player_state() -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    player_id = runtime.player_entities[1]
    transform = runtime.world.get_component(player_id, Transform)
    transform.x = 10 * runtime.stage.tile_size
    transform.y = 7 * runtime.stage.tile_size
    runtime.step(InputFrame.empty())
    _queue_lethal(runtime, player_id)
    runtime.step(InputFrame.empty())
    assert runtime.snapshot().outcome is StageOutcome.FAILED

    health = runtime.world.get_component(player_id, Health)
    velocity = runtime.world.get_component(player_id, Velocity)
    defense = runtime.world.get_component(player_id, DefenseState)
    state = runtime.world.get_component(player_id, ActorState)
    respawn = runtime.world.get_component(player_id, Respawn)
    intent = runtime.world.get_component(player_id, ControlIntent)
    velocity.vx, velocity.vy = 123.0, 456.0
    defense.guarding = True
    defense.dodge_remaining_ms = 48
    defense.dodge_cooldown_ms = 200
    state.name, state.timer_ms = "Dead", 77
    respawn.timer_ms = 400
    intent.move_axis = 1
    runtime.world.events.publish("StaleEvent", {"value": 1})
    before_lives = runtime.world.get_component(player_id, PlayerSlot).lives

    retried = runtime.retry_from_checkpoint()

    assert retried.outcome is StageOutcome.RUNNING
    assert runtime.world.get_component(player_id, PlayerSlot).lives == before_lives - 1
    assert (transform.x, transform.y) == (320.0, 224.0)
    assert (health.current, health.dead, health.invulnerable_ms) == (
        health.maximum,
        False,
        runtime.config.respawn_invulnerable_ms,
    )
    assert velocity == Velocity()
    assert defense == DefenseState()
    assert state == ActorState("Idle")
    assert respawn == Respawn(320.0, 224.0)
    assert intent == ControlIntent()
    assert [event.topic for event in runtime.world.events.peek()] == ["PlayerRespawned"]
    assert runtime.can_retry_checkpoint is False


def test_checkpoint_retry_validates_every_life_before_mutating_any_player() -> None:
    players = (make_active_player(1, leader=True), make_active_player(2))
    runtime = make_runtime(players=players, stage=_checkpoint_stage())
    for player_id in runtime.player_entities.values():
        _queue_lethal(runtime, player_id)
    runtime.step(InputFrame.empty())
    first_slot = runtime.world.get_component(runtime.player_entities[1], PlayerSlot)
    second_slot = runtime.world.get_component(runtime.player_entities[2], PlayerSlot)
    first_slot.lives = 1
    second_slot.lives = 0
    before_hash = runtime.world.world_hash()
    before_rng = runtime.world.rng.state_hash()

    assert runtime.can_retry_checkpoint is False
    with pytest.raises(ValueError, match="checkpoint retry is unavailable"):
        runtime.retry_from_checkpoint()

    assert (first_slot.lives, second_slot.lives) == (1, 0)
    assert runtime.world.world_hash() == before_hash
    assert runtime.world.rng.state_hash() == before_rng
    assert runtime.world.events.peek() == []


def test_multi_player_retry_uses_safe_offsets_and_canonical_event_order() -> None:
    players = (make_active_player(3), make_active_player(1, leader=True))
    runtime = make_runtime(players=players, stage=_checkpoint_stage())
    for player_id in runtime.player_entities.values():
        _queue_lethal(runtime, player_id)
    runtime.step(InputFrame.empty())

    retried = runtime.retry_from_checkpoint()

    assert tuple(player.slot for player in retried.players) == (1, 3)
    assert tuple((player.x, player.y) for player in retried.players) == (
        (64.0, 224.0),
        (64.0, 196.0),
    )
    assert tuple(player.lives_remaining for player in retried.players) == (2, 2)
    events = runtime.world.events.peek()
    assert [event.topic for event in events] == ["PlayerRespawned", "PlayerRespawned"]
    assert [event.payload["slot"] for event in events] == [1, 3]


def test_mote_collection_records_and_publishes_its_stable_catalog_id() -> None:
    mote_id = "test_stage:mote:1"
    stage = make_stage(
        motes=(MoteSpec(mote_id, 2, 5),),
        checkpoints=(CheckpointSpec("test_stage:checkpoint:1", 2, 7),),
    )
    runtime = make_runtime(stage=stage)

    collected = runtime.step(InputFrame.empty())

    assert collected.view.collected_mote_ids == (mote_id,)
    assert runtime.world.resources["collected_mote_ids"] == {mote_id}
    assert [event.topic for event in collected.events] == ["MoteCollected"]
    assert dict(collected.events[0].payload) == {
        "frame_index": 0,
        "mote_id": mote_id,
        "player_id": runtime.player_entities[1],
        "slot": 1,
    }


@pytest.mark.parametrize(
    ("resource", "value", "message"),
    (
        (
            "collected_mote_ids",
            ["test_stage:mote:1", "test_stage:mote:1"],
            "collected_mote_ids must not contain duplicate IDs",
        ),
        (
            "collected_mote_ids",
            {"future_stage:mote:1"},
            "collected mote IDs are not authored for test_stage",
        ),
        (
            "discovered_ability_ids",
            {"future_ability"},
            "discovered ability IDs are not authored for test_stage",
        ),
    ),
)
def test_result_facts_are_rejected_before_completion_is_published(
    resource: str,
    value: object,
    message: str,
) -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    runtime.world.resources[resource] = value
    transform = runtime.world.get_component(runtime.player_entities[1], Transform)
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    transform.x, transform.y = goal.x, goal.y

    with pytest.raises((TypeError, ValueError), match=message):
        runtime.step(InputFrame.empty())

    assert runtime.world.resources["stage_outcome"] is StageOutcome.RUNNING
    assert runtime.world.resources["stage_result"] is None
    assert all(event.topic != "StageCompleted" for event in runtime.world.events.peek())


@pytest.mark.parametrize("boundary", ("snapshot", "step", "world_hash"))
@pytest.mark.parametrize(
    ("collected", "run_motes", "message"),
    (
        (
            {"future_stage:mote:99"},
            1,
            "collected mote IDs are not authored for test_stage",
        ),
        (
            ["test_stage:mote:1", "test_stage:mote:1"],
            2,
            "collected_mote_ids must not contain duplicate IDs",
        ),
        (
            {"test_stage:mote:1"},
            0,
            "run_energy_spheres must exactly count collected stable mote IDs",
        ),
    ),
)
def test_mote_resources_are_catalog_bound_before_every_runtime_boundary(
    boundary: str,
    collected: object,
    run_motes: int,
    message: str,
) -> None:
    stage = make_stage(
        motes=(MoteSpec("test_stage:mote:1", 15, 5),),
        checkpoints=(CheckpointSpec("test_stage:checkpoint:1", 2, 7),),
    )
    runtime = make_runtime(stage=stage)
    runtime.world.resources["collected_mote_ids"] = collected
    runtime.world.resources["run_energy_spheres"] = run_motes
    before = (
        runtime.world.frame_index,
        runtime.world.rng.state_hash(),
        runtime.world.get_component(runtime.player_entities[1], Transform).x,
    )

    with pytest.raises((TypeError, ValueError), match=message):
        if boundary == "snapshot":
            runtime.snapshot()
        elif boundary == "step":
            runtime.step(InputFrame.empty())
        else:
            runtime.world.world_hash()

    assert (
        runtime.world.frame_index,
        runtime.world.rng.state_hash(),
        runtime.world.get_component(runtime.player_entities[1], Transform).x,
    ) == before


@pytest.mark.parametrize("corruption", ("missing_resource", "duplicate_id", "two_active"))
def test_checkpoint_corruption_is_rejected_before_input_or_frame_mutation(
    corruption: str,
) -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    checkpoints = runtime.world.query(Checkpoint)
    if corruption == "missing_resource":
        runtime.world.resources.pop("active_checkpoint_id")
    elif corruption == "duplicate_id":
        checkpoints[1][1].checkpoint_id = checkpoints[0][1].checkpoint_id
    else:
        checkpoints[1][1].active = True
    player = runtime.world.get_component(runtime.player_entities[1], Transform)
    before = (runtime.world.frame_index, player.x, player.y, runtime.world.rng.state_hash())

    with pytest.raises((TypeError, ValueError)):
        runtime.step(InputFrame.empty())

    assert (runtime.world.frame_index, player.x, player.y, runtime.world.rng.state_hash()) == before


@pytest.mark.parametrize(
    ("value", "active_slots", "error"),
    (
        (None, (1,), TypeError),
        ({True: 0}, (1,), ValueError),
        ({1: True}, (1,), ValueError),
        ({1: 0}, (1, 2), ValueError),
    ),
)
def test_death_counter_validation_rejects_bool_and_partial_state(
    value: object,
    active_slots: tuple[int, ...],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        validate_deaths_by_slot(value, active_slots)


@pytest.mark.parametrize(
    "checkpoints",
    (
        (),
        (
            CheckpointSpec("test_stage:checkpoint:1", 2, 7),
            CheckpointSpec("test_stage:checkpoint:1", 10, 7),
        ),
        (
            CheckpointSpec("test_stage:checkpoint:1", 2, 7),
            CheckpointSpec("test_stage:checkpoint:2", 2, 7),
        ),
        (CheckpointSpec("test_stage:checkpoint:1", 2, 5),),
    ),
)
def test_runtime_rejects_missing_duplicate_or_unsupported_checkpoint_geometry(
    checkpoints: tuple[CheckpointSpec, ...],
) -> None:
    with pytest.raises(ValueError):
        make_runtime(stage=make_stage(checkpoints=checkpoints))


def test_goal_system_rejects_invalid_resources_and_goal_identity() -> None:
    invalid_outcome = make_runtime(stage=_checkpoint_stage())
    invalid_outcome.world.resources["stage_outcome"] = "running"
    with pytest.raises(TypeError, match="stage_outcome"):
        StageGoalSystem().update(invalid_outcome.world, 16)

    invalid_stage = make_runtime(stage=_checkpoint_stage())
    invalid_stage.world.resources["stage_spec"] = object()
    with pytest.raises(TypeError, match="stage_spec"):
        StageGoalSystem().update(invalid_stage.world, 16)

    no_players = make_runtime(stage=_checkpoint_stage())
    no_players.world.resources["active_players"] = ()
    StageGoalSystem().update(no_players.world, 16)
    assert no_players.world.resources["stage_outcome"] is StageOutcome.RUNNING

    missing_goal = make_runtime(stage=_checkpoint_stage())
    missing_goal.world.destroy_entity(missing_goal.world.query(StageGoal)[0][0])
    with pytest.raises(RuntimeError, match="exactly one goal"):
        StageGoalSystem().update(missing_goal.world, 16)

    wrong_goal = make_runtime(stage=_checkpoint_stage())
    goal = wrong_goal.world.query(StageGoal)[0][1]
    goal.stage_id = "other_stage"
    with pytest.raises(ValueError, match="identity"):
        StageGoalSystem().update(wrong_goal.world, 16)


def test_boss_goal_rejects_forged_defeat_state_with_live_health() -> None:
    config = GameConfig()
    stage = load_catalog_bundle(config.content_dir).campaign.stages["world_1_stage_5"]
    runtime = StageRuntime(
        config,
        stage,
        create_default_registry(config.content_dir),
        (make_active_player(1, leader=True),),
        seed=77,
    )
    boss_id, boss_state, boss_health = runtime.world.query(BossState, Health)[0]
    runtime.world.add_component(boss_id, replace(boss_state, defeated=True))
    assert boss_health.dead is False

    with pytest.raises(ValueError, match="defeat state"):
        StageGoalSystem().update(runtime.world, 16)


def test_removed_inactive_player_cannot_suppress_all_active_failure() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1, p2), stage=_checkpoint_stage())
    removed_id = runtime.player_entities[2]
    runtime.sync_active_players((p1,))
    assert removed_id not in runtime.world.alive_entities

    _queue_lethal(runtime, runtime.player_entities[1])
    failed = runtime.step(InputFrame.empty())

    assert failed.view.outcome is StageOutcome.FAILED
    assert dict(failed.events[-1].payload)["active_slots"] == (1,)
    assert runtime.world.resources["deaths_by_slot"] == {1: 1}


def test_dead_required_coop_player_cannot_trigger_or_be_ignored_by_goal() -> None:
    players = (make_active_player(1, leader=True), make_active_player(2))
    runtime = make_runtime(players=players, stage=_checkpoint_stage())
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    for player_id in runtime.player_entities.values():
        transform = runtime.world.get_component(player_id, Transform)
        transform.x, transform.y = goal.x, goal.y
    _queue_lethal(runtime, runtime.player_entities[2])

    frame = runtime.step(InputFrame.empty())

    assert frame.view.outcome is StageOutcome.RUNNING
    assert "StageCompleted" not in [event.topic for event in frame.events]
    assert runtime.world.get_component(runtime.player_entities[2], Health).dead is True


def test_retry_clears_capture_combat_input_and_stale_event_state() -> None:
    runtime = make_runtime(stage=_checkpoint_stage())
    player_id = runtime.player_entities[1]
    _queue_lethal(runtime, player_id)
    runtime.step(InputFrame.empty())
    assert runtime.snapshot().outcome is StageOutcome.FAILED

    enemy_id = runtime.world.create_entity()
    runtime.world.add_component(enemy_id, Transform(100.0, 100.0))
    runtime.world.add_component(enemy_id, Velocity(20.0, 30.0))
    runtime.world.add_component(enemy_id, Collider(20, 20, solid=False))
    runtime.world.add_component(enemy_id, CapturedBy(player_id))
    capture = runtime.world.get_component(player_id, CaptureState)
    capture.phase = "holding"
    capture.captured_entity_id = enemy_id
    capture.captured_ability_id = "cinder"
    capture.captured_visual_id = "emberling"

    attack_id = runtime.world.create_entity()
    runtime.world.add_component(
        attack_id,
        Attack(
            owner_entity_id=player_id,
            team="player",
            attack_kind="stale",
            visual_id="stale",
            damage=1,
            knockback_x=0.0,
            knockback_y=0.0,
            ttl_ms=100,
            pierce_remaining=0,
            cuts_projectiles=False,
            guard_break=False,
            pull_strength=0.0,
            interaction_kind=None,
            born_frame=runtime.world.frame_index,
        ),
    )
    runtime.world.resources["damage_queue"] = [DamageRecord(0, player_id, 1, 0.0, 0.0, True)]
    runtime.world.resources["attack_requests"] = [
        AttackRequest(
            owner_entity_id=player_id,
            team="player",
            ability_id="none",
            attack_kind="stale_request",
            visual_id="stale_request",
            x=0.0,
            y=0.0,
            width=10,
            height=10,
            vx=0.0,
            vy=0.0,
            damage=1,
            knockback_x=0.0,
            knockback_y=0.0,
            ttl_ms=16,
        )
    ]
    runtime.world.resources["pending_enemy_launches"] = [PendingEnemyLaunch(player_id, enemy_id)]
    runtime.world.frame_input = object()
    runtime.world.events.publish("StaleEvent", {"value": 1})
    rng_before = runtime.world.rng.state_hash()

    runtime.retry_from_checkpoint()

    assert capture == CaptureState()
    assert runtime.world.try_component(enemy_id, CapturedBy) is None
    assert runtime.world.get_component(enemy_id, Collider).solid is True
    assert runtime.world.get_component(enemy_id, Velocity) == Velocity()
    assert attack_id not in runtime.world.alive_entities
    assert runtime.world.resources["damage_queue"] == []
    assert runtime.world.resources["attack_requests"] == []
    assert runtime.world.resources["pending_enemy_launches"] == []
    assert runtime.world.resources["boss_commands"] == ()
    assert runtime.world.frame_input == InputFrame.empty()
    assert [event.topic for event in runtime.world.events.peek()] == ["PlayerRespawned"]
    assert runtime.world.rng.state_hash() == rng_before


def test_result_sorts_valid_catalog_facts_and_rejects_tampering() -> None:
    stage = make_stage(
        enemy_spawns=(
            EnemySpawn(200.0, 160.0, "grunt", "cinder", 180.0, 240.0),
            EnemySpawn(240.0, 160.0, "grunt", "galehook", 220.0, 280.0),
        ),
        motes=(
            MoteSpec("test_stage:mote:1", 4, 5),
            MoteSpec("test_stage:mote:2", 6, 5),
        ),
        checkpoints=(CheckpointSpec("test_stage:checkpoint:1", 2, 7),),
    )
    runtime = make_runtime(stage=stage)
    runtime.world.resources["run_energy_spheres"] = 2
    runtime.world.resources["collected_mote_ids"] = [
        "test_stage:mote:2",
        "test_stage:mote:1",
    ]
    runtime.world.resources["discovered_ability_ids"] = ["galehook", "cinder"]
    runtime.world.resources["deaths_by_slot"] = {1: 2}
    player = runtime.world.get_component(runtime.player_entities[1], Transform)
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    player.x, player.y = goal.x, goal.y

    completed = runtime.step(InputFrame.empty())

    assert completed.result is not None
    assert completed.result.collected_mote_ids == (
        "test_stage:mote:1",
        "test_stage:mote:2",
    )
    assert completed.result.discovered_ability_ids == ("cinder", "galehook")
    assert completed.result.deaths_by_slot == ((1, 2),)
    runtime.world.resources["stage_result"] = replace(
        completed.result,
        active_slots=(2,),
    )
    with pytest.raises(ValueError, match="exactly match gameplay-owned"):
        runtime.snapshot()
