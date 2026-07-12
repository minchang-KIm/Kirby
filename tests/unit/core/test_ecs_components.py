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
