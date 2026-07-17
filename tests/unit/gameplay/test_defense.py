"""Directional guard, dodge, and typed damage boundary tests."""

from __future__ import annotations

from dataclasses import fields

import pytest

from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    ControlIntent,
    DamageRecord,
    DefenseState,
    Facing,
    Health,
    PlayerSlot,
    Transform,
    Velocity,
)
from windsprig.gameplay.systems import DamageSystem, DefenseSystem


def _defender(
    *,
    facing: int = 1,
    on_ground: bool = True,
    state_name: str = "Idle",
) -> tuple[World, int, int]:
    world = World()
    world.resources["config"] = GameConfig()
    target_id = world.create_entity()
    for component in (
        PlayerSlot(1),
        Transform(0.0, 0.0),
        Velocity(),
        Collider(28, 28, on_ground=on_ground),
        Facing(facing),
        Health(10, 10),
        ActorState(state_name),
        ControlIntent(),
        DefenseState(),
    ):
        world.add_component(target_id, component)
    source_id = world.create_entity()
    world.add_component(source_id, Transform(10.0, 0.0))
    return world, target_id, source_id


def _queue_hit(
    world: World,
    source_id: int,
    target_id: int,
    *,
    amount: int = 5,
    knockback_x: float = -200.0,
    knockback_y: float = -100.0,
    guard_break: bool = False,
) -> None:
    world.resources["damage_queue"] = [
        DamageRecord(
            source_id=source_id,
            target_id=target_id,
            amount=amount,
            knockback_x=knockback_x,
            knockback_y=knockback_y,
            guard_break=guard_break,
        )
    ]


def _damage_payload(world: World) -> dict[str, object]:
    events = [event for event in world.events.peek() if event.topic == "PlayerDamaged"]
    assert len(events) == 1
    return dict(events[0].payload)


def test_damage_record_has_the_exact_typed_queue_boundary() -> None:
    assert tuple(field.name for field in fields(DamageRecord)) == (
        "source_id",
        "target_id",
        "amount",
        "knockback_x",
        "knockback_y",
        "guard_break",
        "attack_id",
    )


@pytest.mark.parametrize(("axis", "facing", "expected"), ((-1, 1, -1), (1, -1, 1), (0, -7, -1)))
def test_dodge_direction_uses_axis_then_normalized_facing(
    axis: int,
    facing: int,
    expected: int,
) -> None:
    world, player, _ = _defender(facing=facing)
    intent = world.get_component(player, ControlIntent)
    intent.move_axis = axis
    intent.dodge_pressed = True

    DefenseSystem().update(world, 16)

    defense = world.get_component(player, DefenseState)
    assert (defense.dodge_remaining_ms, defense.dodge_cooldown_ms) == (160, 520)
    assert defense.dodge_direction == expected
    assert defense.guarding is False
    assert world.get_component(player, Facing).direction == expected
    assert world.get_component(player, Velocity).vx == 620.0 * expected
    assert world.get_component(player, ActorState).name == "Dodge"
    assert [event.topic for event in world.events.peek()] == ["PlayerDodged"]
    assert world.events.peek()[0].payload == {
        "frame_index": 0,
        "entity_id": player,
        "slot": 1,
        "direction": expected,
    }


def test_dodge_rejects_through_512_ms_and_accepts_at_528_ms() -> None:
    world, player, _ = _defender()
    intent = world.get_component(player, ControlIntent)
    defense = world.get_component(player, DefenseState)
    intent.dodge_pressed = True
    DefenseSystem().update(world, 16)
    intent.dodge_pressed = False

    for _ in range(31):
        DefenseSystem().update(world, 16)
    assert defense.dodge_cooldown_ms == 24

    intent.dodge_pressed = True
    intent.guard_held = True
    DefenseSystem().update(world, 16)
    assert defense.dodge_cooldown_ms == 8
    assert defense.guarding is True
    assert len(world.events.peek()) == 1

    DefenseSystem().update(world, 16)
    assert (defense.dodge_remaining_ms, defense.dodge_cooldown_ms) == (160, 520)
    assert defense.guarding is False
    assert len(world.events.peek()) == 2


def test_held_dodge_edge_does_not_duplicate_event_or_restart_timers() -> None:
    world, player, _ = _defender()
    intent = world.get_component(player, ControlIntent)
    defense = world.get_component(player, DefenseState)
    intent.dodge_pressed = True

    DefenseSystem().update(world, 16)
    world.get_component(player, Facing).direction = -1
    intent.move_axis = -1
    DefenseSystem().update(world, 16)
    DefenseSystem().update(world, 16)

    assert (defense.dodge_remaining_ms, defense.dodge_cooldown_ms) == (128, 488)
    assert world.get_component(player, Facing).direction == 1
    assert world.get_component(player, Velocity).vx == 620.0
    assert len(world.events.peek()) == 1


def test_simultaneous_guard_and_dodge_prefers_dodge() -> None:
    world, player, _ = _defender()
    intent = world.get_component(player, ControlIntent)
    intent.guard_held = True
    intent.dodge_pressed = True

    DefenseSystem().update(world, 16)

    defense = world.get_component(player, DefenseState)
    assert defense.dodge_remaining_ms == 160
    assert defense.guarding is False
    assert world.get_component(player, ActorState).name == "Dodge"


