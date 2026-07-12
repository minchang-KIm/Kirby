"""Focused ECS component lifecycle contracts."""

from __future__ import annotations

from windsprig.core.ecs import World
from windsprig.gameplay.components import CapturedBy


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
