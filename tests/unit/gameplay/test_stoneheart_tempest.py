"""Exact Stoneheart, Tempest, interaction, reset, and hash contracts."""

from __future__ import annotations

from dataclasses import fields

from tests.helpers.gameplay import ability_context, make_runtime, make_stage
from windsprig.content.loader import InteractionSpec
from windsprig.core.ecs import World
from windsprig.gameplay.abilities import StoneheartStrategy, TempestStrategy
from windsprig.gameplay.components import (
    AbilityState,
    Attack,
    Collider,
    ControlIntent,
    Health,
    Interaction,
    Transform,
)
from windsprig.gameplay.systems import AbilitySystem, InteractionSystem


def _spawn_attack(
    world: World,
    *,
    owner_entity_id: int,
    attack_kind: str = "ground_slam",
    interaction_kind: str | None = "breakable_floor",
    hit_entity_ids: set[int] | None = None,
) -> int:
    entity_id = world.create_entity()
    world.add_component(
        entity_id,
        Attack(
            owner_entity_id=owner_entity_id,
            team="player",
            attack_kind=attack_kind,
            visual_id=f"test.{attack_kind}",
            damage=6,
            knockback_x=0.0,
            knockback_y=0.0,
            ttl_ms=480,
            pierce_remaining=0,
            cuts_projectiles=False,
            guard_break=True,
            pull_strength=0.0,
            interaction_kind=interaction_kind,
            born_frame=0,
            hit_entity_ids=hit_entity_ids or set(),
        ),
    )
    world.add_component(entity_id, Transform(64.0, 64.0))
    world.add_component(entity_id, Collider(32, 32, solid=False))
    return entity_id


def _spawn_floor(world: World) -> int:
    entity_id = world.create_entity()
    world.add_component(entity_id, Interaction("test.floor", "breakable_floor"))
    world.add_component(entity_id, Transform(64.0, 64.0))
    world.add_component(entity_id, Collider(32, 32, solid=False))
    return entity_id


def test_locked_attack_and_interaction_components_have_exact_fields() -> None:
    assert tuple(field.name for field in fields(Attack)) == (
        "owner_entity_id",
        "team",
        "attack_kind",
        "visual_id",
        "damage",
        "knockback_x",
        "knockback_y",
        "ttl_ms",
        "pierce_remaining",
        "cuts_projectiles",
        "guard_break",
        "pull_strength",
        "interaction_kind",
        "born_frame",
        "last_advanced_frame",
        "hit_entity_ids",
    )
    assert tuple(field.name for field in fields(Interaction)) == (
        "interaction_id",
        "kind",
        "state",
    )


def test_stoneheart_refuses_grounded_and_emits_exact_airborne_slam() -> None:
    refused = StoneheartStrategy().activate(ability_context(on_ground=True))
    execution = StoneheartStrategy().activate(ability_context(on_ground=False))

    assert refused.attacks == ()
    assert refused.armor_ms == 0
    assert len(execution.attacks) == 1
    attack = execution.attacks[0]
    assert execution.armor_ms == 420
    assert (
        attack.ability_id,
        attack.attack_kind,
        attack.damage,
        attack.guard_break,
        attack.interaction_kind,
    ) == ("stoneheart", "ground_slam", 6, True, "breakable_floor")


def test_stoneheart_system_owns_only_the_exact_armor_timer() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    ability = runtime.world.get_component(player, AbilityState)
    collider = runtime.world.get_component(player, Collider)
    intent = runtime.world.get_component(player, ControlIntent)
    ability.current_id = "stoneheart"
    collider.on_ground = True
    intent.ability_pressed = True
    system = AbilitySystem()

    system.update(runtime.world, 16)

    assert runtime.world.resources["attack_requests"] == []
    assert ability.armor_remaining_ms == 0

    collider.on_ground = False
    intent.ability_pressed = True
    system.update(runtime.world, 16)

    assert len(runtime.world.resources["attack_requests"]) == 1  # type: ignore[arg-type]
    assert ability.armor_remaining_ms == 420
    system.update(runtime.world, 16)
    assert ability.armor_remaining_ms == 404


def test_tempest_refuses_below_full_meter_and_emits_exact_one_shot() -> None:
    refused = TempestStrategy().activate(ability_context(meter=99))
    execution = TempestStrategy().activate(ability_context(meter=100))

    assert refused.attacks == ()
    assert (refused.meter_cost, refused.restore_previous) == (0, False)
    assert len(execution.attacks) == 1
    attack = execution.attacks[0]
    assert (
        attack.ability_id,
        attack.attack_kind,
        attack.damage,
        attack.pierce,
        execution.meter_cost,
        execution.restore_previous,
    ) == ("tempest", "screen_tempest", 5, 10_000, 100, True)


def test_tempest_queue_uses_stage_bounds_and_forgets_tempest_after_restore() -> None:
    stage = make_stage()
    runtime = make_runtime(stage=stage)
    player = runtime.player_entities[1]
    ability = runtime.world.get_component(player, AbilityState)
    ability.current_id = "tempest"
    ability.previous_id = "cinder"
    ability.meter = 100
    runtime.world.get_component(player, ControlIntent).ability_pressed = True

    AbilitySystem().update(runtime.world, 16)

    requests = runtime.world.resources["attack_requests"]
    assert isinstance(requests, list)
    assert len(requests) == 1
    request = requests[0]
    assert (request.x, request.y, request.width, request.height) == (
        0.0,
        0.0,
        stage.pixel_width,
        stage.pixel_height,
    )
    assert (ability.current_id, ability.previous_id, ability.meter) == (
        "cinder",
        "none",
        0,
    )
    assert "tempest" not in (ability.current_id, ability.previous_id)


