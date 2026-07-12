"""Resolve deterministic attack overlaps with authored stage interactions."""

from __future__ import annotations

from windsprig.core.ecs import World
from windsprig.gameplay.components import Attack, Collider, Health, Interaction, Transform
from windsprig.math2d import Rect

type _InteractionPair = tuple[int, Attack, int, Interaction]


class InteractionSystem:
    """Apply each matching authored interaction transition at most once."""

    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        for _, attack, _, interaction in _ordered_overlap_pairs(world):
            if interaction.state != "idle":
                continue
            if interaction.kind == "conductor":
                interaction.state = "energized"
            elif interaction.kind == "switch":
                interaction.state = "activated"
            elif (
                interaction.kind == "breakable_floor"
                and attack.attack_kind == "ground_slam"
                and _owner_is_living_and_grounded(world, attack.owner_entity_id)
            ):
                interaction.state = "broken"


def _ordered_overlap_pairs(world: World) -> tuple[_InteractionPair, ...]:
    pairs: list[_InteractionPair] = []
    interaction_rows = world.query(Interaction, Transform, Collider)
    for attack_id, attack, attack_transform, attack_collider in world.query(
        Attack,
        Transform,
        Collider,
    ):
        attack_rect = Rect(
            attack_transform.x,
            attack_transform.y,
            attack_collider.width,
            attack_collider.height,
        )
        for interaction_id, interaction, interaction_transform, interaction_collider in interaction_rows:
            if attack.interaction_kind != interaction.kind:
                continue
            interaction_rect = Rect(
                interaction_transform.x,
                interaction_transform.y,
                interaction_collider.width,
                interaction_collider.height,
            )
            if attack_rect.intersects(interaction_rect):
                pairs.append((attack_id, attack, interaction_id, interaction))
    pairs.sort(key=lambda pair: (pair[0], pair[2]))
    return tuple(pairs)


def _owner_is_living_and_grounded(world: World, owner_entity_id: int) -> bool:
    if owner_entity_id not in world.alive_entities:
        return False
    health = world.try_component(owner_entity_id, Health)
    collider = world.try_component(owner_entity_id, Collider)
    return health is not None and collider is not None and health.current > 0 and not health.dead and collider.on_ground
