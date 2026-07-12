"""Focused branch behavior for the production ECS gameplay systems."""

from __future__ import annotations

import pytest

from windsprig.config import GameConfig
from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.components import (
    NON_ENTITY_DAMAGE_SOURCE_ID,
    AbilityState,
    ActorState,
    Collectible,
    Collider,
    ControlIntent,
    DamageRecord,
    DefenseState,
    DrawState,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    Health,
    MovementState,
    PlayerSlot,
    Projectile,
    Respawn,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.systems import (
    AbilitySystem,
    CollisionSystem,
    CombatSystem,
    CoopRespawnSystem,
    DamageSystem,
    DrawSystem,
    EnemyAISystem,
    InputCommandSystem,
    MovementSystem,
    PickupSystem,
)
from windsprig.input.commands import (
    AbilityUseCommand,
    DodgeCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    GuardCommand,
    HoverCommand,
    InputFrame,
    JumpCommand,
    MoveCommand,
)
from windsprig.physics import TileCollisionWorld


def add_entity(world: World, *components: object) -> int:
    entity_id = world.create_entity()
    for component in components:
        world.add_component(entity_id, component)
    return entity_id


def stage_spec() -> StageSpec:
    return StageSpec(
        stage_id="test_stage",
        world_id="test_world",
        node_id="test_node",
        width_tiles=20,
        height_tiles=10,
        tile_size=32,
        ground_y_tile=8,
        player_spawns=((10.0, 20.0),),
        enemy_spawns=(),
        motes=(),
        checkpoints=(),
        interactions=(),
        goal_tile=(18, 8),
        hazards=(),
        one_way_tiles=(),
        solids=(),
    )


def test_ability_system_drops_one_ability_and_materializes_another_as_a_projectile() -> None:
    world = World()
    world.resources["ability_registry"] = create_default_registry(GameConfig().content_dir)
    add_entity(
        world,
        Team("enemy"),
        Transform(0, 0),
        Facing(),
        ControlIntent(ability_pressed=True),
        AbilityState(current="fire"),
        ActorState(),
    )
    dropped = add_entity(
        world,
        Team("player"),
        Transform(20, 30),
        Facing(),
        ControlIntent(drop_pressed=True),
        AbilityState(current="fire"),
        ActorState(),
    )
    caster = add_entity(
        world,
        Team("player"),
        Transform(100, 50),
        Facing(-1),
        ControlIntent(ability_pressed=True),
        AbilityState(current="ultra_sword", cooldown_ms=10),
        ActorState(),
    )

    AbilitySystem().update(world, 16)

    dropped_ability = world.get_component(dropped, AbilityState)
    caster_ability = world.get_component(caster, AbilityState)
    assert (dropped_ability.previous, dropped_ability.current, dropped_ability.is_super) == ("fire", "none", False)
    assert caster_ability.cooldown_ms == 600
    assert caster_ability.is_super is True
    projectile_rows = world.query(Projectile, Team, Transform, Velocity, Collider)
    assert len(projectile_rows) == 1
    _, projectile, team, transform, velocity, collider = projectile_rows[0]
    assert projectile.owner == caster
    assert projectile.tag == "ultra_sword"
    assert team.name == "player"
    assert transform.x < 100
    assert velocity.vx < 0
    assert collider.solid is False
    assert world.resources["projectile_requests"] == []
    assert [event.topic for event in world.events.peek()] == ["ability_dropped", "ability_used"]


def test_combat_system_expires_projectiles_and_queues_projectile_and_contact_damage() -> None:
    world = World()
    player = add_entity(
        world,
        Team("player"),
        Transform(10, 10),
        Collider(20, 20),
        Health(5, 5),
    )
    dead_player = add_entity(
        world,
        Team("player"),
        Transform(10, 10),
        Collider(20, 20),
        Health(0, 5, dead=True),
    )
    enemy = add_entity(
        world,
        Team("enemy"),
        Transform(12, 10),
        Collider(20, 20),
        Health(5, 5),
        EnemyAI("boss", 0, 100),
    )
    add_entity(
        world,
        Team("enemy"),
        Transform(500, 500),
        Collider(20, 20),
        Health(0, 5, dead=True),
        EnemyAI("grunt", 0, 100),
    )
    expired = add_entity(
        world,
        Projectile(owner=player, tag="expired", damage=1, ttl_ms=1),
        Team("player"),
        Transform(0, 0),
        Collider(5, 5, solid=False),
        Velocity(),
    )
    colliding = add_entity(
        world,
        Projectile(owner=player, tag="hit", damage=3, ttl_ms=100),
        Team("player"),
        Transform(12, 10),
        Collider(10, 10, solid=False),
        Velocity(100, 0),
    )
    surviving = add_entity(
        world,
        Projectile(owner=enemy, tag="miss", damage=3, ttl_ms=100),
        Team("enemy"),
        Transform(1_000, 1_000),
        Collider(10, 10, solid=False),
        Velocity(),
    )

    CombatSystem().update(world, 16)

    assert expired not in world.alive_entities
    assert colliding not in world.alive_entities
    assert surviving in world.alive_entities
    assert dead_player in world.alive_entities
    queue = world.resources["damage_queue"]
    assert isinstance(queue, list)
    assert any(item.target_id == enemy and item.amount == 3 and item.source_id == player for item in queue)
    assert any(item.target_id == player and item.amount == 2 and item.source_id == enemy for item in queue)


def test_hazard_uses_an_explicit_non_entity_unblockable_damage_source() -> None:
    world = World()
    world.resources["config"] = GameConfig()
    world.resources["collision_world"] = TileCollisionWorld(
        tile_size=32,
        width_tiles=2,
        height_tiles=2,
        solid_tiles=set(),
        hazard_tiles={(0, 0)},
    )
    player = add_entity(
        world,
        PlayerSlot(1),
        Transform(2, 2),
        Velocity(),
        Collider(20, 20, on_ground=True),
        Health(10, 10),
        Facing(1),
        ActorState("Guard"),
        DefenseState(guarding=True),
    )

    CollisionSystem().update(world, 16)

    assert world.resources["damage_queue"] == [
        DamageRecord(
            source_id=NON_ENTITY_DAMAGE_SOURCE_ID,
            target_id=player,
            amount=1,
            knockback_x=0.0,
            knockback_y=-200.0,
            guard_break=True,
        )
    ]
    world.get_component(player, Collider).on_ground = True
    DamageSystem().update(world, 0)
    assert world.get_component(player, Health).current == 9
    assert world.events.peek()[0].payload["guarded"] is False


def test_coop_respawn_uses_an_alive_anchor_and_respects_timer_and_lives() -> None:
    world = World()
    world.resources["stage_spec"] = stage_spec()
    add_entity(world, PlayerSlot(1), Transform(100, 80), Health(5, 5))
    fallen = add_entity(world, PlayerSlot(4), Transform(0, 0), Health(0, 10, dead=True))
    ready = add_entity(
        world,
        PlayerSlot(2, lives=2),
        Respawn(20, 30),
        Transform(0, 0),
        Velocity(20, 30),
        Collider(20, 20, on_ground=True),
        Health(0, 10, dead=True),
        ActorState("Dead"),
    )
    waiting = add_entity(
        world,
        PlayerSlot(3, lives=2),
        Respawn(20, 30, timer_ms=100),
        Transform(0, 0),
        Velocity(),
        Collider(20, 20),
        Health(0, 10, dead=True),
        ActorState("Dead"),
    )
    exhausted = add_entity(
        world,
        PlayerSlot(4, lives=0),
        Respawn(20, 30),
        Transform(0, 0),
        Velocity(),
        Collider(20, 20),
        Health(0, 10, dead=True),
        ActorState("Dead"),
    )
    world.get_component(fallen, Transform).y = 500

    CoopRespawnSystem().update(world, 16)

    ready_slot = world.get_component(ready, PlayerSlot)
    ready_transform = world.get_component(ready, Transform)
    ready_health = world.get_component(ready, Health)
    assert ready_slot.lives == 1
    assert (ready_transform.x, ready_transform.y) == (118, 52)
    assert (ready_health.current, ready_health.dead, ready_health.invulnerable_ms) == (5, False, 1200)
    assert world.get_component(ready, Velocity) == Velocity(0.0, -100.0)
    assert world.get_component(ready, Collider).on_ground is False
    assert world.get_component(ready, ActorState).name == "Idle"
    assert world.get_component(waiting, Respawn).timer_ms == 84
    assert world.get_component(waiting, Health).dead is True
    assert world.get_component(exhausted, Health).dead is True
    assert world.resources["damage_queue"] == [
        DamageRecord(
            source_id=NON_ENTITY_DAMAGE_SOURCE_ID,
            target_id=fallen,
            amount=10,
            knockback_x=0.0,
            knockback_y=-220.0,
            guard_break=True,
        )
    ]
    assert world.events.peek()[0].payload == {"slot": 2, "entity_id": ready}


def test_coop_respawn_uses_the_checkpoint_when_no_player_is_alive() -> None:
    world = World()
    world.resources["stage_spec"] = stage_spec()
    player = add_entity(
        world,
        PlayerSlot(1, lives=1),
        Respawn(45, 55),
        Transform(0, 0),
        Velocity(),
        Collider(20, 20),
        Health(0, 8, dead=True),
        ActorState("Dead"),
    )

    CoopRespawnSystem().update(world, 16)

    transform = world.get_component(player, Transform)
    assert (transform.x, transform.y) == (45, 55)


def test_damage_system_ignores_invalid_hits_and_applies_hurt_death_and_respawn_state() -> None:
    world = World()
    world.resources["config"] = GameConfig()
    dead = add_entity(world, Health(0, 5, dead=True))
    invulnerable = add_entity(world, Health(5, 5, invulnerable_ms=50))
    hurt = add_entity(world, Health(5, 5), Velocity(10, 0), ActorState("Idle"))
    killed_player = add_entity(
        world,
        Health(1, 5),
        Velocity(),
        ActorState("Idle"),
        PlayerSlot(1),
        Respawn(0, 0),
    )
    killed_enemy = add_entity(world, Health(1, 1))
    world.resources["damage_queue"] = [
        DamageRecord(0, 999, 1, 0.0, 0.0, False),
        DamageRecord(0, dead, 1, 0.0, 0.0, False),
        DamageRecord(0, invulnerable, 1, 0.0, 0.0, False),
        DamageRecord(0, hurt, 2, 5.0, 10.0, False),
        DamageRecord(0, killed_player, 1, 0.0, 0.0, False),
        DamageRecord(0, killed_enemy, 1, 0.0, 0.0, False),
    ]

    DamageSystem().update(world, 10)

    assert world.resources["damage_queue"] == []
    assert world.get_component(invulnerable, Health).current == 5
    assert world.get_component(invulnerable, Health).invulnerable_ms == 40
    assert world.get_component(hurt, Health).current == 3
    assert world.get_component(hurt, Velocity) == Velocity(15.0, 10.0)
    assert world.get_component(hurt, ActorState).name == "Hurt"
    assert world.get_component(killed_player, Health).dead is True
    assert world.get_component(killed_player, Respawn).timer_ms == 1800
    assert world.get_component(killed_player, ActorState).name == "Dead"
    assert world.get_component(killed_enemy, Health).dead is True
    assert [event.payload["entity_id"] for event in world.events.peek() if event.topic == "actor_dead"] == [
        killed_player,
        killed_enemy,
    ]


def test_draw_system_filters_targets_then_harmonizes_with_the_first_valid_echo() -> None:
    world = World()
    player = add_entity(
        world,
        Team("player"),
        Transform(100, 100),
        Collider(20, 20),
        ControlIntent(draw_pressed=True),
        DrawState(),
        AbilityState(current="none"),
        ActorState("Idle"),
        Facing(1),
    )
    add_entity(world, Team("player"), Transform(110, 100), Collider(20, 20), Health(2, 2), EnemyDropAbility("ice"))
    add_entity(
        world,
        Team("enemy"),
        Transform(115, 100),
        Collider(20, 20),
        Health(0, 2, dead=True),
        EnemyDropAbility("ice"),
    )
    add_entity(world, Team("enemy"), Transform(110, 200), Collider(20, 20), Health(2, 2), EnemyDropAbility("ice"))
    add_entity(world, Team("enemy"), Transform(50, 100), Collider(20, 20), Health(2, 2), EnemyDropAbility("ice"))
    captured = add_entity(
        world,
        Team("enemy"),
        Transform(130, 100),
        Collider(20, 20),
        Health(2, 2),
        EnemyDropAbility("fire"),
    )

    DrawSystem().update(world, 16)

    draw_state = world.get_component(player, DrawState)
    assert draw_state.active is True
    assert draw_state.captured_entity == captured
    assert world.get_component(captured, Transform).x == 114

    intent = world.get_component(player, ControlIntent)
    intent.draw_pressed = False
    intent.draw_released = True
    DrawSystem().update(world, 16)

    assert captured not in world.alive_entities
    assert world.get_component(player, AbilityState).current == "fire"
    assert world.get_component(player, ActorState).name == "Harmonize"
    assert draw_state == DrawState()
    assert world.events.peek()[0].topic == "ability_copied"


def test_draw_release_without_a_live_capture_launches_a_facing_projectile() -> None:
    world = World()
    player = add_entity(
        world,
        Team("player"),
        Transform(50, 40),
        Collider(20, 20),
        ControlIntent(draw_released=True),
        DrawState(active=True, active_ms=30, captured_entity=999),
        AbilityState(),
        ActorState("Draw"),
        Facing(-1),
    )

    DrawSystem().update(world, 16)

    requests = world.resources["projectile_requests"]
    assert isinstance(requests, list)
    assert requests == [
        {
            "owner": player,
            "team": "player",
            "tag": "spit_star",
            "x": 60,
            "y": 48,
            "vx": -360.0,
            "vy": -20.0,
            "damage": 2,
            "ttl_ms": 300,
            "width": 20,
            "height": 16,
        }
    ]


def test_enemy_ai_covers_dead_chase_and_all_patrol_boundaries() -> None:
    world = World()
    add_entity(world, PlayerSlot(1), Transform(100, 0), Health(5, 5))
    add_entity(world, PlayerSlot(2), Transform(500, 0), Health(0, 5, dead=True))
    dead = add_entity(world, EnemyAI("grunt", 0, 100), Transform(0, 0), Velocity(20, 0), Health(0, 2, dead=True))
    chasing_right = add_entity(world, EnemyAI("grunt", 0, 300), Transform(50, 0), Velocity(), Health(2, 2))
    chasing_left = add_entity(world, EnemyAI("brute", 0, 300), Transform(150, 0), Velocity(), Health(2, 2))
    boss = add_entity(world, EnemyAI("boss", 0, 300), Transform(90, 0), Velocity(), Health(2, 2))
    patrol_left = add_entity(
        world,
        EnemyAI("grunt", 300, 400, aggro_range=10),
        Transform(250, 0),
        Velocity(),
        Health(2, 2),
    )
    patrol_right = add_entity(
        world,
        EnemyAI("grunt", 300, 400, aggro_range=10),
        Transform(450, 0),
        Velocity(),
        Health(2, 2),
    )
    patrol_middle = add_entity(
        world,
        EnemyAI("boss", 300, 400, aggro_range=10, facing=-1),
        Transform(350, 0),
        Velocity(),
        Health(2, 2),
    )

    EnemyAISystem().update(world, 16)

    assert world.get_component(dead, Velocity).vx == 0
    assert world.get_component(chasing_right, Velocity).vx == 140
    assert world.get_component(chasing_left, Velocity).vx == -90
    assert world.get_component(boss, Velocity).vx == 120
    assert world.get_component(patrol_left, Velocity).vx == 88
    assert world.get_component(patrol_right, Velocity).vx == -88
    assert world.get_component(patrol_middle, Velocity).vx == -70


def test_input_command_system_resets_stale_intent_and_maps_every_command_type() -> None:
    world = World()
    first = add_entity(world, PlayerSlot(1), ControlIntent(move_axis=-1, jump_pressed=True), Facing(-1))
    second = add_entity(world, PlayerSlot(2), ControlIntent(), Facing(1))
    third = add_entity(world, PlayerSlot(3), ControlIntent(), Facing(-1))
    system = InputCommandSystem()
    world.frame_input = object()
    system.update(world, 16)
    assert world.get_component(first, ControlIntent).jump_pressed is True

    world.frame_input = InputFrame(
        commands_by_slot={
            1: [
                MoveCommand(1, 1),
                JumpCommand(1, True),
                HoverCommand(1, True),
                DrawStartCommand(1),
                DrawReleaseCommand(1),
                AbilityUseCommand(1, True),
                GuardCommand(1, True),
                DodgeCommand(1, True),
                DropAbilityCommand(1, True),
            ],
            2: [MoveCommand(2, -1)],
            3: [MoveCommand(3, 0)],
        }
    )
    system.update(world, 16)

    first_intent = world.get_component(first, ControlIntent)
    assert first_intent == ControlIntent(
        move_axis=1,
        jump_pressed=True,
        hover_held=True,
        draw_pressed=True,
        draw_released=True,
        ability_pressed=True,
        guard_held=True,
        dodge_pressed=True,
        drop_pressed=True,
    )
    assert world.get_component(first, Facing).direction == 1
    assert world.get_component(second, Facing).direction == -1
    assert world.get_component(third, Facing).direction == -1


def test_movement_system_handles_guard_acceleration_deceleration_jump_hover_and_gravity() -> None:
    world = World()
    world.resources["config"] = GameConfig()

    def player(intent: ControlIntent, velocity: Velocity, collider: Collider) -> int:
        return add_entity(
            world,
            PlayerSlot(1),
            Team("player"),
            Transform(0, 0),
            velocity,
            collider,
            intent,
            ActorState("Idle"),
            MovementState(),
            DefenseState(guarding=intent.guard_held),
            Health(10, 10),
        )

    jumping = player(ControlIntent(move_axis=1, jump_pressed=True, guard_held=True), Velocity(), Collider(20, 20, True))
    moving_left = player(ControlIntent(move_axis=-1), Velocity(), Collider(20, 20))
    slowing_right = player(ControlIntent(), Velocity(100, 0), Collider(20, 20))
    slowing_left = player(ControlIntent(), Velocity(-100, 0), Collider(20, 20))
    hovering = player(ControlIntent(hover_held=True), Velocity(0, 0), Collider(20, 20))
    over_speed = player(ControlIntent(move_axis=1), Velocity(500, 2_000), Collider(20, 20))

    MovementSystem().update(world, 16)

    assert world.get_component(jumping, Velocity).vx == pytest.approx(27.2)
    assert world.get_component(jumping, Velocity).vy == pytest.approx(-720.0)
    assert world.get_component(jumping, Collider).on_ground is False
    assert world.get_component(jumping, ActorState).name == "Jump"
    assert world.get_component(moving_left, Velocity).vx == pytest.approx(-27.2)
    assert world.get_component(slowing_right, Velocity).vx == pytest.approx(52.0)
    assert world.get_component(slowing_left, Velocity).vx == pytest.approx(-52.0)
    assert world.get_component(hovering, Velocity).vy == pytest.approx(11.2)
    assert world.get_component(hovering, ActorState).name == "Hover"
    assert world.get_component(over_speed, Velocity).vx == pytest.approx(472.8)
    assert world.get_component(over_speed, Velocity).vy == 1600.0


def test_pickup_system_ignores_ineligible_entities_and_collects_each_overlap_once() -> None:
    world = World()
    add_entity(world, Team("enemy"), Transform(0, 0), Collider(20, 20), Health(5, 5))
    add_entity(world, Team("player"), Transform(0, 0), Collider(20, 20), Health(0, 5, dead=True))
    add_entity(world, Team("player"), Transform(10, 10), Collider(20, 20), Health(5, 5))
    collected = add_entity(world, Collectible("mote", collected=True), Transform(10, 10), Collider(8, 8))
    far = add_entity(world, Collectible("mote", value=2), Transform(500, 500), Collider(8, 8))
    overlap = add_entity(world, Collectible("mote", value=3), Transform(15, 15), Collider(8, 8))

    PickupSystem().update(world, 16)

    assert collected in world.alive_entities
    assert far in world.alive_entities
    assert overlap not in world.alive_entities
    assert world.resources["run_energy_spheres"] == 3
    assert world.events.peek()[0].payload == {"kind": "mote", "value": 3}