def test_tempest_refusal_and_invalid_tempest_previous_cannot_rearm_it() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    ability = runtime.world.get_component(player, AbilityState)
    intent = runtime.world.get_component(player, ControlIntent)
    ability.current_id = "tempest"
    ability.previous_id = "cinder"
    ability.meter = 99
    intent.ability_pressed = True
    system = AbilitySystem()

    system.update(runtime.world, 16)

    assert runtime.world.resources["attack_requests"] == []
    assert (ability.current_id, ability.previous_id, ability.meter) == (
        "tempest",
        "cinder",
        99,
    )

    ability.previous_id = "tempest"
    ability.meter = 100
    intent.ability_pressed = True
    system.update(runtime.world, 16)

    assert (ability.current_id, ability.previous_id, ability.meter) == ("none", "none", 0)


def test_authored_interactions_materialize_as_sorted_immutable_views_and_reset() -> None:
    stage = make_stage(
        interactions=(
            InteractionSpec("z.switch", "switch", 6, 3, 2, 1),
            InteractionSpec("a.conductor", "conductor", 2, 4),
            InteractionSpec("m.lift", "gust_lift", 10, 1, 1, 3),
        )
    )
    runtime = make_runtime(stage=stage)
    fresh = make_runtime(stage=stage)
    initial_hash = runtime.world.world_hash()
    snapshot = runtime.snapshot()

    assert tuple(view.entity_id for view in snapshot.interactions) == tuple(
        sorted(view.entity_id for view in snapshot.interactions)
    )
    assert tuple(view.interaction_id for view in snapshot.interactions) == (
        "z.switch",
        "a.conductor",
        "m.lift",
    )
    assert [
        (
            view.interaction_id,
            view.interaction_kind,
            view.interaction_state,
            view.x,
            view.y,
            view.width,
            view.height,
        )
        for view in snapshot.interactions
    ] == [
        ("z.switch", "switch", "idle", 192.0, 96.0, 64, 32),
        ("a.conductor", "conductor", "idle", 64.0, 128.0, 32, 32),
        ("m.lift", "gust_lift", "idle", 320.0, 32.0, 32, 96),
    ]
    entity_ids = tuple(view.entity_id for view in snapshot.interactions)
    rows = runtime.world.query(Interaction, Transform, Collider)
    assert len(rows) == 3
    assert all(collider.solid is False for _, _, _, collider in rows)

    runtime.world.get_component(entity_ids[0], Interaction).state = "energized"
    assert runtime.world.world_hash() != initial_hash
    reset = runtime.reset_stage()

    assert tuple(view.entity_id for view in reset.interactions) == entity_ids
    assert tuple(view.interaction_state for view in reset.interactions) == (
        "idle",
        "idle",
        "idle",
    )
    assert runtime.world.world_hash() == fresh.world.world_hash() == initial_hash


def test_floor_requires_existing_slam_and_a_living_grounded_owner() -> None:
    world = World()
    owner = world.create_entity()
    world.add_component(owner, Health(10, 10))
    world.add_component(owner, Collider(28, 28, on_ground=False))
    floor_id = _spawn_floor(world)
    attack_id = _spawn_attack(world, owner_entity_id=owner)
    system = InteractionSystem()

    system.update(world, 16)
    assert world.get_component(floor_id, Interaction).state == "idle"

    world.destroy_entity(attack_id)
    world.get_component(owner, Collider).on_ground = True
    system.update(world, 16)
    assert world.get_component(floor_id, Interaction).state == "idle"

    missing_owner_attack = _spawn_attack(world, owner_entity_id=99_999)
    system.update(world, 16)
    assert world.get_component(floor_id, Interaction).state == "idle"
    world.destroy_entity(missing_owner_attack)

    health = world.get_component(owner, Health)
    health.current = 0
    health.dead = True
    _spawn_attack(world, owner_entity_id=owner)
    system.update(world, 16)
    assert world.get_component(floor_id, Interaction).state == "idle"

    health.current = 10
    health.dead = False
    system.update(world, 16)
    assert world.get_component(floor_id, Interaction).state == "broken"
    first_hash = world.world_hash()
    system.update(world, 16)
    assert world.world_hash() == first_hash


def test_floor_rejects_non_slam_even_when_interaction_kind_matches() -> None:
    world = World()
    owner = world.create_entity()
    world.add_component(owner, Health(10, 10))
    world.add_component(owner, Collider(28, 28, on_ground=True))
    floor_id = _spawn_floor(world)
    _spawn_attack(world, owner_entity_id=owner, attack_kind="not_a_slam")

    InteractionSystem().update(world, 16)

    assert world.get_component(floor_id, Interaction).state == "idle"


def test_attack_hit_set_hash_is_json_safe_and_history_independent() -> None:
    expected = {1, 33, 65, 129, 257}
    first_hits: set[int] = set()
    for entity_id in (257, 1, 129, 33, 65):
        first_hits.add(entity_id)
    second_hits = set(range(600))
    second_hits.difference_update(set(range(600)) - expected)

    first = World(seed=91)
    second = World(seed=91)
    first_attack = _spawn_attack(first, owner_entity_id=1, hit_entity_ids=first_hits)
    second_attack = _spawn_attack(second, owner_entity_id=1, hit_entity_ids=second_hits)

    assert first_attack == second_attack
    assert first.world_hash() == second.world_hash()
    first.get_component(first_attack, Attack).hit_entity_ids.add(513)
    assert first.world_hash() != second.world_hash()
