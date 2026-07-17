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
    draw_started: bool = False
    draw_released: bool = False
    ability_pressed: bool = False
    ability_held: bool = False
    ability_released: bool = False
    ability_consumed: bool = False
    guard_held: bool = False
    dodge_pressed: bool = False
    drop_pressed: bool = False
    gather_confirmed: bool = False


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
class CaptureState:
    phase: str = "idle"
    draw_elapsed_ms: int = 0
    captured_entity_id: int | None = None
    captured_ability_id: str | None = None
    captured_visual_id: str | None = None


@dataclass
class CapturedBy:
    player_entity_id: int


@dataclass
class AbilityState:
    current_id: str = "none"
    previous_id: str = "none"
    cooldown_remaining_ms: int = 0
    charge_ms: int = 0
    combo_step: int = 0
    combo_window_remaining_ms: int = 0
    meter: int = 0
    armor_remaining_ms: int = 0


@dataclass(frozen=True, slots=True)
class AttackRequest:
    owner_entity_id: int
    team: str
    ability_id: str
    attack_kind: str
    visual_id: str
    x: float
    y: float
    width: int
    height: int
    vx: float
    vy: float
    damage: int
    knockback_x: float
    knockback_y: float
    ttl_ms: int
    pierce: int = 0
    cuts_projectiles: bool = False
    guard_break: bool = False
    pull_strength: float = 0.0
    interaction_kind: str | None = None


@dataclass
class Attack:
    owner_entity_id: int
    team: str
    attack_kind: str
    visual_id: str
    damage: int
    knockback_x: float
    knockback_y: float
    ttl_ms: int
    pierce_remaining: int
    cuts_projectiles: bool
    guard_break: bool
    pull_strength: float
    interaction_kind: str | None
    born_frame: int
    last_advanced_frame: int = -1
    hit_entity_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class PendingEnemyLaunch:
    """Pair one queued launch request with its destroyed source enemy."""

    player_id: int
    enemy_id: int


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
    stable_id: str | None = None


@dataclass
class EchoPickup:
    ability_id: str


@dataclass
class Interaction:
    interaction_id: str
    kind: str
    state: str = "idle"


@dataclass
class Checkpoint:
    """Hashed team checkpoint identity, safe position, and activation state."""

    checkpoint_id: str
    x: float
    y: float
    active: bool = False


@dataclass
class StageGoal:
    node_id: str
    world_id: str
    stage_id: str


@dataclass
class GatherState:
    """Hashed team-gather countdown and its current goal participation."""

    leader_slot: int | None = None
    leader_confirmed: bool = False
    countdown_remaining_ms: int = 0
    at_goal_slots: tuple[int, ...] = ()

    def cancel(self) -> int | None:
        """Reset an active countdown and return its prior leader slot."""

        leader_slot = self.leader_slot
        self.leader_slot = None
        self.leader_confirmed = False
        self.countdown_remaining_ms = 0
        return leader_slot


@dataclass
class Respawn:
    x: float
    y: float
    timer_ms: int = 0
    started_frame: int = -1


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
    attack_id: int | None = None


NON_ENTITY_DAMAGE_SOURCE_ID = 0


@dataclass
class DamageQueue:
    pending: list[DamageRecord] = field(default_factory=list)
