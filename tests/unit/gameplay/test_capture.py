"""Canonical capture, harmonize, launch, and echo recovery contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

import windsprig.gameplay.components as component_types
import windsprig.gameplay.systems as system_types
from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    AttackRequest,
    CapturedBy,
    CaptureState,
    Collider,
    ControlIntent,
    EchoPickup,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    Health,
    PlayerSlot,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.systems import (
    CaptureSystem,
    CollisionSystem,
    CombatSystem,
    EnemyAISystem,
    PickupSystem,
)
from windsprig.gameplay.systems.capture_system import provisional_attack_request_id
from windsprig.physics import TileCollisionWorld


def _add(world: World, *components: object) -> int:
    entity_id = world.create_entity()
    for component in components:
        world.add_component(entity_id, component)
    return entity_id


def _capture_world(*, facing: int = 1) -> tuple[World, int]:
    world = World()
    world.resources["config"] = GameConfig()
    world.resources["attack_requests"] = []
    world.resources["discovered_ability_ids"] = set()
    player = _add(
        world,
        PlayerSlot(1),
        Team("player"),
        Transform(100.0, 100.0),
        Velocity(),
        Collider(28, 28, on_ground=True),
        Facing(facing),
        Health(10, 10),
        ActorState(),
        ControlIntent(),
        CaptureState(),
        AbilityState(),
    )
    return world, player


def _enemy(
    world: World,
    *,
    x: float,
    y: float = 100.0,
    kind: str = "grunt",
    ability_id: str = "none",
    captured_by: int | None = None,
) -> int:
    components: list[object] = [
        Team("enemy"),
        Transform(x, y),
        Velocity(25.0, 5.0),
        Collider(26, 26),
        Facing(-1),
        Health(2, 2),
        ActorState("Run"),
        EnemyAI(kind, x - 20, x + 20),
        EnemyDropAbility(ability_id),
    ]
    if captured_by is not None:
        components.append(CapturedBy(captured_by))
    return _add(world, *components)


def _event_payload(world: World, topic: str) -> dict[str, object]:
    events = [event for event in world.events.peek() if event.topic == topic]
    assert len(events) == 1
    return dict(events[0].payload)


def _request(owner: int = 1) -> AttackRequest:
    return AttackRequest(
        owner_entity_id=owner,
        team="player",
        ability_id="none",
        attack_kind="probe",
        visual_id="probe",
        x=0.0,
        y=0.0,
        width=1,
        height=1,
        vx=0.0,
        vy=0.0,
        damage=1,
        knockback_x=0.0,
        knockback_y=0.0,
        ttl_ms=1,
        pierce=0,
        cuts_projectiles=False,
        guard_break=False,
        pull_strength=0.0,
        interaction_kind=None,
    )


def test_canonical_component_fields_are_exact_and_attack_requests_are_frozen() -> None:
    assert not hasattr(component_types, "DrawState")
    assert not hasattr(system_types, "DrawSystem")
    assert tuple(field.name for field in fields(CaptureState)) == (
        "phase",
        "draw_elapsed_ms",
        "captured_entity_id",
        "captured_ability_id",
        "captured_visual_id",
    )
    assert tuple(field.name for field in fields(CapturedBy)) == ("player_entity_id",)
    assert tuple(field.name for field in fields(EchoPickup)) == ("ability_id",)
    assert tuple(field.name for field in fields(AbilityState)) == (
        "current_id",
        "previous_id",
        "cooldown_remaining_ms",
        "charge_ms",
        "combo_step",
        "combo_window_remaining_ms",
        "meter",
        "armor_remaining_ms",
    )
    assert tuple(field.name for field in fields(AttackRequest)) == (
        "owner_entity_id",
        "team",
        "ability_id",
        "attack_kind",
        "visual_id",
        "x",
        "y",
        "width",
        "height",
        "vx",
        "vy",
        "damage",
        "knockback_x",
        "knockback_y",
        "ttl_ms",
        "pierce",
        "cuts_projectiles",
        "guard_break",
        "pull_strength",
        "interaction_kind",
    )
    with pytest.raises(FrozenInstanceError):
        _request().damage = 9  # type: ignore[misc]


def test_capture_selects_nearest_then_enemy_id_after_exact_filtering() -> None:
    world, player = _capture_world()
    _enemy(world, x=90.0)
    _enemy(world, x=182.0)
    _enemy(world, x=110.0, y=139.0)
    _enemy(world, x=110.0, kind="boss", ability_id="tempest")
    reserved = _enemy(world, x=108.0)
    owner = _add(
        world,
        Health(current=3, maximum=3),
        CaptureState(phase="holding", captured_entity_id=reserved),
    )
    world.add_component(reserved, CapturedBy(owner))
    expected = _enemy(world, x=120.0, ability_id="none")
    _enemy(world, x=120.0, ability_id="cinder")
    world.get_component(player, ControlIntent).draw_started = True

    CaptureSystem().update(world, 16)

    capture = world.get_component(player, CaptureState)
    assert capture == CaptureState(
        phase="holding",
        draw_elapsed_ms=16,
        captured_entity_id=expected,
        captured_ability_id=None,
        captured_visual_id="grunt",
    )
    assert world.get_component(expected, CapturedBy) == CapturedBy(player)
    assert world.get_component(expected, Velocity) == Velocity()
    assert world.get_component(expected, Collider).solid is False
    assert _event_payload(world, "EnemyCaptured") == {
        "frame_index": 0,
        "player_id": player,
        "enemy_id": expected,
        "ability_id": None,
        "visual_id": "grunt",
    }
    with pytest.raises(TypeError):
        world.events.peek()[0].payload["enemy_id"] = 999  # type: ignore[index]


def test_capture_respects_flipped_facing_and_configured_growing_range() -> None:
    world, player = _capture_world(facing=-1)
    behind = _enemy(world, x=110.0)
    expected = _enemy(world, x=18.8, ability_id="galehook")
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True

    CaptureSystem().update(world, 16)

    assert world.get_component(player, CaptureState).captured_entity_id == expected
    assert not world.has_component(behind, CapturedBy)


def test_empty_release_clears_stale_frame_request_and_is_idempotent() -> None:
    world, player = _capture_world()
    intent = world.get_component(player, ControlIntent)
    intent.draw_released = True
    world.resources["attack_requests"] = [_request()]
    system = CaptureSystem()

    system.update(world, 16)
    system.update(world, 16)

    assert world.resources["attack_requests"] == []
    assert _event_payload(world, "CaptureReleased") == {
        "frame_index": 0,
        "player_id": player,
        "outcome": "empty",
    }
    assert [event.topic for event in world.events.peek()] == ["CaptureReleased"]


@pytest.mark.parametrize("actor_name", ["Hurt", "Guard", "Dodge", "Attack"])
def test_idle_release_preserves_non_capture_actor_state(actor_name: str) -> None:
    world, player = _capture_world()
    state = world.get_component(player, ActorState)
    state.name = actor_name
    state.timer_ms = 100
    world.get_component(player, ControlIntent).draw_released = True

    CaptureSystem().update(world, 16)

    assert (state.name, state.timer_ms) == (actor_name, 100)
    assert [event.topic for event in world.events.peek()] == ["CaptureReleased"]


def test_release_with_capture_queues_one_fully_populated_launch_and_one_event() -> None:
    world, player = _capture_world()
    enemy = _enemy(world, x=120.0)
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True
    system = CaptureSystem()
    system.update(world, 16)
    world.events.drain()
    intent.draw_released = True

    system.update(world, 16)

    assert enemy not in world.alive_entities
    requests = world.resources["attack_requests"]
    assert isinstance(requests, list)
    assert requests == [
        AttackRequest(
            owner_entity_id=player,
            team="player",
            ability_id="none",
            attack_kind="launched_enemy",
            visual_id="wind_launch",
            x=122.0,
            y=100.0,
            width=26,
            height=26,
            vx=520.0,
            vy=-40.0,
            damage=4,
            knockback_x=260.0,
            knockback_y=-120.0,
            ttl_ms=480,
            pierce=0,
            cuts_projectiles=False,
            guard_break=False,
            pull_strength=0.0,
            interaction_kind=None,
        )
    ]
    assert provisional_attack_request_id(requests) == 2
    assert _event_payload(world, "EnemyLaunched") == {
        "frame_index": 0,
        "player_id": player,
        "enemy_id": enemy,
        "attack_id": 1,
    }


def test_simultaneous_compatible_harmonize_consumes_release_and_ability_use() -> None:
    world, player = _capture_world()
    enemy = _enemy(world, x=120.0, ability_id="cinder")
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True
    system = CaptureSystem()
    system.update(world, 16)
    world.events.drain()
    intent.ability_pressed = True
    intent.draw_released = True

    system.update(world, 16)

    ability = world.get_component(player, AbilityState)
    assert (ability.previous_id, ability.current_id) == ("none", "cinder")
    assert intent.ability_consumed is True
    assert enemy not in world.alive_entities
    assert world.get_component(player, CaptureState) == CaptureState()
    assert world.resources["discovered_ability_ids"] == {"cinder"}
    assert world.resources["attack_requests"] == []
    assert [event.topic for event in world.events.peek()] == ["AbilityEquipped"]
    assert _event_payload(world, "AbilityEquipped") == {
        "frame_index": 0,
        "player_id": player,
        "ability_id": "cinder",
        "source": "capture",
    }


def test_incompatible_harmonize_retains_capture_and_suppresses_simultaneous_release() -> None:
    world, player = _capture_world()
    enemy = _enemy(world, x=120.0, ability_id="none")
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True
    system = CaptureSystem()
    system.update(world, 16)
    world.events.drain()
    intent.ability_pressed = True
    intent.draw_released = True

    system.update(world, 16)
    system.update(world, 16)

    assert world.get_component(player, CaptureState).captured_entity_id == enemy
    assert intent.ability_consumed is True
    assert intent.ability_pressed is False
    assert enemy in world.alive_entities
    assert world.resources["attack_requests"] == []
    assert _event_payload(world, "HarmonizeUnavailable") == {
        "frame_index": 0,
        "player_id": player,
        "enemy_id": enemy,
    }
    assert [event.topic for event in world.events.peek()] == ["HarmonizeUnavailable"]


def test_dead_captured_target_is_released_immediately() -> None:
    world, player = _capture_world()
    enemy = _enemy(world, x=120.0)
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True
    system = CaptureSystem()
    system.update(world, 16)
    world.get_component(enemy, Health).dead = True

    system.update(world, 16)

    assert world.get_component(player, CaptureState) == CaptureState()
    assert not world.has_component(enemy, CapturedBy)
    assert world.get_component(enemy, Collider).solid is True
    assert world.get_component(player, ActorState).name == "Idle"


@pytest.mark.parametrize("with_enemy", [False, True])
def test_airborne_release_recovers_draw_to_fall(with_enemy: bool) -> None:
    world, player = _capture_world()
    collider = world.get_component(player, Collider)
    collider.on_ground = False
    world.get_component(player, ActorState).name = "Jump"
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True
    enemy = _enemy(world, x=120.0) if with_enemy else None
    system = CaptureSystem()
    system.update(world, 16)
    intent.draw_released = True

    system.update(world, 16)

    assert world.get_component(player, ActorState).name == "Fall"
    if enemy is not None:
        assert enemy not in world.alive_entities


def test_dead_owner_clears_movement_drop_and_ability_inputs() -> None:
    world, player = _capture_world()
    health = world.get_component(player, Health)
    health.dead = True
    state = world.get_component(player, ActorState)
    state.name = "Dead"
    ability = world.get_component(player, AbilityState)
    ability.current_id = "cinder"
    intent = world.get_component(player, ControlIntent)
    intent.move_axis = 1
    intent.ability_pressed = True
    intent.drop_pressed = True

    CaptureSystem().update(world, 16)

    assert (intent.move_axis, intent.ability_pressed, intent.drop_pressed) == (0, False, False)
    assert ability.current_id == "cinder"
    assert world.query(EchoPickup) == []


def test_destroyed_capture_recovers_to_one_empty_release() -> None:
    world, player = _capture_world()
    enemy = _enemy(world, x=120.0)
    intent = world.get_component(player, ControlIntent)
    intent.draw_started = True
    system = CaptureSystem()
    system.update(world, 16)
    world.events.drain()
    world.destroy_entity(enemy)
    intent.draw_released = True

    system.update(world, 16)

    assert world.get_component(player, CaptureState) == CaptureState()
    assert world.resources["attack_requests"] == []
    assert [event.topic for event in world.events.peek()] == ["CaptureReleased"]


def test_missing_or_dead_owner_releases_captured_enemy_without_sentinel_owner() -> None:
    for destroy_owner in (False, True):
        world, player = _capture_world()
        enemy = _enemy(world, x=120.0)
        intent = world.get_component(player, ControlIntent)
        intent.draw_started = True
        system = CaptureSystem()
        system.update(world, 16)
        if destroy_owner:
            world.destroy_entity(player)
        else:
            world.get_component(player, Health).dead = True

        system.update(world, 16)

        assert enemy in world.alive_entities
        assert not world.has_component(enemy, CapturedBy)
        assert world.get_component(enemy, Collider).solid is True


def test_captured_enemy_cannot_move_collide_or_deal_body_contact_damage() -> None:
    world = World()
    world.resources["collision_world"] = TileCollisionWorld(
        tile_size=32,
        width_tiles=20,
        height_tiles=10,
        solid_tiles=set(),
        hazard_tiles=set(),
    )
    player = _add(
        world,
        PlayerSlot(1),
        Team("player"),
        Transform(100.0, 100.0),
        Collider(28, 28),
        Health(10, 10),
    )
    enemy = _add(
        world,
        Team("enemy"),
        Transform(100.0, 100.0),
        Velocity(200.0, 200.0),
        Collider(26, 26, solid=True),
        Health(2, 2),
        EnemyAI("grunt", 0.0, 200.0),
        CapturedBy(player),
    )

    EnemyAISystem().update(world, 16)
    CollisionSystem().update(world, 16)
    CombatSystem().update(world, 16)

    assert world.get_component(enemy, Transform) == Transform(100.0, 100.0)
    assert world.get_component(enemy, Velocity) == Velocity()
    assert world.resources["damage_queue"] == []


def test_drop_none_is_noop_and_equipped_drop_spawns_one_recoverable_echo() -> None:
    world, player = _capture_world()
    intent = world.get_component(player, ControlIntent)
    system = CaptureSystem()
    intent.drop_pressed = True
    system.update(world, 16)
    assert world.query(EchoPickup) == []
    assert world.events.peek() == []

    ability = world.get_component(player, AbilityState)
    ability.current_id = "galehook"
    intent.drop_pressed = True
    system.update(world, 16)
    rows = world.query(EchoPickup, Transform, Collider)
    assert len(rows) == 1
    pickup_id, echo, transform, collider = rows[0]
    assert echo == EchoPickup("galehook")
    assert (transform.x, transform.y) == (100.0, 100.0)
    assert collider.solid is False
    assert (ability.previous_id, ability.current_id) == ("galehook", "none")
    assert _event_payload(world, "AbilityDropped") == {
        "frame_index": 0,
        "player_id": player,
        "ability_id": "galehook",
        "pickup_id": pickup_id,
    }


def test_echo_pickup_contention_uses_living_active_player_entity_order_once() -> None:
    world, first = _capture_world()
    dead = _add(
        world,
        PlayerSlot(2),
        Team("player"),
        Transform(100, 100),
        Collider(28, 28),
        Health(0, 10, dead=True),
        AbilityState(),
    )
    inactive = _add(
        world,
        Team("player"),
        Transform(100, 100),
        Collider(28, 28),
        Health(10, 10),
        AbilityState(),
    )
    second = _add(
        world,
        PlayerSlot(3),
        Team("player"),
        Transform(100, 100),
        Collider(28, 28),
        Health(10, 10),
        AbilityState(),
    )
    pickup = _add(world, EchoPickup("stoneheart"), Transform(100, 100), Collider(20, 20, solid=False))

    PickupSystem().update(world, 16)
    PickupSystem().update(world, 16)

    assert pickup not in world.alive_entities
    assert world.get_component(first, AbilityState).current_id == "stoneheart"
    assert world.get_component(dead, AbilityState).current_id == "none"
    assert world.get_component(inactive, AbilityState).current_id == "none"
    assert world.get_component(second, AbilityState).current_id == "none"
    assert world.resources["discovered_ability_ids"] == {"stoneheart"}
    assert [event.topic for event in world.events.peek()] == ["AbilityEquipped"]
    assert _event_payload(world, "AbilityEquipped") == {
        "frame_index": 0,
        "player_id": first,
        "ability_id": "stoneheart",
        "source": "echo_pickup",
    }
