"""Collect overlapping run pickups exactly once and publish their result."""

from __future__ import annotations

from typing import cast

from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AbilityState,
    Collectible,
    Collider,
    EchoPickup,
    Health,
    PlayerSlot,
    Team,
    Transform,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.math2d import Rect


class PickupSystem:
    """Apply collectible overlap only to living player entities."""

    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        deferred_echo_ids = cast(
            set[int],
            world.resources.pop("deferred_echo_pickup_ids", set()),
        )
        collectible_players = [
            row
            for row in world.query(Team, Transform, Collider, Health)
            if row[1].name == "player" and not row[4].dead
        ]
        to_destroy: set[int] = set()
        for collectible_id, collectible, ctf, ccol in world.query(Collectible, Transform, Collider):
            if collectible.collected:
                continue
            crect = Rect(ctf.x, ctf.y, ccol.width, ccol.height)
            for _, _, ptf, pcol, _ in collectible_players:
                prect = Rect(ptf.x, ptf.y, pcol.width, pcol.height)
                if prect.intersects(crect):
                    collectible.collected = True
                    world.resources["run_energy_spheres"] = (
                        world.resources.get("run_energy_spheres", 0) + collectible.value
                    )
                    world.events.publish("collectible_picked", {"kind": collectible.kind, "value": collectible.value})
                    to_destroy.add(collectible_id)
                    break
        for entity_id in to_destroy:
            world.destroy_entity(entity_id)

        echo_players = [
            row
            for row in world.query(
                PlayerSlot,
                Team,
                Transform,
                Collider,
                Health,
                AbilityState,
            )
            if row[2].name == "player" and not row[5].dead
        ]
        for pickup_id, echo, echo_tf, echo_col in world.query(
            EchoPickup,
            Transform,
            Collider,
        ):
            if pickup_id in deferred_echo_ids:
                continue
            echo_rect = Rect(echo_tf.x, echo_tf.y, echo_col.width, echo_col.height)
            for player_id, _, _, player_tf, player_col, _, ability in echo_players:
                player_rect = Rect(
                    player_tf.x,
                    player_tf.y,
                    player_col.width,
                    player_col.height,
                )
                if not player_rect.intersects(echo_rect):
                    continue
                ability.previous_id = ability.current_id
                ability.current_id = echo.ability_id
                cast(
                    set[str],
                    world.resources.setdefault("discovered_ability_ids", set()),
                ).add(echo.ability_id)
                publish(
                    world,
                    GameplayTopic.ABILITY_EQUIPPED,
                    player_id=player_id,
                    ability_id=echo.ability_id,
                    source="echo_pickup",
                )
                world.destroy_entity(pickup_id)
                break
