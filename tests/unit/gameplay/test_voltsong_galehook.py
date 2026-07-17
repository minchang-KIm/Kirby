"""Exact Voltsong, Galehook, and authored interaction contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.helpers.gameplay import ability_context, make_runtime
from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.abilities import (
    AbilityRegistry,
    GalehookStrategy,
    StoneheartStrategy,
    TempestStrategy,
    VoltsongStrategy,
    create_default_registry,
    select_chain_targets,
)
from windsprig.gameplay.components import Attack, Collider, Interaction, Transform
from windsprig.gameplay.systems import InteractionSystem
from windsprig.gameplay.systems.interaction_system import _ordered_overlap_pairs


def _spawn_attack(
    world: World,
    *,
    attack_kind: str,
    interaction_kind: str | None,
    x: float = 32.0,
    y: float = 32.0,
    owner_entity_id: int = 999,
) -> int:
    entity_id = world.create_entity()
    world.add_component(
        entity_id,
        Attack(
            owner_entity_id=owner_entity_id,
            team="player",
            attack_kind=attack_kind,
            visual_id=f"test.{attack_kind}",
            damage=1,
            knockback_x=0.0,
            knockback_y=0.0,
            ttl_ms=100,
            pierce_remaining=0,
            cuts_projectiles=False,
            guard_break=False,
            pull_strength=0.0,
            interaction_kind=interaction_kind,
            born_frame=0,
        ),
    )
    world.add_component(entity_id, Transform(x, y))
    world.add_component(entity_id, Collider(24, 24, solid=False))
    return entity_id


def _spawn_interaction(
    world: World,
    *,
    interaction_id: str,
    kind: str,
    x: float = 32.0,
    y: float = 32.0,
) -> int:
    entity_id = world.create_entity()
    world.add_component(entity_id, Interaction(interaction_id, kind))
    world.add_component(entity_id, Transform(x, y))
    world.add_component(entity_id, Collider(32, 32, solid=False))
    return entity_id


def test_voltsong_emits_one_exact_conductor_chain_pulse() -> None:
    execution = VoltsongStrategy().activate(ability_context(facing=-1))

    assert len(execution.attacks) == 1
    attack = execution.attacks[0]
    assert (
        attack.ability_id,
        attack.attack_kind,
        attack.damage,
        attack.interaction_kind,
    ) == ("voltsong", "chain_pulse", 2, "conductor")
    assert attack.owner_entity_id == 1


def test_chain_selection_includes_radius_boundary_and_uses_distance_then_id() -> None:
    candidates = (
        (40, 132.0001, 0.0),
        (9, 132.0, 0.0),
        (7, 0.0, -10.0),
        (3, 6.0, 8.0),
        (1, 0.0, 10.0),
    )

    assert select_chain_targets((0.0, 0.0), candidates) == (1, 3, 7)
    assert select_chain_targets((0.0, 0.0), tuple(reversed(candidates))) == (1, 3, 7)
    assert select_chain_targets((0.0, 0.0), candidates, limit=4) == (1, 3, 7, 9)
    assert select_chain_targets((0.0, 0.0), candidates, limit=0) == ()


def test_chain_selection_honors_custom_origin_radius_and_limit() -> None:
    candidates = ((8, 14.0, 20.0), (2, 10.0, 24.0), (4, 13.0, 24.0))

    assert select_chain_targets((10.0, 20.0), candidates, radius_px=4.0, limit=2) == (2, 8)


def test_galehook_emits_one_exact_outbound_boomerang_request() -> None:
    execution = GalehookStrategy().activate(ability_context(facing=-1))

    assert len(execution.attacks) == 1
    attack = execution.attacks[0]
    assert (
        attack.ability_id,
        attack.attack_kind,
        attack.damage,
        attack.ttl_ms,
        attack.pull_strength,
        attack.interaction_kind,
    ) == ("galehook", "boomerang", 2, 800, 260.0, "switch")
    assert attack.vx < 0.0


def test_registry_resolves_each_public_family_to_one_distinct_strategy() -> None:
    registry = create_default_registry(GameConfig().content_dir)

    assert registry.names() == [
        "bloomblade",
        "cinder",
        "galehook",
        "none",
        "stoneheart",
        "tempest",
        "voltsong",
    ]
    assert isinstance(registry.get("voltsong"), VoltsongStrategy)
    assert isinstance(registry.get("galehook"), GalehookStrategy)
    assert isinstance(registry.get("stoneheart"), StoneheartStrategy)
    assert isinstance(registry.get("tempest"), TempestStrategy)
    assert registry.get("unknown") is registry.get("none")

    context = ability_context(on_ground=False, meter=100)
    signatures = {
        (
            attack.attack_kind,
            attack.ttl_ms,
            attack.interaction_kind,
        )
        for ability_id in (
            "bloomblade",
            "cinder",
            "voltsong",
            "galehook",
            "stoneheart",
            "tempest",
        )
        for attack in registry.get(ability_id).activate(context).attacks
    }
    assert len(signatures) == 6


def test_registry_keeps_strict_metadata_validation_and_requires_none_fallback(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="no 'none' strategy"):
        AbilityRegistry().get("missing")

    registry = create_default_registry(GameConfig().content_dir)
    valid = json.loads(Path("windsprig/content/abilities.json").read_text(encoding="utf-8"))
    invalid_rows: list[tuple[object, str]] = [
        ([[]], "only the 'abilities' object"),
        ({"abilities": {}}, "exactly the six public ability IDs"),
    ]
    missing_field = copy.deepcopy(valid)
    del missing_field["abilities"]["bloomblade"]["icon_id"]
    invalid_rows.append((missing_field, "invalid fields"))
    empty_value = copy.deepcopy(valid)
    empty_value["abilities"]["bloomblade"]["icon_id"] = ""
    invalid_rows.append((empty_value, "non-empty strings"))
    mismatched = copy.deepcopy(valid)
    mismatched["abilities"]["bloomblade"]["strategy"] = "cinder"
    invalid_rows.append((mismatched, "mismatched strategy"))

    for index, (payload, message) in enumerate(invalid_rows):
        path = tmp_path / f"invalid-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            registry.validate_metadata(path)


def test_conductor_and_switch_transitions_are_matching_ordered_and_idempotent() -> None:
    world = World()
    switch_id = _spawn_interaction(world, interaction_id="z.switch", kind="switch")
    conductor_id = _spawn_interaction(world, interaction_id="a.conductor", kind="conductor")
    future_id = _spawn_interaction(world, interaction_id="m.future", kind="gust_lift")
    _spawn_attack(world, attack_kind="boomerang", interaction_kind="switch")
    _spawn_attack(world, attack_kind="chain_pulse", interaction_kind="conductor")
    _spawn_attack(world, attack_kind="mismatch", interaction_kind="breakable_floor")
    system = InteractionSystem()

    system.update(world, 16)

    assert world.get_component(switch_id, Interaction).state == "activated"
    assert world.get_component(conductor_id, Interaction).state == "energized"
    assert world.get_component(future_id, Interaction).state == "idle"
    assert world.events.peek() == []
    first_hash = world.world_hash()

    system.update(world, 16)

    assert world.world_hash() == first_hash


def test_overlap_pairs_use_attack_and_interaction_entity_ids_not_authored_names() -> None:
    world = World()
    first_interaction = _spawn_interaction(
        world,
        interaction_id="z.authored-first",
        kind="conductor",
    )
    second_interaction = _spawn_interaction(
        world,
        interaction_id="a.authored-second",
        kind="conductor",
    )
    first_attack = _spawn_attack(
        world,
        attack_kind="chain_pulse",
        interaction_kind="conductor",
    )
    second_attack = _spawn_attack(
        world,
        attack_kind="chain_pulse",
        interaction_kind="conductor",
    )

    pairs = _ordered_overlap_pairs(world)

    assert tuple((pair[0], pair[2]) for pair in pairs) == (
        (first_attack, first_interaction),
        (first_attack, second_interaction),
        (second_attack, first_interaction),
        (second_attack, second_interaction),
    )


def test_runtime_installs_interactions_between_damage_and_pickups() -> None:
    runtime = make_runtime()
    names = tuple(type(system).__name__ for system in runtime.world.scheduler.systems)

    assert names[names.index("DamageSystem") + 1] == "InteractionSystem"
    assert names[names.index("InteractionSystem") + 1] == "PickupSystem"
