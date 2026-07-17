"""Exact fixed-step movement boundaries for the camera-ready player."""

from __future__ import annotations

import pytest

from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    ControlIntent,
    DefenseState,
    Facing,
    Health,
    MovementState,
    PlayerSlot,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.systems import DefenseSystem, MovementSystem


def _movement_player(
    *,
    on_ground: bool = False,
    velocity: Velocity | None = None,
) -> tuple[World, int]:
    world = World()
    world.resources["config"] = GameConfig()
    entity_id = world.create_entity()
    for component in (
        PlayerSlot(1),
        Team("player"),
        Transform(0.0, 0.0),
        velocity or Velocity(),
        Collider(28, 28, on_ground=on_ground),
        ControlIntent(),
        ActorState(),
        Facing(),
        Health(10, 10),
        MovementState(),
        DefenseState(),
    ):
        world.add_component(entity_id, component)
    return world, entity_id


def _advance_movement(world: World, steps: int = 1) -> None:
    for _ in range(steps):
        MovementSystem().update(world, 16)


def test_coyote_jump_is_valid_at_96_ms_and_invalid_at_112_ms() -> None:
    valid_world, valid_player = _movement_player()
    valid_movement = valid_world.get_component(valid_player, MovementState)
    valid_intent = valid_world.get_component(valid_player, ControlIntent)
    valid_velocity = valid_world.get_component(valid_player, Velocity)
    valid_movement.coyote_remaining_ms = 100

    _advance_movement(valid_world, 5)
    valid_intent.jump_pressed = True
    _advance_movement(valid_world)

    assert valid_movement.coyote_remaining_ms == 0
    assert valid_movement.jump_buffer_remaining_ms == 0
    assert valid_velocity.vy == pytest.approx(-720.0)

    invalid_world, invalid_player = _movement_player()
    invalid_movement = invalid_world.get_component(invalid_player, MovementState)
    invalid_intent = invalid_world.get_component(invalid_player, ControlIntent)
    invalid_velocity = invalid_world.get_component(invalid_player, Velocity)
    invalid_movement.coyote_remaining_ms = 100

    _advance_movement(invalid_world, 6)
    invalid_intent.jump_pressed = True
    _advance_movement(invalid_world)

    assert invalid_movement.coyote_remaining_ms == 0
    assert invalid_movement.jump_buffer_remaining_ms == 120
    assert invalid_velocity.vy >= 0.0


def test_jump_buffer_lands_one_frame_before_112_ms_consumption() -> None:
    world, player = _movement_player()
    movement = world.get_component(player, MovementState)
    intent = world.get_component(player, ControlIntent)
    collider = world.get_component(player, Collider)
    velocity = world.get_component(player, Velocity)

    intent.jump_pressed = True
    _advance_movement(world)
    intent.jump_pressed = False
    _advance_movement(world, 6)
    assert movement.jump_buffer_remaining_ms == 24

    collider.on_ground = True
    _advance_movement(world)

    assert movement.jump_buffer_remaining_ms == 0
    assert collider.on_ground is False
    assert velocity.vy == pytest.approx(-720.0)


def test_jump_buffer_is_expired_at_128_ms_even_after_landing() -> None:
    world, player = _movement_player()
    movement = world.get_component(player, MovementState)
    intent = world.get_component(player, ControlIntent)
    collider = world.get_component(player, Collider)
    velocity = world.get_component(player, Velocity)

    intent.jump_pressed = True
    _advance_movement(world)
    intent.jump_pressed = False
    _advance_movement(world, 7)
    assert movement.jump_buffer_remaining_ms == 8

    collider.on_ground = True
    velocity.vy = 0.0
    _advance_movement(world)

    assert movement.jump_buffer_remaining_ms == 0
    assert collider.on_ground is True
    assert velocity.vy == pytest.approx(40.0)


def test_active_dodge_blocks_but_does_not_consume_buffered_jump() -> None:
    world, player = _movement_player(on_ground=True)
    movement = world.get_component(player, MovementState)
    defense = world.get_component(player, DefenseState)
    intent = world.get_component(player, ControlIntent)
    collider = world.get_component(player, Collider)
    velocity = world.get_component(player, Velocity)
    defense.dodge_remaining_ms = 160
    defense.dodge_direction = -1
    velocity.vx = -620.0
    intent.jump_pressed = True

    _advance_movement(world)

    assert movement.jump_buffer_remaining_ms == 120
    assert collider.on_ground is True
    assert velocity.vx == -620.0


