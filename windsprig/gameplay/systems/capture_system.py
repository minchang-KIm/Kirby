"""Own deterministic draw, capture, launch, harmonize, and echo drops."""

from __future__ import annotations

from typing import cast

from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    AttackRequest,
    CapturedBy,
    CaptureState,
    Collider,
    ControlIntent,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    Health,
    PlayerSlot,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.gameplay.factory import EntityFactory
from windsprig.gameplay.state_machine import transition


def provisional_attack_request_id(requests: list[AttackRequest]) -> int:
    """Return the Task 5 ordinal that Task 8 replaces with a spawned entity ID."""
    return len(requests) + 1


class CaptureSystem:
    """Resolve one mutually exclusive terminal outcome per captured enemy."""

    def update(self, world: World, dt_ms: int) -> None:
        requests = cast(
            list[AttackRequest],
            world.resources.setdefault("attack_requests", []),
        )
        requests.clear()
        self._recover_orphaned_enemies(world)

        for (
            player_id,
            slot,
            transform,
            velocity,
            collider,
            facing,
            health,
            intent,
            capture,
            ability,
            state,
        ) in world.query(
            PlayerSlot,
            Transform,
            Velocity,
            Collider,
            Facing,
            Health,
            ControlIntent,
            CaptureState,
            AbilityState,
            ActorState,
        ):
            _ = slot
            if health.dead or state.name == "Dead":
                self._release_player_capture(world, capture)
                intent.move_axis = 0
                intent.jump_pressed = False
                intent.hover_held = False
                intent.draw_started = False
                intent.draw_released = False
                intent.ability_pressed = False
                intent.ability_consumed = False
                intent.guard_held = False
                intent.dodge_pressed = False
                intent.drop_pressed = False
                continue

            if intent.draw_started:
                draw_state = transition(state.name, "Draw")
                if capture.phase == "idle" and draw_state == "Draw":
                    capture.phase = "drawing"
                    capture.draw_elapsed_ms = 0
                    state.name = draw_state
                intent.draw_started = False

            if capture.phase == "drawing":
                capture.draw_elapsed_ms += dt_ms
                self._capture_nearest(
                    world,
                    player_id,
                    transform,
                    collider,
                    _direction(facing.direction),
                    capture,
                )

            held = self._held_enemy(world, player_id, capture)
            if capture.phase == "holding" and held is None:
                self._release_player_capture(world, capture)
                state.name = transition(state.name, _resting_state(collider, velocity))
            elif held is not None:
                _, enemy_transform, enemy_velocity, enemy_collider, _, _, _ = held
                enemy_transform.x = transform.x + (collider.width - 6) * _direction(facing.direction)
                enemy_transform.y = transform.y
                enemy_velocity.vx = 0.0
                enemy_velocity.vy = 0.0
                enemy_collider.solid = False

            harmonize_attempted = capture.phase == "holding" and intent.ability_pressed
            if harmonize_attempted:
                self._harmonize(world, player_id, intent, capture, ability, state)

            if intent.draw_released and not harmonize_attempted:
                held = self._held_enemy(world, player_id, capture)
                if held is None:
                    publish(
                        world,
                        GameplayTopic.CAPTURE_RELEASED,
                        player_id=player_id,
                        outcome="empty",
                    )
                else:
                    self._launch(world, player_id, _direction(facing.direction), capture, held, requests)
                _reset_capture(capture)
                state.name = transition(state.name, _resting_state(collider, velocity))
            if intent.draw_released:
                intent.draw_released = False

            if intent.drop_pressed:
                self._drop_ability(world, player_id, transform, ability)
                intent.drop_pressed = False

    def _capture_nearest(
        self,
        world: World,
        player_id: int,
        player_transform: Transform,
        player_collider: Collider,
        facing: int,
        capture: CaptureState,
    ) -> None:
        if capture.captured_entity_id is not None:
            return
        config = cast(GameConfig, world.resources["config"])
        draw_range = config.draw_base_range_px + min(
            config.draw_max_bonus_range_px,
            capture.draw_elapsed_ms * config.draw_range_growth_px_per_ms,
        )
        candidates: list[
            tuple[
                float,
                int,
                Transform,
                Velocity,
                Collider,
                EnemyAI,
                EnemyDropAbility,
            ]
        ] = []
        for enemy_id, team, transform, velocity, collider, health, ai, drop in world.query(
            Team,
            Transform,
            Velocity,
            Collider,
            Health,
            EnemyAI,
            EnemyDropAbility,
        ):
            if team.name != "enemy" or health.dead or ai.kind == "boss":
                continue
            if world.has_component(enemy_id, CapturedBy):
                continue
            dx = transform.x - player_transform.x
            if dx * facing < 0 or abs(dx) > draw_range:
                continue
            if abs(transform.y - player_transform.y) > player_collider.height + 10:
                continue
            candidates.append((abs(dx), enemy_id, transform, velocity, collider, ai, drop))
        if not candidates:
            return
        _, enemy_id, enemy_transform, enemy_velocity, enemy_collider, ai, drop = min(
            candidates,
            key=lambda item: (item[0], item[1]),
        )
        ability_id = None if drop.ability == "none" else drop.ability
        capture.phase = "holding"
        capture.captured_entity_id = enemy_id
        capture.captured_ability_id = ability_id
        capture.captured_visual_id = ai.kind
        world.add_component(enemy_id, CapturedBy(player_id))
        enemy_velocity.vx = 0.0
        enemy_velocity.vy = 0.0
        enemy_collider.solid = False
        enemy_transform.x = player_transform.x + (player_collider.width - 6) * facing
        enemy_transform.y = player_transform.y
        publish(
            world,
            GameplayTopic.ENEMY_CAPTURED,
            player_id=player_id,
            enemy_id=enemy_id,
            ability_id=ability_id,
            visual_id=ai.kind,
        )

    def _harmonize(
        self,
        world: World,
        player_id: int,
        intent: ControlIntent,
        capture: CaptureState,
        ability: AbilityState,
        state: ActorState,
    ) -> None:
        enemy_id = capture.captured_entity_id
        if enemy_id is None:
            return
        intent.ability_pressed = False
        intent.ability_consumed = True
        if capture.captured_ability_id is None:
            publish(
                world,
                GameplayTopic.HARMONIZE_UNAVAILABLE,
                player_id=player_id,
                enemy_id=enemy_id,
            )
            return
        ability.previous_id = ability.current_id
        ability.current_id = capture.captured_ability_id
        cast(set[str], world.resources.setdefault("discovered_ability_ids", set())).add(
            ability.current_id
        )
        publish(
            world,
            GameplayTopic.ABILITY_EQUIPPED,
            player_id=player_id,
            ability_id=ability.current_id,
            source="capture",
        )
        world.destroy_entity(enemy_id)
        _reset_capture(capture)
        state.name = transition(state.name, "Harmonize")

    def _launch(
        self,
        world: World,
        player_id: int,
        facing: int,
        capture: CaptureState,
        held: tuple[int, Transform, Velocity, Collider, Health, EnemyAI, EnemyDropAbility],
        requests: list[AttackRequest],
    ) -> None:
        enemy_id, transform, _, collider, _, _, _ = held
        attack_id = provisional_attack_request_id(requests)
        requests.append(
            AttackRequest(
                owner_entity_id=player_id,
                team="player",
                ability_id="none",
                attack_kind="launched_enemy",
                visual_id="wind_launch",
                x=transform.x,
                y=transform.y,
                width=collider.width,
                height=collider.height,
                vx=520.0 * facing,
                vy=-40.0,
                damage=4,
                knockback_x=260.0 * facing,
                knockback_y=-120.0,
                ttl_ms=480,
                pierce=0,
                cuts_projectiles=False,
                guard_break=False,
                pull_strength=0.0,
                interaction_kind=None,
            )
        )
        world.destroy_entity(enemy_id)
        publish(
            world,
            GameplayTopic.ENEMY_LAUNCHED,
            player_id=player_id,
            enemy_id=enemy_id,
            attack_id=attack_id,
        )

    def _drop_ability(
        self,
        world: World,
        player_id: int,
        transform: Transform,
        ability: AbilityState,
    ) -> None:
        if ability.current_id == "none":
            return
        dropped_id = ability.current_id
        pickup_id = EntityFactory(world).spawn_echo_pickup(dropped_id, transform.x, transform.y)
        cast(
            set[int],
            world.resources.setdefault("deferred_echo_pickup_ids", set()),
        ).add(pickup_id)
        ability.previous_id = dropped_id
        ability.current_id = "none"
        publish(
            world,
            GameplayTopic.ABILITY_DROPPED,
            player_id=player_id,
            ability_id=dropped_id,
            pickup_id=pickup_id,
        )

    def _held_enemy(
        self,
        world: World,
        player_id: int,
        capture: CaptureState,
    ) -> tuple[int, Transform, Velocity, Collider, Health, EnemyAI, EnemyDropAbility] | None:
        enemy_id = capture.captured_entity_id
        if capture.phase != "holding" or enemy_id is None or enemy_id not in world.alive_entities:
            return None
        owner = world.try_component(enemy_id, CapturedBy)
        transform = world.try_component(enemy_id, Transform)
        velocity = world.try_component(enemy_id, Velocity)
        collider = world.try_component(enemy_id, Collider)
        health = world.try_component(enemy_id, Health)
        ai = world.try_component(enemy_id, EnemyAI)
        drop = world.try_component(enemy_id, EnemyDropAbility)
        if (
            owner is None
            or owner.player_entity_id != player_id
            or transform is None
            or velocity is None
            or collider is None
            or health is None
            or health.dead
            or ai is None
            or drop is None
        ):
            return None
        return enemy_id, transform, velocity, collider, health, ai, drop

    def _recover_orphaned_enemies(self, world: World) -> None:
        for enemy_id, owner in world.query(CapturedBy):
            capture = world.try_component(owner.player_entity_id, CaptureState)
            health = world.try_component(owner.player_entity_id, Health)
            valid = (
                owner.player_entity_id in world.alive_entities
                and health is not None
                and not health.dead
                and capture is not None
                and capture.phase == "holding"
                and capture.captured_entity_id == enemy_id
            )
            if valid:
                continue
            world.remove_component(enemy_id, CapturedBy)
            collider = world.try_component(enemy_id, Collider)
            velocity = world.try_component(enemy_id, Velocity)
            if collider is not None:
                collider.solid = True
            if velocity is not None:
                velocity.vx = 0.0
                velocity.vy = 0.0

    def _release_player_capture(self, world: World, capture: CaptureState) -> None:
        enemy_id = capture.captured_entity_id
        if enemy_id is not None and enemy_id in world.alive_entities:
            collider = world.try_component(enemy_id, Collider)
            velocity = world.try_component(enemy_id, Velocity)
            world.remove_component(enemy_id, CapturedBy)
            if collider is not None:
                collider.solid = True
            if velocity is not None:
                velocity.vx = 0.0
                velocity.vy = 0.0
        _reset_capture(capture)


def _reset_capture(capture: CaptureState) -> None:
    capture.phase = "idle"
    capture.draw_elapsed_ms = 0
    capture.captured_entity_id = None
    capture.captured_ability_id = None
    capture.captured_visual_id = None


def _direction(value: int) -> int:
    return -1 if value < 0 else 1


def _resting_state(collider: Collider, velocity: Velocity) -> str:
    if not collider.on_ground:
        return "Fall"
    return "Run" if abs(velocity.vx) > 40.0 else "Idle"
