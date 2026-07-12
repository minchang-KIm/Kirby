"""Materialize typed attack requests as stable ECS entities."""

from __future__ import annotations

from typing import cast

from windsprig.core.ecs import World
from windsprig.gameplay.bosses import (
    BossCommand,
    BossState,
    boss_command_sort_key,
)
from windsprig.gameplay.components import (
    Attack,
    AttackRequest,
    Collider,
    PendingEnemyLaunch,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, publish


class AttackSpawnSystem:
    """Drain the request FIFO once and publish IDs only after creation."""

    def update(self, world: World, dt_ms: int) -> None:
        _ = dt_ms
        requests = cast(list[AttackRequest], world.resources.setdefault("attack_requests", []))
        pending_launches = cast(
            list[PendingEnemyLaunch],
            world.resources.setdefault("pending_enemy_launches", []),
        )
        boss_requests, retained = _boss_requests(world)
        world.resources["boss_commands"] = retained

        queued = tuple(requests) + boss_requests
        requests.clear()
        for request in queued:
            attack_id = _spawn(world, request)
            publish(
                world,
                GameplayTopic.ATTACK_SPAWNED,
                attack_id=attack_id,
                owner_id=request.owner_entity_id,
                attack_kind=request.attack_kind,
                visual_id=request.visual_id,
            )
            if request.attack_kind == "launched_enemy" and pending_launches:
                launch = pending_launches.pop(0)
                publish(
                    world,
                    GameplayTopic.ENEMY_LAUNCHED,
                    player_id=launch.player_id,
                    enemy_id=launch.enemy_id,
                    attack_id=attack_id,
                )
            if request.ability_id != "none":
                publish(
                    world,
                    GameplayTopic.ABILITY_USED,
                    player_id=request.owner_entity_id,
                    ability_id=request.ability_id,
                    attack_ids=(attack_id,),
                )


def _spawn(world: World, request: AttackRequest) -> int:
    attack_id = world.create_entity()
    world.add_component(attack_id, Transform(request.x, request.y))
    world.add_component(attack_id, Velocity(request.vx, request.vy))
    world.add_component(
        attack_id,
        Collider(width=request.width, height=request.height, solid=False),
    )
    world.add_component(attack_id, Team(request.team))
    world.add_component(
        attack_id,
        Attack(
            owner_entity_id=request.owner_entity_id,
            team=request.team,
            attack_kind=request.attack_kind,
            visual_id=request.visual_id,
            damage=request.damage,
            knockback_x=request.knockback_x,
            knockback_y=request.knockback_y,
            ttl_ms=request.ttl_ms,
            pierce_remaining=request.pierce,
            cuts_projectiles=request.cuts_projectiles,
            guard_break=request.guard_break,
            pull_strength=request.pull_strength,
            interaction_kind=request.interaction_kind,
            born_frame=world.frame_index,
        ),
    )
    return attack_id


def _boss_requests(world: World) -> tuple[tuple[AttackRequest, ...], tuple[BossCommand, ...]]:
    commands = cast(tuple[BossCommand, ...], world.resources.get("boss_commands", ()))
    boss_rows = world.query(BossState)
    if len(boss_rows) != 1:
        return (), commands
    owner_id = cast(int, boss_rows[0][0])
    requests: list[AttackRequest] = []
    retained: list[BossCommand] = []
    for command in commands:
        request = _boss_request(owner_id, command)
        if request is None:
            retained.append(command)
        else:
            requests.append(request)
    return tuple(requests), tuple(sorted(retained, key=boss_command_sort_key))


def _boss_request(owner_id: int, command: BossCommand) -> AttackRequest | None:
    if command.command != "execute":
        return None
    values = dict(command.parameters)
    integer_names = ("width", "height", "damage", "ttl_ms")
    numeric_names = ("x", "y", "vx", "vy", "knockback_x", "knockback_y")
    if any(type(values.get(name)) is not int for name in integer_names):
        return None
    if any(type(values.get(name)) not in {int, float} for name in numeric_names):
        return None
    if "pierce" in values and type(values["pierce"]) is not int:
        return None
    if "cuts_projectiles" in values and type(values["cuts_projectiles"]) is not bool:
        return None
    if "guard_break" in values and type(values["guard_break"]) is not bool:
        return None
    if "pull_strength" in values and type(values["pull_strength"]) not in {int, float}:
        return None
    if "interaction_kind" in values and type(values["interaction_kind"]) is not str:
        return None
    return AttackRequest(
        owner_entity_id=owner_id,
        team="enemy",
        ability_id="none",
        attack_kind=command.attack_id,
        visual_id=command.attack_id,
        x=float(values["x"]),
        y=float(values["y"]),
        width=cast(int, values["width"]),
        height=cast(int, values["height"]),
        vx=float(values["vx"]),
        vy=float(values["vy"]),
        damage=cast(int, values["damage"]),
        knockback_x=float(values["knockback_x"]),
        knockback_y=float(values["knockback_y"]),
        ttl_ms=cast(int, values["ttl_ms"]),
        pierce=cast(int, values.get("pierce", 0)),
        cuts_projectiles=cast(bool, values.get("cuts_projectiles", False)),
        guard_break=cast(bool, values.get("guard_break", False)),
        pull_strength=float(values.get("pull_strength", 0.0)),
        interaction_kind=cast(str | None, values.get("interaction_kind")),
    )


__all__ = ["AttackSpawnSystem"]
