"""Immutable gameplay state exposed to rendering and progression layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from windsprig.content.models import Vulnerability
from windsprig.core.ecs import FrameSnapshot
from windsprig.core.events import GameEvent


class StageOutcome(StrEnum):
    """Simulation-owned terminal state for a stage."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PlayerView:
    """Presentation-safe state for one active player."""

    entity_id: int
    slot: int
    x: float
    y: float
    width: int
    height: int
    facing: int
    actor_state: str
    hp: int
    maximum_hp: int
    lives_remaining: int
    ability_id: str
    ability_meter: int
    ability_charge_ms: int
    guard_active: bool
    dodge_active: bool
    invulnerable: bool
    hover_remaining_ms: int
    hover_max_ms: int
    captured_ability_id: str | None
    captured_visual_id: str | None


@dataclass(frozen=True, slots=True)
class EnemyView:
    """Presentation-safe state for one enemy."""

    entity_id: int
    enemy_kind: str
    x: float
    y: float
    width: int
    height: int
    facing: int
    actor_state: str
    hp: int
    maximum_hp: int
    ability_id: str | None
    captured_by: int | None


@dataclass(frozen=True, slots=True)
class AttackView:
    """Presentation-safe state for a live attack volume."""

    entity_id: int
    owner_entity_id: int
    attack_kind: str
    visual_id: str
    x: float
    y: float
    width: int
    height: int
    facing: int
    ttl_ms: int


@dataclass(frozen=True, slots=True)
class EchoPickupView:
    """Presentation-safe state for a recoverable ability echo."""

    entity_id: int
    ability_id: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class InteractionView:
    """Presentation-safe state for one authored world interaction."""

    entity_id: int
    interaction_id: str
    interaction_kind: str
    interaction_state: str
    x: float
    y: float
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class BossView:
    """Presentation-safe state for one authored boss encounter."""

    entity_id: int
    boss_id: str
    phase_id: str
    x: float
    y: float
    width: int
    height: int
    facing: int
    actor_state: str
    hp: int
    maximum_hp: int
    telegraph_id: str | None
    telegraph_remaining_ms: int
    vulnerability_state: Vulnerability


@dataclass(frozen=True, slots=True)
class CheckpointView:
    """Presentation-safe checkpoint position and activation state."""

    checkpoint_id: str
    x: float
    y: float
    is_active: bool


@dataclass(frozen=True, slots=True)
class GoalGatherView:
    """Team readiness and leader-confirmed goal countdown state."""

    goal_x: float
    goal_y: float
    at_goal_slots: tuple[int, ...]
    required_slots: tuple[int, ...]
    leader_slot: int | None
    leader_confirmed: bool
    countdown_remaining_ms: int


@dataclass(frozen=True, slots=True)
class CameraTargetView:
    """Read-only camera target emitted for an eligible active player."""

    entity_id: int
    slot: int
    x: float
    y: float
    weight: float
    enabled: bool


@dataclass(frozen=True, slots=True)
class StageSnapshot:
    """Complete render-facing state for one deterministic simulation frame."""

    frame_index: int
    elapsed_ms: int
    stage_id: str
    world_id: str
    node_id: str
    outcome: StageOutcome
    players: tuple[PlayerView, ...]
    enemies: tuple[EnemyView, ...]
    attacks: tuple[AttackView, ...]
    echo_pickups: tuple[EchoPickupView, ...]
    interactions: tuple[InteractionView, ...]
    checkpoints: tuple[CheckpointView, ...]
    goal_gather: GoalGatherView
    camera_targets: tuple[CameraTargetView, ...]
    bosses: tuple[BossView, ...]
    collected_mote_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageResult:
    """Frozen completion facts consumed by progression and results screens."""

    stage_id: str
    world_id: str
    node_id: str
    clear_time_ms: int
    collected_mote_ids: tuple[str, ...]
    discovered_ability_ids: tuple[str, ...]
    active_slots: tuple[int, ...]
    deaths_by_slot: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class StageFrame:
    """Atomic simulation, view, event, and optional result boundary."""

    simulation: FrameSnapshot
    view: StageSnapshot
    events: tuple[GameEvent, ...]
    result: StageResult | None
