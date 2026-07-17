"""Focused ECS component lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from windsprig.core.ecs import World
from windsprig.gameplay.components import CapturedBy


@dataclass
class _NestedSetComponent:
    payload: dict[str, object]


@dataclass
class _UnsupportedLeafComponent:
    payload: object


class _VolatileHashLeaf:
    repr_calls = 0

    def __repr__(self) -> str:
        type(self).repr_calls += 1
        return f"volatile-{type(self).repr_calls}"


class _VolatileHashComponent:
    """Unsupported top-level component whose repr exposes accidental fallback use."""

    __slots__ = ()
    repr_calls = 0

    def __repr__(self) -> str:
        type(self).repr_calls += 1
        return f"volatile-component-{type(self).repr_calls}"


def test_world_remove_component_releases_one_component_without_touching_entity() -> None:
    world = World()
    entity_id = world.create_entity()
    world.add_component(entity_id, CapturedBy(7))

    world.remove_component(entity_id, CapturedBy)
    world.remove_component(entity_id, CapturedBy)

    assert entity_id in world.alive_entities
    assert not world.has_component(entity_id, CapturedBy)


def test_remove_component_prunes_history_only_hash_state() -> None:
    changed = World()
    baseline = World()
    changed_entity = changed.create_entity()
    baseline.create_entity()
    changed.add_component(changed_entity, CapturedBy(7))

    changed.remove_component(changed_entity, CapturedBy)

    assert changed.components.debug_dump() == baseline.components.debug_dump() == {}
    assert changed.world_hash() == baseline.world_hash()


def test_destroy_entity_prunes_history_only_hash_state() -> None:
    changed = World()
    baseline = World()
    changed_entity = changed.create_entity()
    baseline_entity = baseline.create_entity()
    changed.add_component(changed_entity, CapturedBy(7))

    changed.destroy_entity(changed_entity)
    baseline.destroy_entity(baseline_entity)

    assert changed.components.debug_dump() == baseline.components.debug_dump() == {}
    assert changed.world_hash() == baseline.world_hash()


def test_world_hash_canonicalizes_supported_nested_sets_across_histories() -> None:
    first_ids: set[int] = set()
    for entity_id in (257, 1, 129, 33, 65):
        first_ids.add(entity_id)
    second_ids = set(range(600))
    second_ids.intersection_update({1, 33, 65, 129, 257})

    first = World(seed=91)
    second = World(seed=91)
    first_entity = first.create_entity()
    second_entity = second.create_entity()
    first.add_component(
        first_entity,
        _NestedSetComponent(
            {
                "ids": [first_ids],
                "groups": {frozenset({9, 3}), frozenset({7, 1})},
            }
        ),
    )
    second.add_component(
        second_entity,
        _NestedSetComponent(
            {
                "ids": [second_ids],
                "groups": {frozenset({1, 7}), frozenset({3, 9})},
            }
        ),
    )

    assert first.world_hash() == second.world_hash()
    first_ids.add(513)
    assert first.world_hash() != second.world_hash()


def test_world_hash_rejects_unsupported_nested_leaf_without_repr_fallback() -> None:
    _VolatileHashLeaf.repr_calls = 0
    world = World(seed=5)
    entity_id = world.create_entity()
    world.add_component(
        entity_id,
        _UnsupportedLeafComponent(_VolatileHashLeaf()),
    )

    with pytest.raises(
        TypeError,
        match=r"^unsupported deterministic hash value: _VolatileHashLeaf$",
    ):
        world.world_hash()

    assert _VolatileHashLeaf.repr_calls == 0


def test_world_hash_rejects_unsupported_component_without_repr_fallback() -> None:
    _VolatileHashComponent.repr_calls = 0
    world = World(seed=8)
    entity_id = world.create_entity()
    world.add_component(entity_id, _VolatileHashComponent())

    with pytest.raises(
        TypeError,
        match=r"^unsupported deterministic hash value: _VolatileHashComponent$",
    ):
        world.world_hash()

    assert _VolatileHashComponent.repr_calls == 0