@pytest.mark.parametrize(
    ("on_ground", "vx", "expected"),
    ((True, 0.0, "Idle"), (True, 80.0, "Run"), (False, 0.0, "Fall")),
)
@pytest.mark.parametrize("ending", ("guard", "dodge"))
def test_guard_release_and_dodge_expiry_choose_a_deterministic_actor_state(
    on_ground: bool,
    vx: float,
    expected: str,
    ending: str,
) -> None:
    world, player, _ = _defender(on_ground=on_ground)
    velocity = world.get_component(player, Velocity)
    state = world.get_component(player, ActorState)
    defense = world.get_component(player, DefenseState)
    velocity.vx = vx
    if ending == "guard":
        state.name = "Guard"
        defense.guarding = True
    else:
        state.name = "Dodge"
        defense.dodge_remaining_ms = 16
        defense.dodge_cooldown_ms = 400

    DefenseSystem().update(world, 16)

    assert state.name == expected
    assert defense.guarding is False
    assert defense.dodge_remaining_ms == 0


@pytest.mark.parametrize(
    ("remaining", "invulnerable"),
    ((160, True), (144, True), (128, True), (112, True), (96, True), (80, True), (64, True), (48, True), (32, False)),
)
def test_dodge_iframe_strict_cutoff_at_every_fixed_step(
    remaining: int,
    invulnerable: bool,
) -> None:
    world, player, source = _defender()
    world.get_component(player, DefenseState).dodge_remaining_ms = remaining
    _queue_hit(world, source, player, amount=1, knockback_x=0.0, knockback_y=0.0)

    DamageSystem().update(world, 0)

    expected_hp = 10 if invulnerable else 9
    assert world.get_component(player, Health).current == expected_hp
    assert [event.topic for event in world.events.peek()] == ([] if invulnerable else ["PlayerDamaged"])


@pytest.mark.parametrize(
    ("facing", "source_x", "expected_guarded"),
    ((1, 10.0, True), (1, -10.0, False), (-1, -10.0, True), (-1, 10.0, False), (1, 0.0, True)),
)
def test_front_rear_facing_flip_and_same_x_guard_matrix(
    facing: int,
    source_x: float,
    expected_guarded: bool,
) -> None:
    world, player, source = _defender(facing=facing)
    world.get_component(player, DefenseState).guarding = True
    world.get_component(player, ActorState).name = "Guard"
    world.get_component(source, Transform).x = source_x
    _queue_hit(world, source, player)

    DamageSystem().update(world, 0)

    payload = _damage_payload(world)
    assert payload["guarded"] is expected_guarded
    assert world.get_component(player, Health).current == (8 if expected_guarded else 5)


def test_front_guard_rounds_damage_scales_both_knockbacks_and_preserves_guard() -> None:
    world, player, source = _defender()
    defense = world.get_component(player, DefenseState)
    defense.guarding = True
    world.get_component(player, ActorState).name = "Guard"
    _queue_hit(world, source, player)

    DamageSystem().update(world, 0)

    assert world.get_component(player, Health).current == 8
    assert world.get_component(player, Velocity) == Velocity(-70.0, -35.0)
    assert world.get_component(player, ActorState).name == "Guard"
    assert defense.guarding is True
    assert _damage_payload(world) == {
        "frame_index": 0,
        "source_id": source,
        "target_id": player,
        "slot": 1,
        "amount": 2,
        "guarded": True,
        "knockback_x": -70.0,
        "knockback_y": -35.0,
    }


@pytest.mark.parametrize("reason", ("guard_break", "missing", "destroyed", "airborne", "hurt", "dead", "bad_facing"))
def test_invalid_guard_conditions_apply_full_damage_and_knockback(reason: str) -> None:
    world, player, source = _defender()
    defense = world.get_component(player, DefenseState)
    defense.guarding = True
    world.get_component(player, ActorState).name = "Guard"
    guard_break = False
    if reason == "guard_break":
        guard_break = True
    elif reason == "missing":
        source = 999
    elif reason == "destroyed":
        world.destroy_entity(source)
    elif reason == "airborne":
        world.get_component(player, Collider).on_ground = False
    elif reason == "hurt":
        world.get_component(player, ActorState).name = "Hurt"
    elif reason == "dead":
        world.get_component(player, ActorState).name = "Dead"
    else:
        world.get_component(player, Facing).direction = 2
    _queue_hit(world, source, player, guard_break=guard_break)

    DamageSystem().update(world, 0)

    assert world.get_component(player, Health).current == 5
    assert world.get_component(player, Velocity) == Velocity(-200.0, -100.0)
    assert _damage_payload(world)["guarded"] is False


def test_unguarded_hurt_recovers_after_one_owned_fixed_step() -> None:
    world, player, source = _defender()
    _queue_hit(world, source, player, amount=1, knockback_x=0.0, knockback_y=0.0)
    DamageSystem().update(world, 0)
    state = world.get_component(player, ActorState)
    assert (state.name, state.timer_ms) == ("Hurt", 16)

    DefenseSystem().update(world, 16)

    assert state.name == "Idle"
    assert state.timer_ms == 0
