"""Strict deterministic validation for mutable gameplay queue resources."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from typing import cast

from windsprig.content.models import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AttackRequest,
    Checkpoint,
    Collider,
    DamageRecord,
    PendingEnemyLaunch,
    PlayerSlot,
    Transform,
)
from windsprig.gameplay.snapshot import StageResult
from windsprig.input.roster import ActivePlayer

type CheckpointRow = tuple[int, Checkpoint, Transform, Collider]


def validate_attack_requests(value: object) -> tuple[AttackRequest, ...]:
    """Return an immutable view after validating every request and field."""

    if type(value) is not list:
        raise TypeError("attack_requests must be a list of AttackRequest values")
    requests = cast(list[object], value)
    validated: list[AttackRequest] = []
    for request in requests:
        if type(request) is not AttackRequest:
            raise TypeError("attack_requests must be a list of AttackRequest values")
        validated.append(validate_attack_request(request))
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


def validate_attack_request(value: object) -> AttackRequest:
    """Validate one exact canonical request, including every field invariant."""

    if type(value) is not AttackRequest:
        raise TypeError("boss-derived attack must be an AttackRequest")
    request = value
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
    return request


def validate_deaths_by_slot(
    value: object,
    active_slots: tuple[int, ...] | None = None,
) -> tuple[tuple[int, int], ...]:
    """Validate mutable death counters and return their canonical immutable view."""

    if type(value) is not dict:
        raise TypeError("deaths_by_slot must be a dictionary of integer counters")
    counters = cast(dict[object, object], value)
    validated: list[tuple[int, int]] = []
    for slot, count in counters.items():
        if type(slot) is not int or not 1 <= slot <= 4:
            raise ValueError("deaths_by_slot keys must be integer slots from 1 to 4")
        if type(count) is not int or count < 0:
            raise ValueError("deaths_by_slot values must be non-negative integers")
        validated.append((slot, count))
    canonical = tuple(sorted(validated))
    if active_slots is not None and tuple(slot for slot, _ in canonical) != active_slots:
        raise ValueError("deaths_by_slot must exactly match active player slots")
    return canonical


def validate_checkpoint_state(world: World, stage: StageSpec) -> tuple[CheckpointRow, ...]:
    """Reject checkpoint geometry or activation state that diverges from the catalog."""

    if not stage.checkpoints:
        raise ValueError("stage must define at least one checkpoint")
    expected_ids = tuple(spec.checkpoint_id for spec in stage.checkpoints)
    if any(type(checkpoint_id) is not str or not checkpoint_id for checkpoint_id in expected_ids):
        raise ValueError("checkpoint IDs must be non-empty strings")
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("stage checkpoint IDs must be unique")
    expected_tiles: set[tuple[int, int]] = set()
    for spec in stage.checkpoints:
        if type(spec.tile_x) is not int or type(spec.tile_y) is not int:
            raise TypeError("checkpoint tile coordinates must be integers")
        tile = (spec.tile_x, spec.tile_y)
        if tile in expected_tiles:
            raise ValueError("stage checkpoint tile geometry must be unique")
        expected_tiles.add(tile)

    rows = cast(list[CheckpointRow], world.query(Checkpoint, Transform, Collider))
    if len(rows) != len(stage.checkpoints):
        raise ValueError("checkpoint entities must exactly match the stage catalog")
    if tuple(checkpoint.checkpoint_id for _, checkpoint, _, _ in rows) != expected_ids:
        raise ValueError("checkpoint entity order and IDs must match the stage catalog")

    active_rows: list[CheckpointRow] = []
    for row, spec in zip(rows, stage.checkpoints, strict=True):
        _, checkpoint, transform, collider = row
        if type(spec.tile_x) is not int or type(spec.tile_y) is not int:
            raise TypeError("checkpoint tile coordinates must be integers")
        if not (0 <= spec.tile_x < stage.width_tiles and 0 <= spec.tile_y < stage.height_tiles - 1):
            raise ValueError("checkpoint tile coordinates must be inside the stage")
        tile = (spec.tile_x, spec.tile_y)
        support = (spec.tile_x, spec.tile_y + 1)
        if tile in stage.solids or tile in stage.hazards:
            raise ValueError("checkpoint positions must not overlap solid or hazard tiles")
        vertical_clearance = {(spec.tile_x, tile_y) for tile_y in range(max(0, spec.tile_y - 3), spec.tile_y + 1)}
        if vertical_clearance & (set(stage.solids) | set(stage.hazards)):
            raise ValueError("checkpoint positions must retain four-player vertical clearance")
        if support in stage.hazards or (support not in stage.solids and support not in stage.one_way_tiles):
            raise ValueError("checkpoint positions must have authored safe support")
        expected_x = float(spec.tile_x * stage.tile_size)
        expected_y = float(spec.tile_y * stage.tile_size)
        if (
            checkpoint.x != expected_x
            or checkpoint.y != expected_y
            or transform.x != expected_x
            or transform.y != expected_y
        ):
            raise ValueError("checkpoint entity positions must match authored tile geometry")
        if (
            type(collider.width) is not int
            or type(collider.height) is not int
            or collider.width != stage.tile_size
            or collider.height != stage.tile_size
            or type(collider.solid) is not bool
            or collider.solid
        ):
            raise ValueError("checkpoint colliders must use one non-solid authored tile")
        if type(checkpoint.active) is not bool:
            raise TypeError("Checkpoint.active must be a boolean")
        if checkpoint.active:
            active_rows.append(row)

    active_id = world.resources.get("active_checkpoint_id")
    if type(active_id) is not str or not active_id:
        raise TypeError("active_checkpoint_id must be a non-empty checkpoint ID")
    if len(active_rows) != 1 or active_rows[0][1].checkpoint_id != active_id:
        raise ValueError("exactly one checkpoint must match active_checkpoint_id")
    return tuple(rows)


def build_stage_result(world: World, stage: StageSpec, clear_time_ms: int) -> StageResult:
    """Build one catalog-bound result from validated gameplay-owned facts."""

    if type(clear_time_ms) is not int or clear_time_ms <= 0:
        raise ValueError("clear_time_ms must be a positive integer")
    raw_players = world.resources.get("active_players")
    if type(raw_players) is not tuple or any(type(player) is not ActivePlayer for player in raw_players):
        raise TypeError("active_players must be a tuple of ActivePlayer values")
    players = cast(tuple[ActivePlayer, ...], raw_players)
    active_slots = tuple(player.slot for player in players)
    if not active_slots:
        raise ValueError("a completed stage must retain at least one active player")
    if active_slots != tuple(sorted(active_slots)) or len(active_slots) != len(set(active_slots)):
        raise ValueError("active player slots must be unique and sorted")

    component_slots = tuple(slot.slot for _, slot in world.query(PlayerSlot) if slot.slot in active_slots)
    if component_slots != active_slots:
        raise ValueError("active player slots must exactly match player entities")
    deaths = validate_deaths_by_slot(world.resources.get("deaths_by_slot"), active_slots)
    collected = validate_result_ids(
        world.resources.get("collected_mote_ids"),
        "collected_mote_ids",
        {mote.mote_id for mote in stage.motes},
        stage.stage_id,
    )
    run_motes = world.resources.get("run_energy_spheres")
    if type(run_motes) is not int or run_motes != len(collected):
        raise ValueError("run_energy_spheres must exactly count collected stable mote IDs")

    discovered = validate_result_ids(
        world.resources.get("discovered_ability_ids"),
        "discovered_ability_ids",
        {enemy.ability_id for enemy in stage.enemy_spawns if enemy.ability_id is not None},
        stage.stage_id,
    )
    return StageResult(
        stage_id=stage.stage_id,
        world_id=stage.world_id,
        node_id=stage.node_id,
        clear_time_ms=clear_time_ms,
        collected_mote_ids=collected,
        discovered_ability_ids=discovered,
        active_slots=active_slots,
        deaths_by_slot=deaths,
    )


def validate_result_ids(
    value: object,
    field: str,
    allowed_ids: set[str],
    stage_id: str,
) -> tuple[str, ...]:
    """Return sorted unique IDs after binding them to one authored stage."""

    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Collection):
        raise TypeError(f"{field} must be a collection of strings")
    raw = tuple(cast(Collection[object], value))
    if any(type(item) is not str for item in raw):
        raise TypeError(f"{field} must be a collection of strings")
    if any(not item for item in cast(tuple[str, ...], raw)):
        raise ValueError(f"{field} must contain non-empty string IDs")
    if len(raw) != len(set(raw)):
        raise ValueError(f"{field} must not contain duplicate IDs")
    canonical = tuple(sorted(cast(tuple[str, ...], raw)))
    unknown = tuple(item for item in canonical if item not in allowed_ids)
    if unknown:
        category = "collected mote IDs" if field == "collected_mote_ids" else "discovered ability IDs"
        raise ValueError(f"{category} are not authored for {stage_id}: {unknown}")
    return canonical


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
    "build_stage_result",
    "validate_attack_request",
    "validate_attack_requests",
    "validate_checkpoint_state",
    "validate_damage_queue",
    "validate_deaths_by_slot",
    "validate_pending_enemy_launches",
    "validate_result_ids",
]