def test_hover_uses_scaled_gravity_on_steps_53_and_54_then_full_gravity() -> None:
    world, player = _movement_player()
    movement = world.get_component(player, MovementState)
    intent = world.get_component(player, ControlIntent)
    velocity = world.get_component(player, Velocity)
    state = world.get_component(player, ActorState)
    intent.hover_held = True

    _advance_movement(world, 53)
    assert movement.hover_remaining_ms == 2
    assert movement.hover_ready is True
    before_54 = velocity.vy

    _advance_movement(world)
    assert movement.hover_remaining_ms == 0
    assert movement.hover_ready is False
    assert velocity.vy - before_54 == pytest.approx(11.2)
    assert state.name == "Hover"
    before_55 = velocity.vy

    _advance_movement(world)
    assert velocity.vy - before_55 == pytest.approx(40.0)
    assert state.name == "Fall"


def test_grounding_resets_hover_and_gravity_is_applied_exactly_once() -> None:
    hover_world, hover_player = _movement_player()
    hover_movement = hover_world.get_component(hover_player, MovementState)
    hover_intent = hover_world.get_component(hover_player, ControlIntent)
    hover_velocity = hover_world.get_component(hover_player, Velocity)
    hover_intent.hover_held = True
    hover_movement.hover_remaining_ms = 16

    _advance_movement(hover_world)

    assert hover_velocity.vy == pytest.approx(11.2)
    assert hover_movement.hover_ready is False

    hover_world.get_component(hover_player, Collider).on_ground = True
    hover_intent.hover_held = False
    _advance_movement(hover_world)
    assert hover_movement == MovementState(
        coyote_remaining_ms=100,
        jump_buffer_remaining_ms=0,
        hover_remaining_ms=850,
        hover_ready=True,
    )

    normal_world, normal_player = _movement_player()
    _advance_movement(normal_world)
    assert normal_world.get_component(normal_player, Velocity).vy == pytest.approx(40.0)


@pytest.mark.parametrize(
    ("state_name", "health_dead"),
    (("Dead", True), ("Hurt", False), ("Draw", False), ("Idle", True)),
)
def test_jump_effects_require_an_alive_legal_actor_transition(
    state_name: str,
    health_dead: bool,
) -> None:
    world, player = _movement_player(on_ground=True)
    state = world.get_component(player, ActorState)
    health = world.get_component(player, Health)
    movement = world.get_component(player, MovementState)
    intent = world.get_component(player, ControlIntent)
    velocity = world.get_component(player, Velocity)
    state.name = state_name
    health.dead = health_dead
    intent.jump_pressed = True

    _advance_movement(world)

    assert state.name == state_name
    assert velocity.vy == pytest.approx(40.0)
    assert movement.coyote_remaining_ms == 100
    assert movement.jump_buffer_remaining_ms == 120


@pytest.mark.parametrize(
    ("state_name", "health_dead"),
    (("Dead", True), ("Hurt", False), ("Draw", False), ("Idle", True)),
)
def test_hover_effects_require_an_alive_legal_actor_transition(
    state_name: str,
    health_dead: bool,
) -> None:
    world, player = _movement_player()
    state = world.get_component(player, ActorState)
    health = world.get_component(player, Health)
    movement = world.get_component(player, MovementState)
    intent = world.get_component(player, ControlIntent)
    velocity = world.get_component(player, Velocity)
    state.name = state_name
    health.dead = health_dead
    intent.hover_held = True

    _advance_movement(world)

    assert state.name == state_name
    assert velocity.vy == pytest.approx(40.0)
    assert movement.hover_remaining_ms == 850
    assert movement.hover_ready is True


def test_hurt_recovery_timer_cannot_be_overwritten_by_hover_in_the_same_tick() -> None:
    world, player = _movement_player()
    state = world.get_component(player, ActorState)
    intent = world.get_component(player, ControlIntent)
    velocity = world.get_component(player, Velocity)
    state.name = "Hurt"
    state.timer_ms = 32
    intent.hover_held = True

    DefenseSystem().update(world, 16)
    MovementSystem().update(world, 16)

    assert (state.name, state.timer_ms) == ("Hurt", 16)
    assert velocity.vy == pytest.approx(40.0)


def test_dead_player_input_cannot_apply_horizontal_acceleration() -> None:
    world, player = _movement_player()
    world.get_component(player, ActorState).name = "Dead"
    world.get_component(player, Health).dead = True
    world.get_component(player, ControlIntent).move_axis = 1

    _advance_movement(world)

    assert world.get_component(player, Velocity) == Velocity(0.0, 40.0)
