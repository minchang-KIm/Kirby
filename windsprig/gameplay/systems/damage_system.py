"""Apply typed damage records with dodge and directional guard rules."""

from __future__ import annotations

import math
from typing import cast

from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    ActorState,
    Collider,
    DamageRecord,
    DefenseState,
    Facing,
    Health,
    PlayerSlot,
    Respawn,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.state_machine import transition
from windsprig.gameplay.validation import validate_damage_queue


class DamageSystem:
    """Consume complete damage records and publish canonical player hits."""

    def update(self, world: World, dt_ms: int) -> None:
        config = cast(GameConfig, world.resources["config"])
        raw_queue = world.resources.get("damage_queue")
        validate_damage_queue(raw_queue)
        queue = cast(list[DamageRecord], raw_queue)

        for _, health in world.query(Health):
            health.invulnerable_ms = max(0, health.invulnerable_ms - dt_ms)
        while queue:
            item = queue.pop(0)
            target_id = item.target_id
            health = world.try_component(target_id, Health)
            if health is None or health.dead or health.invulnerable_ms > 0:
                continue

            defense = world.try_component(target_id, DefenseState)
            # WHY: the strict cutoff yields eight invulnerable 16 ms dodge snapshots.
            if (
                defense is not None
                and defense.dodge_remaining_ms > config.dodge_duration_ms - config.dodge_invulnerable_ms
            ):
                continue

            guarded = _is_front_guard(world, item)
            amount = max(1, math.ceil(item.amount * config.guard_damage_multiplier)) if guarded else item.amount
            knockback_scale = config.guard_knockback_multiplier if guarded else 1.0
            knockback_x = item.knockback_x * knockback_scale
            knockback_y = item.knockback_y * knockback_scale

            health.current -= amount
            health.invulnerable_ms = config.invulnerable_ms
            velocity = world.try_component(target_id, Velocity)
            if velocity is not None:
                velocity.vx += knockback_x
                velocity.vy += knockback_y

            if item.attack_id is not None:
                publish(
                    world,
                    GameplayTopic.ATTACK_HIT,
                    attack_id=item.attack_id,
                    owner_id=item.source_id,
                    target_id=target_id,
                    damage=amount,
                    guarded=guarded,
                )

            slot = world.try_component(target_id, PlayerSlot)
            if slot is not None:
                publish(
                    world,
                    GameplayTopic.PLAYER_DAMAGED,
                    source_id=item.source_id,
                    target_id=target_id,
                    slot=slot.slot,
                    amount=amount,
                    guarded=guarded,
                    knockback_x=knockback_x,
                    knockback_y=knockback_y,
                )

            state = world.try_component(target_id, ActorState)
            if health.current <= 0:
                health.current = 0
                health.dead = True
                if defense is not None:
                    defense.guarding = False
                if state is not None:
                    state.name = transition(state.name, "Dead")
                    state.timer_ms = 0
                if slot is not None:
                    respawn = world.try_component(target_id, Respawn)
                    if respawn is not None:
                        respawn.timer_ms = config.respawn_delay_ms
                    publish(
                        world,
                        GameplayTopic.PLAYER_DEFEATED,
                        entity_id=target_id,
                        slot=slot.slot,
                        lives_remaining=slot.lives,
                    )
                else:
                    publish(
                        world,
                        GameplayTopic.ENEMY_DEFEATED,
                        enemy_id=target_id,
                        source_id=item.source_id,
                    )
                world.events.publish("actor_dead", {"entity_id": target_id})
            elif not guarded:
                if defense is not None:
                    defense.guarding = False
                if state is not None:
                    state.name = transition(state.name, "Hurt")
                    if state.name == "Hurt":
                        state.timer_ms = config.fixed_dt_ms


def _is_front_guard(world: World, item: DamageRecord) -> bool:
    if item.target_id not in world.alive_entities or item.source_id not in world.alive_entities:
        return False
    defense = world.try_component(item.target_id, DefenseState)
    facing = world.try_component(item.target_id, Facing)
    target = world.try_component(item.target_id, Transform)
    source = world.try_component(item.source_id, Transform)
    collider = world.try_component(item.target_id, Collider)
    health = world.try_component(item.target_id, Health)
    state = world.try_component(item.target_id, ActorState)
    slot = world.try_component(item.target_id, PlayerSlot)
    if None in (defense, facing, target, source, collider, health, state, slot):
        return False
    assert defense is not None
    assert facing is not None
    assert target is not None
    assert source is not None
    assert collider is not None
    assert health is not None
    assert state is not None
    return (
        facing.direction in {-1, 1}
        and collider.on_ground
        and not health.dead
        and state.name not in {"Hurt", "Dead"}
        and defense.dodge_remaining_ms == 0
        and defense.guarding
        and not item.guard_break
        and (source.x - target.x) * facing.direction >= 0
    )
