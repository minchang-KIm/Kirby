"""Strict deterministic validation for mutable gameplay queue resources."""

from __future__ import annotations

import math
from typing import cast

from windsprig.gameplay.components import (
    AttackRequest,
    DamageRecord,
    PendingEnemyLaunch,
)


def validate_attack_requests(value: object) -> tuple[AttackRequest, ...]:
    """Return an immutable view after validating every request and field."""

    if type(value) is not list:
        raise TypeError("attack_requests must be a list of AttackRequest values")
    requests = cast(list[object], value)
    validated: list[AttackRequest] = []
    for request in requests:
        if type(request) is not AttackRequest:
            raise TypeError("attack_requests must be a list of AttackRequest values")
        _validate_attack_request(request)
        validated.append(request)
    return tuple(validated)


def validate_damage_queue(value: object) -> tuple[DamageRecord, ...]:
    """Return an immutable view after validating every damage record and field."""

    if type(value) is not list:
        raise TypeError("damage_queue must be a list of DamageRecord values")
    records = cast(list[object], value)
    validated: list[DamageRecord] = []
    for record in records:
        if type(record) is not DamageRecord:
            raise TypeError("damage_queue must be a list of DamageRecord values")
        _validate_damage_record(record)
        validated.append(record)
    return tuple(validated)


def validate_pending_enemy_launches(value: object) -> tuple[PendingEnemyLaunch, ...]:
    """Return an immutable view after validating every pending launch and field."""

    if type(value) is not list:
        raise TypeError("pending_enemy_launches must be a list of PendingEnemyLaunch values")
    launches = cast(list[object], value)
    validated: list[PendingEnemyLaunch] = []
    for launch in launches:
        if type(launch) is not PendingEnemyLaunch:
            raise TypeError("pending_enemy_launches must be a list of PendingEnemyLaunch values")
        _positive_int(launch.player_id, "PendingEnemyLaunch.player_id")
        _positive_int(launch.enemy_id, "PendingEnemyLaunch.enemy_id")
        validated.append(launch)
    return tuple(validated)


def _validate_attack_request(request: AttackRequest) -> None:
    _positive_int(request.owner_entity_id, "AttackRequest.owner_entity_id")
    _team(request.team)
    _non_empty_string(request.ability_id, "AttackRequest.ability_id")
    _non_empty_string(request.attack_kind, "AttackRequest.attack_kind")
    _non_empty_string(request.visual_id, "AttackRequest.visual_id")
    _finite_number(request.x, "AttackRequest.x")
    _finite_number(request.y, "AttackRequest.y")
    _positive_int(request.width, "AttackRequest.width")
    _positive_int(request.height, "AttackRequest.height")
    _finite_number(request.vx, "AttackRequest.vx")
    _finite_number(request.vy, "AttackRequest.vy")
    _positive_int(request.damage, "AttackRequest.damage")
    _finite_number(request.knockback_x, "AttackRequest.knockback_x")
    _finite_number(request.knockback_y, "AttackRequest.knockback_y")
    _positive_int(request.ttl_ms, "AttackRequest.ttl_ms")
    _non_negative_int(request.pierce, "AttackRequest.pierce")
    _exact_bool(request.cuts_projectiles, "AttackRequest.cuts_projectiles")
    _exact_bool(request.guard_break, "AttackRequest.guard_break")
    _non_negative_number(request.pull_strength, "AttackRequest.pull_strength")
    if request.interaction_kind is not None:
        _non_empty_string(
            request.interaction_kind,
            "AttackRequest.interaction_kind",
        )


def _validate_damage_record(record: DamageRecord) -> None:
    _non_negative_int(record.source_id, "DamageRecord.source_id")
    _positive_int(record.target_id, "DamageRecord.target_id")
    _positive_int(record.amount, "DamageRecord.amount")
    _finite_number(record.knockback_x, "DamageRecord.knockback_x")
    _finite_number(record.knockback_y, "DamageRecord.knockback_y")
    _exact_bool(record.guard_break, "DamageRecord.guard_break")
    if record.attack_id is not None:
        _positive_int(record.attack_id, "DamageRecord.attack_id")


def _team(value: object) -> None:
    if type(value) is not str:
        raise TypeError("AttackRequest.team must be a string")
    if value not in {"player", "enemy"}:
        raise ValueError("AttackRequest.team must be player or enemy")


def _non_empty_string(value: object, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    if not value:
        raise ValueError(f"{field} must be non-empty")


def _positive_int(value: object, field: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _non_negative_int(value: object, field: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")


def _finite_number(value: object, field: str) -> float:
    if type(value) not in {int, float}:
        raise TypeError(f"{field} must be a number")
    number = float(cast(int | float, value))
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _non_negative_number(value: object, field: str) -> None:
    number = _finite_number(value, field)
    if number < 0.0:
        raise ValueError(f"{field} must be non-negative")


def _exact_bool(value: object, field: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field} must be a boolean")


__all__ = [
    "validate_attack_requests",
    "validate_damage_queue",
    "validate_pending_enemy_launches",
]
