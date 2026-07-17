"""Resolve canonical attacks plus preserved legacy combat contacts."""

from __future__ import annotations

import math
from typing import cast

from windsprig.core.ecs import World
from windsprig.gameplay.abilities.voltsong import select_chain_targets
from windsprig.gameplay.components import (
    Attack,
    AttackRequest,
    CapturedBy,
    Collider,
    DamageRecord,
    EnemyAI,
    Health,
    Projectile,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish
from windsprig.math2d import Rect

type TargetRow = tuple[int, Team, Transform, Collider, Health]
type EnemyContactRow = tuple[int, Team, Transform, Collider, Health, EnemyAI]


class CombatSystem:
    """Resolve sorted attack contacts without owning canonical attack motion."""

    def update(self, world: World, dt_ms: int) -> None:
        damage_queue = cast(
            list[DamageRecord],
            world.resources.setdefault("damage_queue", []),
        )
        attack_requests = cast(
            list[AttackRequest],
            world.resources.setdefault("attack_requests", []),
        )
        to_destroy: set[int] = set()
        targets = cast(
            list[TargetRow],
            world.query(Team, Transform, Collider, Health),
        )

        self._cut_projectiles(world, to_destroy)
        self._resolve_attacks(
            world,
            targets,
            damage_queue,
            attack_requests,
            to_destroy,
        )
        self._resolve_legacy_projectiles(world, dt_ms, targets, damage_queue, to_destroy)
        self._resolve_body_contacts(world, targets, damage_queue)

        for entity_id in sorted(to_destroy):
            world.destroy_entity(entity_id)

    @staticmethod
    def _cut_projectiles(world: World, to_destroy: set[int]) -> None:
        rows = world.query(Attack, Team, Transform, Collider, Velocity)
        for cutter_id, cutter, cutter_team, cutter_tf, cutter_col, _ in rows:
            if not cutter.cuts_projectiles or cutter_id in to_destroy:
                continue
            cutter_rect = Rect(cutter_tf.x, cutter_tf.y, cutter_col.width, cutter_col.height)
            for projectile_id, _, projectile_team, projectile_tf, projectile_col, velocity in rows:
                if projectile_id == cutter_id or projectile_id in to_destroy:
                    continue
                if projectile_team.name == cutter_team.name:
                    continue
                if velocity.vx == 0.0 and velocity.vy == 0.0:
                    continue
                projectile_rect = Rect(
                    projectile_tf.x,
                    projectile_tf.y,
                    projectile_col.width,
                    projectile_col.height,
                )
                if not cutter_rect.intersects(projectile_rect):
                    continue
                to_destroy.add(projectile_id)
                publish(
                    world,
                    GameplayTopic.PROJECTILE_CUT,
                    cutter_attack_id=cutter_id,
                    projectile_attack_id=projectile_id,
                )

    @staticmethod
    def _resolve_attacks(
        world: World,
        targets: list[TargetRow],
        damage_queue: list[DamageRecord],
        attack_requests: list[AttackRequest],
        to_destroy: set[int],
    ) -> None:
        for attack_id, attack, transform, collider in world.query(
            Attack,
            Transform,
            Collider,
        ):
            if attack_id in to_destroy:
                continue
            ordered_targets = _ordered_targets(
                world,
                attack,
                transform,
                collider,
                targets,
            )
            for target_id, _, target_tf, target_col, _ in ordered_targets:
                attack.hit_entity_ids.add(target_id)
                damage_queue.append(
                    DamageRecord(
                        source_id=attack.owner_entity_id,
                        target_id=target_id,
                        amount=attack.damage,
                        knockback_x=attack.knockback_x,
                        knockback_y=attack.knockback_y,
                        guard_break=attack.guard_break,
                        attack_id=attack_id,
                    )
                )
                if attack.interaction_kind == "spawn_burn_zone":
                    attack_requests.append(
                        _burn_zone_request(attack.owner_entity_id, attack.team, target_tf, target_col)
                    )
                if attack.pull_strength > 0.0:
                    _apply_pull(world, attack, target_id, target_tf)
                if attack.pierce_remaining <= 0:
                    to_destroy.add(attack_id)
                    break
                attack.pierce_remaining -= 1

    @staticmethod
    def _resolve_legacy_projectiles(
        world: World,
        dt_ms: int,
        targets: list[TargetRow],
        damage_queue: list[DamageRecord],
        to_destroy: set[int],
    ) -> None:
        dt_s = dt_ms / 1000.0
        for projectile_id, projectile, team, transform, collider, velocity in world.query(
            Projectile,
            Team,
            Transform,
            Collider,
            Velocity,
        ):
            if world.has_component(projectile_id, Attack):
                continue
            transform.x += velocity.vx * dt_s
            transform.y += velocity.vy * dt_s
            projectile.ttl_ms -= dt_ms
            if projectile.ttl_ms <= 0:
                to_destroy.add(projectile_id)
                continue

            projectile_rect = Rect(transform.x, transform.y, collider.width, collider.height)
            for target_id, target_team, target_tf, target_col, target_hp in targets:
                if target_id == projectile.owner or target_hp.dead:
                    continue
                if target_team.name == team.name:
                    continue
                target_rect = Rect(target_tf.x, target_tf.y, target_col.width, target_col.height)
                if not projectile_rect.intersects(target_rect):
                    continue
                damage_queue.append(
                    DamageRecord(
                        source_id=projectile.owner,
                        target_id=target_id,
                        amount=projectile.damage,
                        knockback_x=velocity.vx * 0.5,
                        knockback_y=min(-120.0, velocity.vy * 0.5),
                        guard_break=False,
                    )
                )
                to_destroy.add(projectile_id)
                break

    @staticmethod
    def _resolve_body_contacts(
        world: World,
        targets: list[TargetRow],
        damage_queue: list[DamageRecord],
    ) -> None:
        players = [row for row in targets if row[1].name == "player"]
        enemies: list[EnemyContactRow] = []
        for row in targets:
            if row[1].name != "enemy" or not row[3].solid or world.has_component(row[0], CapturedBy):
                continue
            ai = world.try_component(row[0], EnemyAI)
            if ai is not None:
                enemies.append((*row, ai))
        for player_id, _, player_tf, player_col, player_hp in players:
            if player_hp.dead:
                continue
            player_rect = Rect(player_tf.x, player_tf.y, player_col.width, player_col.height)
            for enemy_id, _, enemy_tf, enemy_col, enemy_hp, ai in enemies:
                if enemy_hp.dead:
                    continue
                enemy_rect = Rect(enemy_tf.x, enemy_tf.y, enemy_col.width, enemy_col.height)
                if player_rect.intersects(enemy_rect):
                    damage_queue.append(
                        DamageRecord(
                            source_id=enemy_id,
                            target_id=player_id,
                            amount=2 if ai.kind == "boss" else 1,
                            knockback_x=180.0 if enemy_tf.x <= player_tf.x else -180.0,
                            knockback_y=-120.0,
                            guard_break=False,
                        )
                    )


def _ordered_targets(
    world: World,
    attack: Attack,
    transform: Transform,
    collider: Collider,
    rows: list[TargetRow],
) -> list[TargetRow]:
    eligible: list[TargetRow] = []
    attack_rect = Rect(transform.x, transform.y, collider.width, collider.height)
    for target_id, team, target_tf, target_col, health in rows:
        if (
            target_id == attack.owner_entity_id
            or team.name == attack.team
            or health.dead
            or target_id in attack.hit_entity_ids
        ):
            continue
        target_rect = Rect(target_tf.x, target_tf.y, target_col.width, target_col.height)
        if attack.attack_kind != "chain_pulse" and not attack_rect.intersects(target_rect):
            continue
        eligible.append((target_id, team, target_tf, target_col, health))

    owner = world.try_component(attack.owner_entity_id, Transform)
    origin = (owner.x, owner.y) if owner is not None else (transform.x, transform.y)
    if attack.attack_kind == "chain_pulse":
        selected = select_chain_targets(
            origin,
            [(target_id, target_tf.x, target_tf.y) for target_id, _, target_tf, _, _ in eligible],
            limit=attack.pierce_remaining + 1,
        )
        by_id = {row[0]: row for row in eligible}
        return [by_id[target_id] for target_id in selected]
    if attack.attack_kind == "screen_tempest":
        return sorted(
            eligible,
            key=lambda row: (_distance_squared(origin, row[2]), row[0]),
        )
    return sorted(eligible, key=lambda row: row[0])


def _distance_squared(origin: tuple[float, float], target: Transform) -> float:
    return (target.x - origin[0]) ** 2 + (target.y - origin[1]) ** 2


def _burn_zone_request(
    owner_id: int,
    team: str,
    target: Transform,
    collider: Collider,
) -> AttackRequest:
    width = 48
    height = 30
    return AttackRequest(
        owner_entity_id=owner_id,
        team=team,
        ability_id="none",
        attack_kind="burn_zone",
        visual_id="cinder_burn_zone",
        x=target.x + (collider.width - width) / 2.0,
        y=target.y + collider.height - height,
        width=width,
        height=height,
        vx=0.0,
        vy=0.0,
        damage=1,
        knockback_x=0.0,
        knockback_y=0.0,
        ttl_ms=960,
        pierce=10_000,
    )


def _apply_pull(
    world: World,
    attack: Attack,
    target_id: int,
    target: Transform,
) -> None:
    ai = world.try_component(target_id, EnemyAI)
    velocity = world.try_component(target_id, Velocity)
    owner = world.try_component(attack.owner_entity_id, Transform)
    if ai is None or ai.kind == "brute" or velocity is None or owner is None:
        return
    dx = owner.x - target.x
    dy = owner.y - target.y
    distance = math.hypot(dx, dy)
    if distance == 0.0:
        return
    velocity.vx += dx / distance * attack.pull_strength
    velocity.vy += dy / distance * attack.pull_strength


__all__ = ["CombatSystem"]
