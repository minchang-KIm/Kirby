"""Visible, deterministic, exactly-once attack pipeline contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tests.helpers.gameplay import frame, make_runtime, make_stage
from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.bosses import BossCommand, BossState
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    Attack,
    AttackRequest,
    Collider,
    DamageRecord,
    DefenseState,
    EnemyAI,
    Facing,
    Health,
    PendingEnemyLaunch,
    PlayerSlot,
    Projectile,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.systems import (
    AttackMotionSystem,
    AttackSpawnSystem,
    CollisionSystem,
    CombatSystem,
    DamageSystem,
)
from windsprig.input.commands import AbilityUseCommand, InputFrame


def _add(world: World, *components: object) -> int:
    entity_id = world.create_entity()
    for component in components:
        world.add_component(entity_id, component)
    return entity_id


def _request(
    owner: int,
    *,
    ability_id: str = "cinder",
    attack_kind: str = "charged_ember",
    x: float = 10.0,
    y: float = 10.0,
    vx: float = 100.0,
    vy: float = 0.0,
    damage: int = 2,
    ttl_ms: int = 100,
    pierce: int = 0,
    cuts_projectiles: bool = False,
    pull_strength: float = 0.0,
    interaction_kind: str | None = None,
) -> AttackRequest:
    return AttackRequest(
        owner_entity_id=owner,
        team="player",
        ability_id=ability_id,
        attack_kind=attack_kind,
        visual_id=f"{attack_kind}_visual",
        x=x,
        y=y,
        width=20,
        height=20,
        vx=vx,
        vy=vy,
        damage=damage,
        knockback_x=40.0,
        knockback_y=-20.0,
        ttl_ms=ttl_ms,
        pierce=pierce,
        cuts_projectiles=cuts_projectiles,
        pull_strength=pull_strength,
        interaction_kind=interaction_kind,
    )


def _attack(
    owner: int,
    *,
    team: str = "player",
    kind: str = "probe",
    damage: int = 2,
    ttl_ms: int = 100,
    pierce: int = 0,
    cuts: bool = False,
    pull: float = 0.0,
    interaction: str | None = None,
    born_frame: int = 0,
) -> Attack:
    return Attack(
        owner_entity_id=owner,
        team=team,
        attack_kind=kind,
        visual_id=f"{kind}_visual",
        damage=damage,
        knockback_x=40.0,
        knockback_y=-20.0,
        ttl_ms=ttl_ms,
        pierce_remaining=pierce,
        cuts_projectiles=cuts,
        guard_break=False,
        pull_strength=pull,
        interaction_kind=interaction,
        born_frame=born_frame,
    )


def _motion_world() -> World:
    world = World()
    world.resources["stage_spec"] = make_stage()
    return world


def _combat_world() -> World:
    world = World()
    world.resources["damage_queue"] = []
    world.resources["attack_requests"] = []
    return world


def test_new_projectile_is_visible_and_advances_once_on_birth_step() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    runtime.world.get_component(player, AbilityState).current_id = "cinder"
    start_x = runtime.world.get_component(player, Transform).x + 20.0

    result = runtime.step(frame(1, AbilityUseCommand(player_slot=1, released=True)))

    assert len(result.view.attacks) == 1
    view = result.view.attacks[0]
    component = runtime.world.get_component(view.entity_id, Attack)
    velocity = runtime.world.get_component(view.entity_id, Velocity)
    assert view.x == pytest.approx(start_x + velocity.vx * 0.016)
    assert component.last_advanced_frame == result.simulation.frame_index
    assert [event.topic for event in result.events][:2] == ["AttackSpawned", "AbilityUsed"]
    assert result.events[1].payload["attack_ids"] == (view.entity_id,)
    assert runtime.world.resources["attack_requests"] == []


def test_spawn_uses_real_launch_id_and_does_not_publish_ability_used_for_none() -> None:
    world = _motion_world()
    owner = _add(world, Transform(0.0, 0.0))
    world.resources["attack_requests"] = [_request(owner, ability_id="none", attack_kind="launched_enemy")]
    world.resources["pending_enemy_launches"] = [PendingEnemyLaunch(owner, 77)]
    world.resources["boss_commands"] = ()

    AttackSpawnSystem().update(world, 16)

    attack_id = world.query(Attack)[0][0]
    assert [event.topic for event in world.events.peek()] == ["AttackSpawned", "EnemyLaunched"]
    assert world.events.peek()[1].payload == {
        "frame_index": 0,
        "player_id": owner,
        "enemy_id": 77,
        "attack_id": attack_id,
    }
    assert world.resources["pending_enemy_launches"] == []


def test_motion_rejects_double_advance_and_expires_ttl_and_bounds() -> None:
    world = _motion_world()
    owner = _add(world, Transform(50.0, 50.0))
    live = _add(
        world,
        _attack(owner, ttl_ms=32),
        Transform(10.0, 10.0),
        Velocity(),
        Collider(10, 10, solid=False),
        Team("player"),
    )
    expired = _add(
        world,
        _attack(owner, ttl_ms=16),
        Transform(20.0, 20.0),
        Velocity(),
        Collider(10, 10, solid=False),
        Team("player"),
    )
    outside = _add(
        world,
        _attack(owner, ttl_ms=100),
        Transform(700.0, 20.0),
        Velocity(),
        Collider(10, 10, solid=False),
        Team("player"),
    )
    boundary = _add(
        world,
        _attack(owner, ttl_ms=100),
        Transform(float(make_stage().pixel_width), 20.0),
        Velocity(),
        Collider(10, 10, solid=False),
        Team("player"),
    )
    system = AttackMotionSystem()

    system.update(world, 16)

    assert world.get_component(live, Attack).ttl_ms == 16
    assert expired not in world.alive_entities
    assert outside not in world.alive_entities
    assert boundary not in world.alive_entities
    with pytest.raises(AssertionError, match="advanced twice"):
        system.update(world, 16)


def test_collision_skips_attack_before_the_single_motion_owner_advances_it() -> None:
    world = _motion_world()
    world.resources["collision_world"] = make_stage().build_collision_world()
    owner = _add(world, Transform(0.0, 0.0))
    attack_id = _add(
        world,
        _attack(owner),
        Transform(10.0, 10.0),
        Velocity(100.0, 0.0),
        Collider(10, 10, solid=False),
        Team("player"),
        Projectile(owner=owner, tag="legacy_overlap", damage=1, ttl_ms=100),
    )

    CollisionSystem().update(world, 16)
    AttackMotionSystem().update(world, 16)
    CombatSystem().update(world, 16)

    assert world.get_component(attack_id, Transform).x == pytest.approx(11.6)
    assert world.get_component(attack_id, Projectile).ttl_ms == 100


def test_galehook_reverses_at_frame_23_and_homes_toward_owner() -> None:
    world = _motion_world()
    owner = _add(world, Transform(0.0, 0.0))
    boomerang = _add(
        world,
        _attack(owner, kind="boomerang", ttl_ms=800, pierce=2, born_frame=0),
        Transform(100.0, 0.0),
        Velocity(440.0, 0.0),
        Collider(24, 18, solid=False),
        Team("player"),
    )
    system = AttackMotionSystem()
    world.frame_index = 22
    system.update(world, 16)
    assert world.get_component(boomerang, Velocity).vx == 440.0

    world.frame_index = 23
    system.update(world, 16)

    assert world.get_component(boomerang, Velocity).vx < 0.0
    assert world.get_component(boomerang, Transform).x < 107.04


def test_motion_rejects_invalid_stage_future_frame_and_handles_missing_owner_return() -> None:
    missing_stage = World()
    with pytest.raises(TypeError, match="stage_spec"):
        AttackMotionSystem().update(missing_stage, 16)

    world = _motion_world()
    future = _attack(999)
    future.last_advanced_frame = 1
    _add(
        world,
        future,
        Transform(10.0, 10.0),
        Velocity(),
        Collider(10, 10, solid=False),
        Team("player"),
    )
    with pytest.raises(AssertionError, match="advanced beyond"):
        AttackMotionSystem().update(world, 16)

    future.last_advanced_frame = -1
    future.attack_kind = "boomerang"
    world.frame_index = 23
    velocity = world.query(Attack, Velocity)[0][2]
    velocity.vx = 100.0
    AttackMotionSystem().update(world, 16)
    assert velocity.vx == -100.0


def test_galehook_stops_when_it_reaches_owner() -> None:
    world = _motion_world()
    owner = _add(world, Transform(20.0, 20.0))
    boomerang = _add(
        world,
        _attack(owner, kind="boomerang", born_frame=0),
        Transform(20.0, 20.0),
        Velocity(100.0, 0.0),
        Collider(10, 10, solid=False),
        Team("player"),
    )
    world.frame_index = 23

    AttackMotionSystem().update(world, 16)

    assert world.get_component(boomerang, Velocity) == Velocity()


def test_full_scheduler_preserves_stationary_attacks_and_authored_gale_motion() -> None:
    runtime = make_runtime()
    owner = runtime.player_entities[1]
    owner_transform = runtime.world.get_component(owner, Transform)
    owner_collider = runtime.world.get_component(owner, Collider)
    owner_transform.y = 228.0
    owner_collider.on_ground = True
    runtime.world.resources["attack_requests"] = [
        _request(
            owner,
            ability_id="none",
            attack_kind="burn_zone",
            x=300.0,
            y=100.0,
            vx=0.0,
            vy=0.0,
            ttl_ms=960,
            pierce=10_000,
        ),
        _request(
            owner,
            ability_id="none",
            attack_kind="boomerang",
            x=200.0,
            y=228.0,
            vx=440.0,
            vy=0.0,
            ttl_ms=800,
            pierce=2,
            pull_strength=260.0,
        ),
    ]

    runtime.step(InputFrame.empty())
    by_kind = {attack.attack_kind: entity_id for entity_id, attack in runtime.world.query(Attack)}
    burn_id = by_kind["burn_zone"]
    gale_id = by_kind["boomerang"]

    for _ in range(22):
        runtime.step(InputFrame.empty())
        assert runtime.world.get_component(burn_id, Transform).y == 100.0
        assert runtime.world.get_component(burn_id, Velocity) == Velocity()
        assert runtime.world.get_component(gale_id, Velocity) == Velocity(440.0, 0.0)

    before_return = runtime.world.get_component(gale_id, Transform).x
    runtime.step(InputFrame.empty())

    assert runtime.world.get_component(burn_id, Transform).y == 100.0
    assert runtime.world.get_component(burn_id, Velocity) == Velocity()
    assert runtime.world.get_component(gale_id, Velocity) == Velocity(-440.0, 0.0)
    assert runtime.world.get_component(gale_id, Transform).x < before_return


def test_overlap_hits_each_target_once_and_pierces_in_entity_order() -> None:
    world = _combat_world()
    owner = _add(world, Transform(0.0, 0.0), Team("player"))
    targets = [
        _add(
            world,
            Team("enemy"),
            Transform(10.0, 10.0),
            Collider(20, 20),
            Health(5, 5),
            Velocity(),
            EnemyAI("grunt", 0.0, 100.0),
        )
        for _ in range(3)
    ]
    attack_id = _add(
        world,
        _attack(owner, pierce=1),
        Team("player"),
        Transform(10.0, 10.0),
        Collider(20, 20, solid=False),
        Velocity(),
    )
    system = CombatSystem()

    system.update(world, 16)
    queued = world.resources["damage_queue"]

    assert isinstance(queued, list)
    assert [(item.attack_id, item.target_id) for item in queued] == [
        (attack_id, targets[0]),
        (attack_id, targets[1]),
    ]
    assert attack_id not in world.alive_entities
    system.update(world, 16)
    assert len(queued) == 2


def test_bloomblade_cuts_hostile_moving_attack_without_hurting_player() -> None:
    world = _combat_world()
    player = _add(
        world,
        Team("player"),
        Transform(10.0, 10.0),
        Collider(20, 20),
        Health(10, 10),
    )
    cutter = _add(
        world,
        _attack(player, kind="melee_arc", cuts=True),
        Team("player"),
        Transform(10.0, 10.0),
        Collider(30, 30, solid=False),
        Velocity(),
    )
    hostile = _add(
        world,
        _attack(999, team="enemy", kind="hostile_bolt"),
        Team("enemy"),
        Transform(12.0, 12.0),
        Collider(8, 8, solid=False),
        Velocity(-100.0, 0.0),
    )

    CombatSystem().update(world, 16)

    assert hostile not in world.alive_entities
    assert world.get_component(player, Health).current == 10
    assert world.resources["damage_queue"] == []
    event = world.events.peek()[0]
    assert event.topic == "ProjectileCut"
    assert event.payload == {
        "frame_index": 0,
        "cutter_attack_id": cutter,
        "projectile_attack_id": hostile,
    }


def test_cinder_hit_queues_one_exact_stationary_burn_zone() -> None:
    world = _combat_world()
    owner = _add(world, Transform(0.0, 0.0), Team("player"))
    _add(
        world,
        Team("enemy"),
        Transform(20.0, 20.0),
        Collider(20, 20),
        Health(5, 5),
    )
    _add(
        world,
        _attack(owner, kind="charged_ember", interaction="spawn_burn_zone"),
        Team("player"),
        Transform(20.0, 20.0),
        Collider(20, 20, solid=False),
        Velocity(),
    )

    CombatSystem().update(world, 16)

    requests = world.resources["attack_requests"]
    assert isinstance(requests, list)
    assert len(requests) == 1
    burn = requests[0]
    assert (
        burn.ability_id,
        burn.attack_kind,
        burn.visual_id,
        burn.width,
        burn.height,
        burn.vx,
        burn.vy,
        burn.damage,
        burn.ttl_ms,
    ) == ("none", "burn_zone", "cinder_burn_zone", 48, 30, 0.0, 0.0, 1, 960)


def test_voltsong_and_tempest_queue_targets_by_distance_then_entity_id() -> None:
    world = _combat_world()
    owner = _add(world, Transform(0.0, 0.0), Team("player"))
    farther = _add(world, Team("enemy"), Transform(40.0, 0.0), Collider(10, 10), Health(20, 20))
    tied_low = _add(world, Team("enemy"), Transform(20.0, 0.0), Collider(10, 10), Health(20, 20))
    tied_high = _add(world, Team("enemy"), Transform(0.0, 20.0), Collider(10, 10), Health(20, 20))
    _add(
        world,
        _attack(owner, kind="chain_pulse", pierce=2),
        Team("player"),
        Transform(-132.0, -132.0),
        Collider(264, 264, solid=False),
        Velocity(),
    )

    CombatSystem().update(world, 16)

    queue = world.resources["damage_queue"]
    assert isinstance(queue, list)
    assert [item.target_id for item in queue] == [tied_low, tied_high, farther]

    world.resources["damage_queue"] = []
    _add(
        world,
        _attack(owner, kind="screen_tempest", pierce=10_000),
        Team("player"),
        Transform(-100.0, -100.0),
        Collider(300, 300, solid=False),
        Velocity(),
    )
    CombatSystem().update(world, 16)
    tempest_queue = world.resources["damage_queue"]
    assert isinstance(tempest_queue, list)
    assert [item.target_id for item in tempest_queue] == [tied_low, tied_high, farther]


def test_galehook_pull_affects_non_brute_only() -> None:
    world = _combat_world()
    owner = _add(world, Transform(0.0, 0.0), Team("player"))
    grunt = _add(
        world,
        Team("enemy"),
        Transform(20.0, 0.0),
        Collider(10, 10),
        Health(5, 5),
        Velocity(),
        EnemyAI("grunt", 0.0, 100.0),
    )
    brute = _add(
        world,
        Team("enemy"),
        Transform(30.0, 0.0),
        Collider(10, 10),
        Health(5, 5),
        Velocity(),
        EnemyAI("brute", 0.0, 100.0),
    )
    _add(
        world,
        _attack(owner, kind="boomerang", pierce=1, pull=260.0),
        Team("player"),
        Transform(10.0, 0.0),
        Collider(40, 20, solid=False),
        Velocity(),
    )

    CombatSystem().update(world, 16)

    assert world.get_component(grunt, Velocity).vx == -260.0
    assert world.get_component(brute, Velocity) == Velocity()


def test_attack_hit_precedes_player_damage_and_terminal_semantic_event() -> None:
    world = World()
    world.resources["config"] = GameConfig()
    attacker = _add(world, Transform(20.0, 0.0))
    player = _add(
        world,
        PlayerSlot(1, lives=2),
        Transform(0.0, 0.0),
        Velocity(),
        Collider(20, 20, on_ground=True),
        Facing(1),
        DefenseState(guarding=True),
        ActorState("Guard"),
        Health(1, 10),
    )
    world.resources["damage_queue"] = [DamageRecord(attacker, player, 2, -100.0, -50.0, False, attack_id=88)]

    DamageSystem().update(world, 0)

    events = world.events.peek()
    assert [event.topic for event in events[:3]] == [
        "AttackHit",
        "PlayerDamaged",
        "PlayerDefeated",
    ]
    assert events[0].payload == {
        "frame_index": 0,
        "attack_id": 88,
        "owner_id": attacker,
        "target_id": player,
        "damage": 1,
        "guarded": True,
    }
    assert events[2].payload == {
        "frame_index": 0,
        "entity_id": player,
        "slot": 1,
        "lives_remaining": 2,
    }


def test_dodge_suppresses_attack_hit_and_enemy_defeat_is_exactly_once() -> None:
    world = World()
    world.resources["config"] = GameConfig()
    source = _add(world, Transform(0.0, 0.0))
    dodger = _add(
        world,
        PlayerSlot(1),
        Health(5, 5),
        DefenseState(dodge_remaining_ms=160),
    )
    enemy = _add(world, Health(1, 1), ActorState())
    world.resources["damage_queue"] = [
        DamageRecord(source, dodger, 3, 0.0, 0.0, False, attack_id=1),
        DamageRecord(source, enemy, 1, 0.0, 0.0, False, attack_id=2),
        DamageRecord(source, enemy, 1, 0.0, 0.0, False, attack_id=3),
    ]

    DamageSystem().update(world, 0)

    assert [event.topic for event in world.events.peek()] == [
        "AttackHit",
        "EnemyDefeated",
        "actor_dead",
    ]


def test_spawn_consumes_only_complete_boss_geometry_and_retains_incomplete_commands() -> None:
    world = _motion_world()
    boss = _add(
        world,
        BossState("rootjaw", 1, 0, "phase", 0, "active", 1, "attack"),
        Transform(0.0, 0.0),
    )
    assert boss == 1
    complete = BossCommand(
        "execute",
        "rootjaw.complete",
        (
            ("damage", 3),
            ("cuts_projectiles", True),
            ("guard_break", True),
            ("height", 12),
            ("interaction_kind", "switch"),
            ("knockback_x", 20.0),
            ("knockback_y", -10.0),
            ("pierce", 2),
            ("pull_strength", 40.0),
            ("ttl_ms", 100),
            ("vx", 40.0),
            ("vy", 0.0),
            ("width", 16),
            ("x", 2.0),
            ("y", 3.0),
        ),
    )
    incomplete = BossCommand("execute", "rootjaw.future", (("speed", 180),))
    world.resources["attack_requests"] = []
    world.resources["pending_enemy_launches"] = []
    world.resources["boss_commands"] = tuple(sorted((incomplete, complete), key=lambda row: row.attack_id))

    AttackSpawnSystem().update(world, 16)

    spawned = world.query(Attack)
    assert len(spawned) == 1
    assert spawned[0][1].owner_entity_id == boss
    assert spawned[0][1].attack_kind == "rootjaw.complete"
    assert (
        spawned[0][1].pierce_remaining,
        spawned[0][1].cuts_projectiles,
        spawned[0][1].guard_break,
        spawned[0][1].pull_strength,
        spawned[0][1].interaction_kind,
    ) == (2, True, True, 40.0, "switch")
    assert world.resources["boss_commands"] == (incomplete,)


def test_spawn_retains_every_malformed_or_non_execute_boss_command() -> None:
    base: dict[str, bool | int | float | str] = {
        "damage": 3,
        "height": 12,
        "knockback_x": 20.0,
        "knockback_y": -10.0,
        "ttl_ms": 100,
        "vx": 40.0,
        "vy": 0.0,
        "width": 16,
        "x": 2.0,
        "y": 3.0,
    }

    def malformed(attack_id: str, key: str, value: bool | int | float | str) -> BossCommand:
        parameters = {**base, key: value}
        return BossCommand("execute", attack_id, tuple(parameters.items()))

    commands = (
        BossCommand("telegraph", "bad.command", ()),
        malformed("bad.width", "width", 16.0),
        malformed("bad.x", "x", "two"),
        malformed("bad.pierce", "pierce", True),
        malformed("bad.cuts", "cuts_projectiles", 1),
        malformed("bad.guard", "guard_break", 1),
        malformed("bad.pull", "pull_strength", "forty"),
        malformed("bad.interaction", "interaction_kind", 1),
    )
    world = _motion_world()
    boss = _add(
        world,
        BossState("rootjaw", 1, 0, "phase", 0, "active", 1, "attack"),
        Transform(0.0, 0.0),
    )
    assert boss == 1
    world.resources["attack_requests"] = []
    world.resources["pending_enemy_launches"] = []
    world.resources["boss_commands"] = commands

    AttackSpawnSystem().update(world, 16)

    assert world.query(Attack) == []
    retained = world.resources["boss_commands"]
    assert isinstance(retained, tuple)
    assert set(retained) == set(commands)


def test_attack_snapshot_is_frozen_sorted_and_reset_matches_fresh_runtime() -> None:
    runtime = make_runtime()
    owner = runtime.player_entities[1]
    runtime.world.resources["attack_requests"] = [
        _request(owner, x=30.0),
        _request(owner, attack_kind="second", x=10.0),
    ]

    result = runtime.step(InputFrame.empty())

    assert [view.entity_id for view in result.view.attacks] == sorted(view.entity_id for view in result.view.attacks)
    with pytest.raises(FrozenInstanceError):
        result.view.attacks[0].x = 999.0  # type: ignore[misc]
    mutated_hash = runtime.world.world_hash()
    reset = runtime.reset_stage()
    fresh = make_runtime()
    assert mutated_hash != fresh.world.world_hash()
    assert reset == fresh.snapshot()
    assert runtime.world.world_hash() == fresh.world.world_hash()


def test_canonical_attack_view_precedes_mixed_legacy_projectile_view() -> None:
    runtime = make_runtime()
    owner = runtime.player_entities[1]
    mixed = _add(
        runtime.world,
        _attack(owner, kind="canonical", ttl_ms=123),
        Projectile(owner=owner, tag="legacy_duplicate", damage=9, ttl_ms=999),
        Team("player"),
        Transform(20.0, 30.0),
        Collider(10, 12, solid=False),
        Velocity(-10.0, 0.0),
    )
    legacy = _add(
        runtime.world,
        Projectile(owner=owner, tag="legacy_only", damage=1, ttl_ms=77),
        Team("player"),
        Transform(40.0, 50.0),
        Collider(8, 9, solid=False),
        Velocity(),
    )

    views = runtime.snapshot().attacks

    assert [view.entity_id for view in views].count(mixed) == 1
    mixed_view = next(view for view in views if view.entity_id == mixed)
    assert (mixed_view.attack_kind, mixed_view.visual_id, mixed_view.ttl_ms) == (
        "canonical",
        "canonical_visual",
        123,
    )
    legacy_view = next(view for view in views if view.entity_id == legacy)
    assert (legacy_view.attack_kind, legacy_view.ttl_ms) == ("legacy_only", 77)


def test_damage_and_pending_launch_resources_are_strictly_validated_and_hashed() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    baseline = runtime.world.world_hash()
    runtime.world.resources["damage_queue"] = [DamageRecord(0, player, 1, 0.0, 0.0, False, attack_id=9)]
    damage_hash = runtime.world.world_hash()
    assert damage_hash != baseline

    runtime.world.resources["damage_queue"] = []
    runtime.world.resources["pending_enemy_launches"] = [PendingEnemyLaunch(player, 99)]
    assert runtime.world.world_hash() not in {baseline, damage_hash}

    for key, value, message in (
        ("damage_queue", [object()], "damage_queue"),
        ("pending_enemy_launches", (), "pending_enemy_launches"),
    ):
        runtime = make_runtime()
        runtime.world.resources[key] = value
        with pytest.raises(TypeError, match=message):
            runtime.snapshot()
        with pytest.raises(TypeError, match=message):
            runtime.world.world_hash()


def test_attack_ids_views_events_and_hashes_match_fresh_and_reset_runs() -> None:
    first = make_runtime()
    fresh = make_runtime()
    for runtime in (first, fresh):
        player = runtime.player_entities[1]
        runtime.world.get_component(player, AbilityState).current_id = "cinder"

    expected = fresh.step(frame(1, AbilityUseCommand(1, released=True)))
    actual = first.step(frame(1, AbilityUseCommand(1, released=True)))
    assert actual == expected

    first.reset_stage()
    player = first.player_entities[1]
    first.world.get_component(player, AbilityState).current_id = "cinder"
    replayed = first.step(frame(1, AbilityUseCommand(1, released=True)))
    assert replayed == expected
