from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Transform:
    x: float
    y: float


@dataclass
class Velocity:
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class Facing:
    direction: int = 1


@dataclass
class Collider:
    width: int
    height: int
    on_ground: bool = False
    solid: bool = True


@dataclass
class Health:
    current: int
    maximum: int
    invulnerable_ms: int = 0
    dead: bool = False


@dataclass
class Team:
    name: str


@dataclass
class PlayerSlot:
    """Hashed gameplay ownership, leader authority, and remaining team lives."""

    slot: int
    is_human: bool = True
    lives: int = 3
    is_leader: bool = False


@dataclass
class ActorState:
    name: str = "Idle"
    timer_ms: int = 0


@dataclass
class ControlIntent:
    move_axis: int = 0
    jump_pressed: bool = False
    hover_held: bool = False
    draw_pressed: bool = False
    draw_released: bool = False
    ability_pressed: bool = False
    guard_held: bool = False
    dodge_pressed: bool = False
    drop_pressed: bool = False


@dataclass
class MovementState:
    """Own the deterministic player movement windows."""

    coyote_remaining_ms: int = 0
    jump_buffer_remaining_ms: int = 0
    hover_remaining_ms: int = 850
    hover_ready: bool = True


@dataclass
class DefenseState:
    """Own active guard and dodge timing."""

    guarding: bool = False
    dodge_remaining_ms: int = 0
    dodge_cooldown_ms: int = 0
    dodge_direction: int = 1


@dataclass
class DrawState:
    active: bool = False
    active_ms: int = 0
    captured_entity: int | None = None
    captured_echo: str | None = None


@dataclass
class AbilityState:
    current: str = "none"
    previous: str = "none"
    cooldown_ms: int = 0
    is_super: bool = False


@dataclass
class EnemyAI:
    kind: str
    patrol_left: float
    patrol_right: float
    aggro_range: float = 180.0
    facing: int = -1


@dataclass
class EnemyDropAbility:
    ability: str


@dataclass
class Projectile:
    owner: int
    tag: str
    damage: int
    ttl_ms: int


@dataclass
class Collectible:
    kind: str
    value: int = 1
    collected: bool = False


@dataclass
class StageGoal:
    node_id: str
    world_id: str
    stage_id: str


@dataclass
class Respawn:
    x: float
    y: float
    timer_ms: int = 0


@dataclass
class CameraFocus:
    weight: float = 1.0
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class DamageRecord:
    """Carry one complete deterministic hit across the queue boundary."""

    source_id: int
    target_id: int
    amount: int
    knockback_x: float
    knockback_y: float
    guard_break: bool


NON_ENTITY_DAMAGE_SOURCE_ID = 0


@dataclass
class DamageQueue:
    pending: list[DamageRecord] = field(default_factory=list)
