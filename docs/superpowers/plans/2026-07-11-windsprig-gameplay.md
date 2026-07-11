# Windsprig Production Gameplay Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the complete deterministic production gameplay loop on the single ECS runtime, from active-player spawn through movement, defense, capture choices, six distinct abilities, combat, checkpoints, co-op recovery, victory/defeat, results, and replay evidence.

**Architecture:** `GameSession` owns explicit stage-flow state while `StageRuntime` owns one fixed-step ECS `World`; screens pass device-agnostic `InputFrame` values in and receive immutable `StageFrame`/`StageSnapshot` values plus semantic `GameEvent` values out. Focused systems mutate deterministic ECS components in a fixed order, ability strategies produce typed attack requests, and presentation remains a read-only subscriber with no gameplay authority.

**Tech Stack:** Python 3.12+, dataclasses and `StrEnum`, pygame-ce collision primitives, the existing deterministic ECS/EventBus/RNG foundation, pytest, Hypothesis, coverage.py, and JSON replay fixtures.

## Global Constraints

- The active public package is `windsprig`; do not retain `kirby_clone` as a compatibility package, import target, executable name, window title, test namespace, or release artifact string.
- Public names are *Windsprig: Echoes of the Gale*, Sprig, draw, capture, release, launch, harmonize, Wind Mote, Bloomblade, Cinder, Voltsong, Galehook, Stoneheart, and Tempest. Do not add Nintendo, Kirby, Return to Dream Land, or Nintendo character/asset/copy identifiers.
- Use one production ECS runtime. Absorb tested behavior from `windsprig/simulation.py`, `windsprig/player.py`, `windsprig/enemies.py`, `windsprig/entities.py`, and `windsprig/combat.py`, then delete those competing runtime modules in Task 11.
- Run simulation at the exact fixed step `16 ms`; render cadence never changes gameplay results.
- `GameConfig.coyote_time_ms` remains exactly `100`; `GameConfig.jump_buffer_ms` remains exactly `120`.
- Support one to four local active players. Only joined `ActivePlayer` slots receive an entity, HUD/view entry, camera target, lives, enemy targeting weight, or goal participation.
- Render-facing state is immutable. Screens, effects, audio, camera, and render code consume `StageSnapshot` and `GameEvent`; they do not query or mutate `World`.
- Queue discrete input until one fixed step consumes it. Only Move, Hover, and Guard held state may repeat on later fixed steps.
- A projectile or attack volume advances at most once in a simulation frame; `last_advanced_frame` is part of deterministic component state and duplicate advancement is an assertion failure in developer/test runs.
- Runtime hashes include gameplay components/resources only and exclude render interpolation, surfaces, particles, audio channels, screen shake, afterimages, and other presentation-only state.
- Release, launch, harmonize, damage, guard, dodge, capture, ability equip/drop/use, projectile cut, mote collection, checkpoint, respawn, gather, defeat, and victory publish semantic events. Presentation subscribers never alter deterministic state in response.
- The public ability IDs are exactly `bloomblade`, `cinder`, `voltsong`, `galehook`, `stoneheart`, and `tempest`; `none` is the only empty sentinel.
- Tempest costs a full `100` meter, immediately restores the previously equipped non-super ability after use, and cannot be a permanent dominant loadout.
- Stage completion freezes simulation, returns a `StageResult`, and waits for an explicit results choice. Defeat freezes simulation and waits for checkpoint retry, stage retry, or world-map choice.
- No inactive or dead player can trigger a goal. In co-op, all eligible active players must reach the goal, or the roster leader must explicitly start the `3000 ms` gather countdown.
- Production modules target at least `85%` branch coverage overall, but every gameplay invariant in this plan also has a named unit, integration, or replay test.
- This plan does not author the final 30-stage layouts, boss phases, presentation assets, audio, screen layouts, progression math, or saves; it provides the exact gameplay/content/view contracts those downstream tasks consume.

---

## Prerequisite and execution boundary

Execute the release-foundation plan first. Before Task 1, this repository must import exclusively from `windsprig`, and the following foundation signatures must exist unchanged:

```python
# windsprig/core/ecs.py
@dataclass(frozen=True)
class FrameSnapshot:
    frame_index: int
    rng_state_hash: str
    world_state_hash: str
    event_count: int

class World:
    def step(self, dt_ms: int, input_frame: object) -> FrameSnapshot: ...

# windsprig/core/events.py
@dataclass(frozen=True)
class GameEvent:
    topic: str
    payload: dict[str, object]

class EventBus:
    def subscribe(self, topic: str, callback: Callable[[GameEvent], None]) -> None: ...
    def publish(self, topic: str, payload: dict[str, object] | None = None) -> None: ...
    def drain(self) -> list[GameEvent]: ...
    def peek(self) -> list[GameEvent]: ...

# windsprig/core/rng.py
def derive_stage_seed(base_seed: int, stage_id: str) -> int: ...

# windsprig/input/roster.py
@dataclass(frozen=True)
class DeviceRef:
    kind: Literal["keyboard", "gamepad"]
    uid: str
    label: str

@dataclass(frozen=True)
class ActivePlayer:
    slot: int
    device: DeviceRef
    color_token: str
    icon_token: str
    is_leader: bool

class ActiveRoster:
    @property
    def players(self) -> tuple[ActivePlayer, ...]: ...
    def is_active(self, slot: int) -> bool: ...
    @property
    def leader_slot(self) -> int | None: ...

# windsprig/input/commands.py
@dataclass
class InputFrame:
    commands_by_slot: dict[int, list[InputCommand]]
    def add(self, command: InputCommand) -> None: ...
    def commands_for(self, player_slot: int) -> list[InputCommand]: ...
    def continuous_only(self) -> "InputFrame": ...
    @staticmethod
    def empty() -> "InputFrame": ...
```

The canonical command classes are `MoveCommand`, `JumpCommand`, `HoverCommand`, `DrawStartCommand`, `DrawReleaseCommand`, `AbilityUseCommand`, `GuardCommand`, `DodgeCommand`, and `DropAbilityCommand`. Task 6 extends `AbilityUseCommand` with held/released state without renaming it; Task 10 adds `GatherConfirmCommand`.

## Exact file map

### Create

- `windsprig/gameplay/events.py` — gameplay topic enum, exact payload constructors, and event validation used by systems and presentation subscribers.
- `windsprig/gameplay/snapshot.py` — immutable runtime/result/view DTOs and the only supported render-facing gameplay boundary.
- `windsprig/gameplay/session.py` — explicit intro/playing/paused/victory/defeat/results/closed state machine.
- `windsprig/gameplay/systems/defense_system.py` — guard and dodge timers, direction, movement restriction, and invulnerability.
- `windsprig/gameplay/systems/capture_system.py` — draw, capture, release, launch, harmonize, and capture ownership.
- `windsprig/gameplay/systems/attack_spawn_system.py` — consumes typed ability/capture attack requests and creates visible ECS entities.
- `windsprig/gameplay/systems/attack_motion_system.py` — the sole owner of attack movement and TTL advancement.
- `windsprig/gameplay/systems/interaction_system.py` — conductor chains, Galehook switches, and Stoneheart breakable floors.
- `windsprig/gameplay/systems/checkpoint_system.py` — stable checkpoint activation and team respawn position.
- `windsprig/gameplay/abilities/bloomblade.py`, `cinder.py`, `voltsong.py`, `galehook.py`, `stoneheart.py`, `tempest.py` — one strategy per mechanically distinct family.
- `windsprig/gameplay/replay.py` — typed production-ECS replay schema, loader, command codec, and hash runner.
- `tests/helpers/gameplay.py` — deterministic stage/player/runtime builders used by every gameplay test.
- `tests/unit/gameplay/test_content_contracts.py`
- `tests/unit/gameplay/test_runtime_roster.py`
- `tests/unit/gameplay/test_session.py`
- `tests/unit/gameplay/test_movement.py`
- `tests/unit/gameplay/test_defense.py`
- `tests/unit/gameplay/test_capture.py`
- `tests/unit/gameplay/test_bloomblade_cinder.py`
- `tests/unit/gameplay/test_voltsong_galehook.py`
- `tests/unit/gameplay/test_stoneheart_tempest.py`
- `tests/unit/gameplay/test_attack_pipeline.py`
- `tests/unit/gameplay/test_checkpoints_outcomes.py`
- `tests/unit/gameplay/test_coop_goal.py`
- `tests/integration/test_gameplay_action_flow.py`
- `tests/integration/test_gameplay_session_flow.py`
- `tests/integration/test_gameplay_replay.py`
- `tests/fixtures/replays/production_flow_v1.json`
- `tests/architecture/test_single_gameplay_runtime.py`

### Modify

- `windsprig/config.py` — add finite-hover, guard, dodge, capture, gather, and respawn tuning values listed in Task 1.
- `windsprig/content/loader.py` — expose stable motes, checkpoints, and gameplay interactions while deterministically adapting the current catalog.
- `windsprig/content/abilities.json` — replace generic legacy ability rows with the six public IDs and their strategy configuration.
- `windsprig/input/commands.py` — preserve foundation command names; add ability button phases and leader gather confirmation.
- `windsprig/input/devices.py` — emit the new held/released ability phases and gather-confirm edge.
- `windsprig/gameplay/components/core.py` and `windsprig/gameplay/components/__init__.py` — replace prototype inhale/generic projectile state with the exact components below.
- `windsprig/gameplay/factory.py` — spawn only requested active players plus stable checkpoints, motes, interactions, dropped echoes, and typed attacks.
- `windsprig/gameplay/runtime.py` — construct the only ECS scheduler, synchronize pause-lobby roster changes, collect events, freeze outcomes, and return `StageFrame`.
- `windsprig/gameplay/state_machine.py` — use typed actor states and legal transitions for hover, draw/hold, guard, dodge, hurt, defeated, and victory.
- `windsprig/gameplay/abilities/base.py`, `registry.py`, and `__init__.py` — replace generic `DataDrivenAbilityStrategy` with typed, behavior-specific strategies.
- `windsprig/gameplay/systems/input_command_system.py` — translate canonical commands into deterministic intent and ignore inactive slots.
- `windsprig/gameplay/systems/movement_system.py` — acceleration, deceleration, facing, 100 ms coyote, 120 ms buffer, finite hover, and guard speed.
- `windsprig/gameplay/systems/collision_system.py` — move actor bodies only, record landing/hazard facts, and never move attacks.
- `windsprig/gameplay/systems/ability_system.py` — ability charge, combo/meter state, and typed attack requests.
- `windsprig/gameplay/systems/combat_system.py` — overlap resolution, projectile cutting, chain/zone/boomerang semantics, and exactly-once hit IDs.
- `windsprig/gameplay/systems/damage_system.py` — directional guard reduction, dodge/invulnerability rejection, death, knockback, and events.
- `windsprig/gameplay/systems/pickup_system.py` — stable mote IDs and recoverable echo pickups.
- `windsprig/gameplay/systems/coop_respawn_system.py` — active-team recovery at checkpoints or a living teammate.
- `windsprig/gameplay/systems/stage_goal_system.py` — all-player goal and leader-confirmed gather rules.
- `windsprig/gameplay/systems/camera_system.py` — emit active/alive camera targets only; smoothing remains presentation-owned.
- `windsprig/gameplay/systems/hud_system.py` — remove mutable HUD dictionaries; `StageSnapshot` replaces them.
- `windsprig/gameplay/systems/__init__.py` — export and order the new systems.
- `tools/replay_runner.py` — run `windsprig.gameplay.replay.ReplayRunner`, not the deleted simulation.
- `pyproject.toml` — ensure coverage source is `windsprig` and include the gameplay branch-coverage gate.

### Delete only in Task 11, after replacement tests pass

- `windsprig/simulation.py`
- `windsprig/player.py`
- `windsprig/enemies.py`
- `windsprig/entities.py`
- `windsprig/combat.py`
- `tests/unit/test_player.py`
- `tests/unit/test_enemy.py`
- `tests/unit/test_combat.py`
- `tests/unit/test_determinism.py`
- `tests/integration/test_game_flow.py`
- `tests/integration/test_replay_runner.py`
- `tests/integration/replay_sample.json`

## Stable downstream interfaces

Define these values in `windsprig/gameplay/snapshot.py` exactly. Presentation, audio/effects, camera, completion, and save work may consume these names and fields without importing ECS components:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from windsprig.core.ecs import FrameSnapshot
from windsprig.core.events import GameEvent


class StageOutcome(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PlayerView:
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
    entity_id: int
    ability_id: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class InteractionView:
    entity_id: int
    interaction_id: str
    interaction_kind: str
    interaction_state: str
    x: float
    y: float
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class CheckpointView:
    checkpoint_id: str
    x: float
    y: float
    is_active: bool


@dataclass(frozen=True, slots=True)
class GoalGatherView:
    goal_x: float
    goal_y: float
    at_goal_slots: tuple[int, ...]
    required_slots: tuple[int, ...]
    leader_slot: int | None
    leader_confirmed: bool
    countdown_remaining_ms: int


@dataclass(frozen=True, slots=True)
class CameraTargetView:
    entity_id: int
    slot: int
    x: float
    y: float
    weight: float
    enabled: bool


@dataclass(frozen=True, slots=True)
class StageSnapshot:
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
    collected_mote_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageResult:
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
    simulation: FrameSnapshot
    view: StageSnapshot
    events: tuple[GameEvent, ...]
    result: StageResult | None
```

`windsprig/gameplay/runtime.py` produces this public API:

```python
class StageRuntime:
    def __init__(
        self,
        config: GameConfig,
        stage: StageSpec,
        ability_registry: AbilityRegistry,
        active_players: Sequence[ActivePlayer],
        seed: int,
    ) -> None: ...

    def step(self, input_frame: InputFrame) -> StageFrame: ...
    def sync_active_players(self, active_players: Sequence[ActivePlayer]) -> tuple[GameEvent, ...]: ...
    def retry_from_checkpoint(self) -> StageSnapshot: ...
    def reset_stage(self) -> StageSnapshot: ...
    def snapshot(self) -> StageSnapshot: ...

    @property
    def result(self) -> StageResult | None: ...
```

`windsprig/content/loader.py` owns these additions. The loader accepts the current JSON `energy_spheres`/`copy_ability` keys only as a deterministic migration input; `StageSpec` exposes only the new names:

```python
AbilityId = Literal["bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest"]
InteractionKind = Literal["conductor", "switch", "breakable_floor"]

@dataclass(frozen=True, slots=True)
class MoteSpec:
    mote_id: str
    tile_x: int
    tile_y: int

@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    checkpoint_id: str
    tile_x: int
    tile_y: int

@dataclass(frozen=True, slots=True)
class InteractionSpec:
    interaction_id: str
    kind: InteractionKind
    tile_x: int
    tile_y: int
    width_tiles: int = 1
    height_tiles: int = 1

@dataclass(frozen=True, slots=True)
class EnemySpawn:
    x: float
    y: float
    kind: str
    ability_id: AbilityId | None
    patrol_left: float
    patrol_right: float

@dataclass(frozen=True, slots=True)
class StageSpec:
    stage_id: str
    world_id: str
    node_id: str
    width_tiles: int
    height_tiles: int
    tile_size: int
    ground_y_tile: int
    player_spawns: tuple[tuple[float, float], ...]
    enemy_spawns: tuple[EnemySpawn, ...]
    motes: tuple[MoteSpec, ...]
    checkpoints: tuple[CheckpointSpec, ...]
    interactions: tuple[InteractionSpec, ...]
    goal_tile: tuple[int, int]
    hazards: tuple[tuple[int, int], ...]
    one_way_tiles: tuple[tuple[int, int], ...]
    solids: tuple[tuple[int, int], ...]
```

Gameplay events remain foundation `GameEvent` values. Use the following exact topics and payload keys; every payload includes `frame_index: int` and all entity collections are sorted by entity ID or slot before publication:

| Topic | Additional payload keys and exact value types |
|---|---|
| `PlayerJoined` | `entity_id: int`, `slot: int` |
| `PlayerLeft` | `entity_id: int`, `slot: int` |
| `PlayerDamaged` | `target_id: int`, `slot: int`, `source_id: int`, `amount: int`, `guarded: bool`, `knockback_x: float`, `knockback_y: float` |
| `PlayerDodged` | `entity_id: int`, `slot: int`, `direction: int` |
| `EnemyCaptured` | `player_id: int`, `enemy_id: int`, `ability_id: str | None`, `visual_id: str` |
| `CaptureReleased` | `player_id: int`, `outcome: Literal["empty"]` |
| `EnemyLaunched` | `player_id: int`, `enemy_id: int`, `attack_id: int` |
| `HarmonizeUnavailable` | `player_id: int`, `enemy_id: int` |
| `AbilityEquipped` | `player_id: int`, `ability_id: str`, `source: Literal["capture", "echo_pickup"]` |
| `AbilityDropped` | `player_id: int`, `ability_id: str`, `pickup_id: int` |
| `AbilityUsed` | `player_id: int`, `ability_id: str`, `attack_ids: tuple[int, ...]` |
| `AttackSpawned` | `attack_id: int`, `owner_id: int`, `attack_kind: str`, `visual_id: str` |
| `AttackHit` | `attack_id: int`, `owner_id: int`, `target_id: int`, `damage: int`, `guarded: bool` |
| `ProjectileCut` | `cutter_attack_id: int`, `projectile_attack_id: int` |
| `EnemyDefeated` | `enemy_id: int`, `source_id: int` |
| `MoteCollected` | `mote_id: str`, `player_id: int`, `slot: int` |
| `CheckpointReached` | `checkpoint_id: str`, `player_id: int`, `slot: int` |
| `PlayerDefeated` | `entity_id: int`, `slot: int`, `lives_remaining: int` |
| `PlayerRespawned` | `entity_id: int`, `slot: int`, `checkpoint_id: str`, `cost: int` |
| `GatherStarted` | `leader_slot: int`, `countdown_ms: int`, `waiting_slots: tuple[int, ...]` |
| `GatherCancelled` | `leader_slot: int`, `reason: Literal["leader_left_goal", "leader_defeated", "roster_changed"]` |
| `GatherCompleted` | `leader_slot: int`, `gathered_slots: tuple[int, ...]` |
| `StageCompleted` | `stage_id: str`, `node_id: str`, `clear_time_ms: int`, `collected_mote_ids: tuple[str, ...]` |
| `StageFailed` | `stage_id: str`, `node_id: str`, `active_slots: tuple[int, ...]` |

## ECS component and system-order contract

Keep gameplay component state as dataclasses in `windsprig/gameplay/components/core.py`. The final fields used across tasks are:

```python
@dataclass
class MovementState:
    coyote_remaining_ms: int = 0
    jump_buffer_remaining_ms: int = 0
    hover_remaining_ms: int = 850
    hover_ready: bool = True

@dataclass
class DefenseState:
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

@dataclass(frozen=True)
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

@dataclass
class EchoPickup:
    ability_id: str

@dataclass
class Checkpoint:
    checkpoint_id: str
    x: float
    y: float
    active: bool = False

@dataclass
class Interaction:
    interaction_id: str
    kind: str
    state: str = "idle"

@dataclass
class GatherState:
    leader_slot: int | None = None
    leader_confirmed: bool = False
    countdown_remaining_ms: int = 0
    at_goal_slots: tuple[int, ...] = ()
```

Install systems in this exact scheduler order in `StageRuntime`; tests assert the class-name tuple so later work cannot accidentally double-move attacks or resolve damage before defense:

```python
SYSTEM_ORDER = (
    InputCommandSystem,
    DefenseSystem,
    MovementSystem,
    EnemyAISystem,
    CollisionSystem,
    CaptureSystem,
    AbilitySystem,
    AttackSpawnSystem,
    AttackMotionSystem,
    CombatSystem,
    DamageSystem,
    InteractionSystem,
    PickupSystem,
    CheckpointSystem,
    CoopRespawnSystem,
    StageGoalSystem,
    CameraSystem,
)
```

Every later task may modify `tests/helpers/gameplay.py`; helpers are test-only and never imported by `windsprig`. Use these exact contracts so the test snippets below are self-contained:

| Helper | Exact deterministic behavior |
|---|---|
| `frame(slot: int, *commands: InputCommand) -> InputFrame` | returns one `commands_by_slot` entry for `slot` in argument order |
| `make_active_player(slot: int, leader: bool = False) -> ActivePlayer` | keyboard device `test-kb-{slot}`, tokens `player-{slot}` / `sprig-{slot}` |
| `make_runtime(players=(P1,), stage=make_stage()) -> StageRuntime` | fresh config/registry, seed `77`, plus a test-only wildcard event recorder |
| `make_session() -> GameSession` | wraps `make_runtime` in `INTRO` |
| `enter_victory(session: GameSession) -> None` | places the live P1 on the goal and calls one normal session step |
| `grounded_runtime() -> tuple[StageRuntime, int]` | P1 at `(64, 160)`, flat ground, `Collider.on_ground=True` |
| `falling_runtime(bottom_gap_px: int) -> tuple[StageRuntime, int]` | P1 descending at `vy=160` with the requested gap above flat ground |
| `defense_runtime() -> tuple[StageRuntime, int, int, int]` | P1 at x=100 facing right, enemy IDs at x=140 (front) and x=60 (back) |
| `hold_guard(runtime, slot) -> StageFrame` | steps one held `GuardCommand` |
| `queue_damage(runtime, source, target, amount, knockback_x=0.0) -> None` | appends the complete Task 4 damage dict with `guard_break=False` |
| `player_health(runtime, entity_id) -> int` | reads `Health.current` |
| `clear_invulnerability(runtime, entity_id) -> None` | sets only `Health.invulnerable_ms=0` |
| `last_event(runtime, topic) -> GameEvent` / `last_published_topic(runtime) -> str` | reads the test-only wildcard recorder and fails if absent |
| `capture_runtime(enemy_ability, enemy_offset) -> tuple` | returns runtime/P1 and, when offset is not `None`, a capturable enemy at P1 x + offset |
| `equipped_runtime(ability_id) -> tuple[StageRuntime, int]` | `make_runtime` with P1 `AbilityState.current_id` set |
| `event_topics(frame) -> tuple[str, ...]`, `last_topic(frame) -> str`, `count_topic(frame, topic) -> int` | pure `StageFrame.events` queries |
| `move_player_onto(runtime, entity_id, x, y) -> None` | changes only `Transform.x/y` and zeroes velocity |
| `context(ability, on_ground=True, charge_ms=0, combo_step=0, meter=0) -> AbilityContext` | actor 1, frame 0, position `(100,100)`, facing right |
| `component_velocity_x(runtime, entity_id) -> float`, `entity_x(runtime, entity_id) -> float`, `entity_health(runtime, entity_id) -> int` | direct typed component reads |
| `overlapping_attack_runtime() -> tuple[StageRuntime, int, int]` | one stationary player attack overlapping one enemy for at least two steps |
| `projectile_cut_runtime() -> tuple[StageRuntime, int, int]` | Bloomblade P1 and one overlapping hostile projectile |
| `checkpoint_runtime() -> tuple[StageRuntime, int, int]` | stage with start checkpoint and one later checkpoint; returns later checkpoint entity |
| `move_player_onto_checkpoint`, `checkpoint_position`, `goal_runtime`, `move_player_to_goal` | typed wrappers around transforms from the helper stage |
| `defeat_player(runtime, entity_id) -> StageFrame` | queues lethal damage from a real enemy and performs one normal step |
| `coop_runtime() -> tuple[StageRuntime, int, int]` | P1 leader and P2 active on a flat stage with one goal |
| `player_view(runtime, slot) -> PlayerView` | finds exactly one slot in `runtime.snapshot().players` |
| `step_until(runtime, predicate: Callable[[], bool], max_steps: int) -> None` | steps empty input until true, else fails after `max_steps` |
| `step_count(runtime, count: int) -> None` | performs exactly `count` empty fixed steps |
| `move_player_away_from_goal(runtime, entity_id) -> None` | places entity at stage start with zero velocity |
| `test_catalog()` / `test_registry()` | real production catalog/registry loaders rooted at `windsprig/content` |

Subproject 3 is explicitly allowed to append `boss_id: str | None = None` to `StageSpec`, add `BossView` plus `StageSnapshot.bosses`, and add boss-specific semantic topics. It must not rename or remove the fields above.

### Task 1: Lock gameplay content, tuning, event, and snapshot contracts

**Files:**
- Modify: `windsprig/config.py`
- Modify: `windsprig/content/loader.py`
- Create: `windsprig/gameplay/events.py`
- Create: `windsprig/gameplay/snapshot.py`
- Create: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_content_contracts.py`

**Interfaces:**
- Consumes: foundation `GameConfig`, `GameEvent`, `FrameSnapshot`, `StageSpec` loader, and `ActivePlayer` signatures shown above.
- Produces: every immutable DTO, content dataclass, event topic, `make_active_player(slot: int, leader: bool = False) -> ActivePlayer`, and `make_stage(*, player_spawns: tuple[tuple[float, float], ...] = ((64.0, 160.0),), enemy_spawns: tuple[EnemySpawn, ...] = (), motes: tuple[MoteSpec, ...] = (), checkpoints: tuple[CheckpointSpec, ...] = ()) -> StageSpec`.

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/unit/gameplay/test_content_contracts.py
from pathlib import Path

from windsprig.config import GameConfig
from windsprig.content.loader import load_campaign_catalog
from windsprig.gameplay.events import GameplayTopic, make_event


def test_current_catalog_adapts_to_stable_public_gameplay_fields() -> None:
    stage = load_campaign_catalog(Path("windsprig/content")).stages["world_1_stage_1"]
    assert tuple(m.mote_id for m in stage.motes) == (
        "world_1_stage_1.mote.1",
        "world_1_stage_1.mote.2",
        "world_1_stage_1.mote.3",
    )
    assert stage.checkpoints[0].checkpoint_id == "world_1_stage_1.start"
    assert all(enemy.ability_id in {"bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest"}
               for enemy in stage.enemy_spawns if enemy.ability_id is not None)


def test_gameplay_tuning_is_explicit() -> None:
    config = GameConfig()
    assert (config.coyote_time_ms, config.jump_buffer_ms, config.hover_duration_ms) == (100, 120, 850)
    assert (config.dodge_duration_ms, config.dodge_invulnerable_ms, config.gather_countdown_ms) == (160, 128, 3000)


def test_event_factory_injects_frame_and_rejects_unknown_topics() -> None:
    event = make_event(GameplayTopic.PLAYER_DODGED, 7, entity_id=2, slot=1, direction=-1)
    assert event.topic == "PlayerDodged"
    assert event.payload == {"frame_index": 7, "entity_id": 2, "slot": 1, "direction": -1}
```

- [ ] **Step 2: Run the contract tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_content_contracts.py -q`

Expected: FAIL during collection because `windsprig.gameplay.events`, `MoteSpec`, and the new `GameConfig` fields do not exist.

- [ ] **Step 3: Add exact tuning and deterministic catalog adapters**

Add these frozen fields to `GameConfig`:

```python
hover_duration_ms: int = 850
hover_gravity_scale: float = 0.28
guard_damage_multiplier: float = 0.40
guard_knockback_multiplier: float = 0.35
guard_speed_multiplier: float = 0.40
dodge_duration_ms: int = 160
dodge_invulnerable_ms: int = 128
dodge_cooldown_ms: int = 520
dodge_speed: float = 620.0
draw_base_range_px: float = 78.0
draw_range_growth_px_per_ms: float = 0.20
draw_max_bonus_range_px: float = 80.0
respawn_delay_ms: int = 1800
respawn_invulnerable_ms: int = 1200
gather_countdown_ms: int = 3000
```

Add the content dataclasses exactly as declared above and use these loader helpers:

```python
LEGACY_ABILITY_IDS: dict[str, str] = {
    "sword": "bloomblade", "spear": "bloomblade", "fighter": "bloomblade",
    "fire": "cinder", "monster_flame": "cinder",
    "beam": "voltsong", "spark": "voltsong",
    "cutter": "galehook", "whip": "galehook", "ninja": "galehook", "parasol": "galehook",
    "ice": "stoneheart", "hammer": "stoneheart", "grand_hammer": "stoneheart",
    "ultra_sword": "tempest",
}


def _load_motes(raw: dict[str, object]) -> tuple[MoteSpec, ...]:
    stage_id = str(raw["stage_id"])
    if "motes" in raw:
        return tuple(MoteSpec(str(item["mote_id"]), int(item["tile_x"]), int(item["tile_y"]))
                     for item in raw["motes"])
    return tuple(MoteSpec(f"{stage_id}.mote.{index}", int(tile[0]), int(tile[1]))
                 for index, tile in enumerate(raw.get("energy_spheres", []), start=1))


def _load_checkpoints(raw: dict[str, object]) -> tuple[CheckpointSpec, ...]:
    if "checkpoints" in raw:
        return tuple(CheckpointSpec(str(item["checkpoint_id"]), int(item["tile_x"]), int(item["tile_y"]))
                     for item in raw["checkpoints"])
    spawn_x, spawn_y = raw["player_spawns"][0]
    tile_size = int(raw["tile_size"])
    return (CheckpointSpec(f'{raw["stage_id"]}.start', int(float(spawn_x) // tile_size),
                           int(float(spawn_y) // tile_size)),)
```

Create `GameplayTopic` with every topic in the table and implement:

```python
def make_event(topic: GameplayTopic, frame_index: int, **payload: object) -> GameEvent:
    return GameEvent(topic=topic.value, payload={"frame_index": frame_index, **payload})


def publish(world: World, topic: GameplayTopic, **payload: object) -> None:
    event = make_event(topic, world.frame_index, **payload)
    world.events.publish(event.topic, event.payload)
```

Create `snapshot.py` with the complete DTO code in “Stable downstream interfaces.” Implement both test helpers with real `DeviceRef`, `ActivePlayer`, and `StageSpec` constructors so later tests never depend on the 30-stage catalog.

- [ ] **Step 4: Run the contract tests and confirm GREEN**

Run: `uv run pytest tests/unit/gameplay/test_content_contracts.py -q`

Expected: `3 passed`; the current catalog exposes three deterministic mote IDs and one start checkpoint per stage without exposing legacy field names.

- [ ] **Step 5: Commit the contract boundary**

```bash
git add windsprig/config.py windsprig/content/loader.py windsprig/gameplay/events.py windsprig/gameplay/snapshot.py tests/helpers/gameplay.py tests/unit/gameplay/test_content_contracts.py
git commit -m "feat: define production gameplay contracts"
```

### Task 2: Spawn and synchronize only active players in the ECS runtime

**Files:**
- Modify: `windsprig/gameplay/components/core.py`
- Modify: `windsprig/gameplay/components/__init__.py`
- Modify: `windsprig/gameplay/factory.py`
- Modify: `windsprig/gameplay/runtime.py`
- Modify: `windsprig/gameplay/systems/input_command_system.py`
- Modify: `windsprig/gameplay/systems/camera_system.py`
- Modify: `windsprig/gameplay/systems/__init__.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_runtime_roster.py`

**Interfaces:**
- Consumes: `Sequence[ActivePlayer]`, `InputFrame.commands_for(slot)`, `World.step(dt_ms, input_frame) -> FrameSnapshot`, `EventBus.subscribe("*", callback)`, `StageSpec`, and Task 1 DTOs/events.
- Produces: the exact `StageRuntime` constructor, `step`, `sync_active_players`, `snapshot`, and `result` signatures above; `EntityFactory.spawn_player(player: ActivePlayer, x: float, y: float) -> int`.

- [ ] **Step 1: Write roster and scheduler-order tests**

```python
# tests/unit/gameplay/test_runtime_roster.py
from tests.helpers.gameplay import make_active_player, make_runtime
from windsprig.gameplay.components import PlayerSlot


def test_runtime_spawns_only_active_players() -> None:
    runtime = make_runtime(players=(make_active_player(1, leader=True),))
    assert [(entity, slot.slot) for entity, slot in runtime.world.query(PlayerSlot)] == [(1, 1)]
    assert tuple(view.slot for view in runtime.snapshot().players) == (1,)
    assert tuple(view.slot for view in runtime.snapshot().camera_targets) == (1,)


def test_pause_lobby_sync_adds_and_removes_ecs_entities() -> None:
    p1 = make_active_player(1, leader=True)
    p2 = make_active_player(2)
    runtime = make_runtime(players=(p1,))
    joined = runtime.sync_active_players((p1, p2))
    assert [event.topic for event in joined] == ["PlayerJoined"]
    left = runtime.sync_active_players((p2,))
    assert [event.topic for event in left] == ["PlayerLeft"]
    assert [slot.slot for _, slot in runtime.world.query(PlayerSlot)] == [2]


def test_base_scheduler_has_one_collision_and_no_legacy_simulation() -> None:
    runtime = make_runtime(players=(make_active_player(1, leader=True),))
    assert tuple(type(system).__name__ for system in runtime.world.scheduler.systems) == (
        "InputCommandSystem", "EnemyAISystem", "MovementSystem", "CollisionSystem",
        "AbilitySystem", "CombatSystem", "DamageSystem", "PickupSystem",
        "CoopRespawnSystem", "StageGoalSystem", "CameraSystem",
    )
```

- [ ] **Step 2: Run the roster tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_runtime_roster.py -q`

Expected: FAIL because the prototype constructor has no `active_players`, always spawns four entities, and has no roster synchronization API.

- [ ] **Step 3: Replace unconditional spawn and capture per-step events**

Use this runtime structure; `_build_snapshot` is the deterministic query/sort constructor for all Task 1 view fields:

```python
class StageRuntime:
    def __init__(self, config, stage, ability_registry, active_players, seed):
        self.config = config
        self.stage = stage
        self.ability_registry = ability_registry
        self.seed = seed
        self.world = self._new_world()
        self.factory = EntityFactory(self.world)
        self.player_entities: dict[int, int] = {}
        self._step_events: list[GameEvent] = []
        self._result: StageResult | None = None
        self.world.events.subscribe("*", self._step_events.append)
        self._spawn_stage_entities()
        self.sync_active_players(active_players)
        self.world.scheduler.systems = [
            InputCommandSystem(), EnemyAISystem(), MovementSystem(), CollisionSystem(),
            AbilitySystem(), CombatSystem(), DamageSystem(), PickupSystem(),
            CoopRespawnSystem(), StageGoalSystem(), CameraSystem(),
        ]

    def step(self, input_frame: InputFrame) -> StageFrame:
        if self._result is not None:
            snapshot = self.snapshot()
            return StageFrame(self.world.snapshot(), snapshot, (), self._result)
        self._step_events.clear()
        simulation = self.world.step(self.config.fixed_dt_ms, input_frame)
        events = tuple(self._step_events)
        return StageFrame(simulation, self.snapshot(), events, self._result)

    def sync_active_players(self, active_players: Sequence[ActivePlayer]) -> tuple[GameEvent, ...]:
        requested = {player.slot: player for player in sorted(active_players, key=lambda item: item.slot)}
        emitted: list[GameEvent] = []
        for slot in sorted(set(self.player_entities) - set(requested)):
            entity_id = self.player_entities.pop(slot)
            self.world.destroy_entity(entity_id)
            emitted.append(make_event(GameplayTopic.PLAYER_LEFT, self.world.frame_index,
                                      entity_id=entity_id, slot=slot))
        for slot in sorted(set(requested) - set(self.player_entities)):
            spawn = self.stage.player_spawns[min(slot - 1, len(self.stage.player_spawns) - 1)]
            entity_id = self.factory.spawn_player(requested[slot], *spawn)
            self.player_entities[slot] = entity_id
            emitted.append(make_event(GameplayTopic.PLAYER_JOINED, self.world.frame_index,
                                      entity_id=entity_id, slot=slot))
        self.world.resources["active_players"] = tuple(requested.values())
        for event in emitted:
            self.world.events.publish(event.topic, event.payload)
        return tuple(emitted)
```

Change `InputCommandSystem` to iterate `PlayerSlot` entities only, and change `CameraSystem`/snapshot construction to include a target only when the entity still exists, its slot is active, `CameraFocus.enabled` is true, and `Health.dead` is false. Remove the prototype `hud` resource; view construction is the only HUD input. Tasks 4, 5, 7, 8, and 9 insert their systems at the positions declared in the final `SYSTEM_ORDER`; Task 9 adds an assertion for the complete tuple.

- [ ] **Step 4: Run focused and existing runtime tests**

Run: `uv run pytest tests/unit/gameplay/test_runtime_roster.py tests/integration/test_stage_runtime_new.py -q`

Expected: all tests PASS; the migrated integration test constructs one explicit `ActivePlayer` and no test observes inactive slots 2–4.

- [ ] **Step 5: Commit active-player runtime integration**

```bash
git add windsprig/gameplay/components windsprig/gameplay/factory.py windsprig/gameplay/runtime.py windsprig/gameplay/systems tests/helpers/gameplay.py tests/unit/gameplay/test_runtime_roster.py tests/integration/test_stage_runtime_new.py
git commit -m "feat: spawn only active gameplay players"
```

### Task 3: Add explicit stage-session states and frozen navigation outcomes

**Files:**
- Create: `windsprig/gameplay/session.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_session.py`

**Interfaces:**
- Consumes: `StageRuntime.step`, `StageRuntime.retry_from_checkpoint`, `StageRuntime.reset_stage`, `StageRuntime.result`, and immutable `StageSnapshot`.
- Produces: `SessionPhase`, `SessionAction`, `SessionNavigation`, `SessionSnapshot`, `GameSession.create(...)`, `step`, `dispatch`, `sync_active_players`, and `snapshot`.

Use these exact public declarations:

```python
class SessionPhase(StrEnum):
    INTRO = "intro"
    PLAYING = "playing"
    PAUSED = "paused"
    VICTORY = "victory"
    DEFEAT = "defeat"
    RESULTS = "results"
    CLOSED = "closed"

class SessionAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    SHOW_RESULTS = "show_results"
    RETRY_CHECKPOINT = "retry_checkpoint"
    RETRY_STAGE = "retry_stage"
    REPLAY_STAGE = "replay_stage"
    NEXT_STAGE = "next_stage"
    RETURN_TO_MAP = "return_to_map"

class SessionNavigation(StrEnum):
    NEXT_STAGE = "next_stage"
    WORLD_MAP = "world_map"

@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    phase: SessionPhase
    stage: StageSnapshot
    result: StageResult | None
    allowed_actions: tuple[SessionAction, ...]
    navigation: SessionNavigation | None
```

- [ ] **Step 1: Write transition and freeze tests**

```python
# tests/unit/gameplay/test_session.py
from tests.helpers.gameplay import enter_victory, make_session
from windsprig.gameplay.session import SessionAction, SessionPhase, SessionNavigation
from windsprig.input.commands import InputFrame


def test_intro_pause_resume_transitions_are_explicit() -> None:
    session = make_session()
    assert session.snapshot().phase is SessionPhase.INTRO
    assert session.dispatch(SessionAction.START).phase is SessionPhase.PLAYING
    assert session.dispatch(SessionAction.PAUSE).phase is SessionPhase.PAUSED
    frame_before = session.runtime.world.frame_index
    session.step(InputFrame.empty())
    assert session.runtime.world.frame_index == frame_before
    assert session.dispatch(SessionAction.RESUME).phase is SessionPhase.PLAYING


def test_results_wait_for_a_choice() -> None:
    session = make_session()
    session.dispatch(SessionAction.START)
    enter_victory(session)
    assert session.dispatch(SessionAction.SHOW_RESULTS).phase is SessionPhase.RESULTS
    closed = session.dispatch(SessionAction.RETURN_TO_MAP)
    assert closed.phase is SessionPhase.CLOSED
    assert closed.navigation is SessionNavigation.WORLD_MAP
```

- [ ] **Step 2: Run session tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_session.py -q`

Expected: FAIL because `GameSession` and typed session phases do not exist.

- [ ] **Step 3: Implement a table-checked session state machine**

```python
ALLOWED_ACTIONS: dict[SessionPhase, tuple[SessionAction, ...]] = {
    SessionPhase.INTRO: (SessionAction.START, SessionAction.RETURN_TO_MAP),
    SessionPhase.PLAYING: (SessionAction.PAUSE,),
    SessionPhase.PAUSED: (SessionAction.RESUME, SessionAction.RETRY_STAGE, SessionAction.RETURN_TO_MAP),
    SessionPhase.VICTORY: (SessionAction.SHOW_RESULTS,),
    SessionPhase.DEFEAT: (SessionAction.RETRY_CHECKPOINT, SessionAction.RETRY_STAGE, SessionAction.RETURN_TO_MAP),
    SessionPhase.RESULTS: (SessionAction.NEXT_STAGE, SessionAction.REPLAY_STAGE, SessionAction.RETURN_TO_MAP),
    SessionPhase.CLOSED: (),
}

def step(self, input_frame: InputFrame) -> SessionSnapshot:
    if self.phase is not SessionPhase.PLAYING:
        return self.snapshot()
    frame = self.runtime.step(input_frame)
    if frame.view.outcome is StageOutcome.COMPLETED:
        self.phase = SessionPhase.VICTORY
    elif frame.view.outcome is StageOutcome.FAILED:
        self.phase = SessionPhase.DEFEAT
    return self.snapshot()

def dispatch(self, action: SessionAction) -> SessionSnapshot:
    if action not in ALLOWED_ACTIONS[self.phase]:
        raise ValueError(f"{action.value} is not allowed from {self.phase.value}")
    self.phase, self.navigation = self._TRANSITIONS[(self.phase, action)]
    if action is SessionAction.RETRY_CHECKPOINT:
        self.runtime.retry_from_checkpoint()
    elif action in {SessionAction.RETRY_STAGE, SessionAction.REPLAY_STAGE}:
        self.runtime.reset_stage()
    return self.snapshot()
```

Define the complete transition table rather than deriving targets from string names:

```python
_TRANSITIONS = {
    (SessionPhase.INTRO, SessionAction.START): (SessionPhase.PLAYING, None),
    (SessionPhase.INTRO, SessionAction.RETURN_TO_MAP): (SessionPhase.CLOSED, SessionNavigation.WORLD_MAP),
    (SessionPhase.PLAYING, SessionAction.PAUSE): (SessionPhase.PAUSED, None),
    (SessionPhase.PAUSED, SessionAction.RESUME): (SessionPhase.PLAYING, None),
    (SessionPhase.PAUSED, SessionAction.RETRY_STAGE): (SessionPhase.PLAYING, None),
    (SessionPhase.PAUSED, SessionAction.RETURN_TO_MAP): (SessionPhase.CLOSED, SessionNavigation.WORLD_MAP),
    (SessionPhase.VICTORY, SessionAction.SHOW_RESULTS): (SessionPhase.RESULTS, None),
    (SessionPhase.DEFEAT, SessionAction.RETRY_CHECKPOINT): (SessionPhase.PLAYING, None),
    (SessionPhase.DEFEAT, SessionAction.RETRY_STAGE): (SessionPhase.PLAYING, None),
    (SessionPhase.DEFEAT, SessionAction.RETURN_TO_MAP): (SessionPhase.CLOSED, SessionNavigation.WORLD_MAP),
    (SessionPhase.RESULTS, SessionAction.NEXT_STAGE): (SessionPhase.CLOSED, SessionNavigation.NEXT_STAGE),
    (SessionPhase.RESULTS, SessionAction.REPLAY_STAGE): (SessionPhase.PLAYING, None),
    (SessionPhase.RESULTS, SessionAction.RETURN_TO_MAP): (SessionPhase.CLOSED, SessionNavigation.WORLD_MAP),
}
```

Implement `GameSession.create(config, stage, ability_registry, active_players, seed) -> GameSession` by constructing `StageRuntime` with the exact Task 2 signature. `sync_active_players` accepts changes only during `INTRO` or `PAUSED`, delegates to the runtime, and raises `ValueError` while playing. Keep the test-only `enter_victory(session)` helper in `tests/helpers/gameplay.py`, not production code: set `runtime.world.resources["stage_outcome"]` and call the same outcome synchronization used after a normal step.

- [ ] **Step 4: Run session tests and confirm GREEN**

Run: `uv run pytest tests/unit/gameplay/test_session.py -q`

Expected: `2 passed`; paused/victory/defeat/results states perform zero ECS steps until an allowed explicit action occurs.

- [ ] **Step 5: Commit session flow**

```bash
git add windsprig/gameplay/session.py tests/helpers/gameplay.py tests/unit/gameplay/test_session.py
git commit -m "feat: add explicit gameplay session states"
```

### Task 4: Implement production movement, finite hover, guard, and dodge

**Files:**
- Modify: `windsprig/gameplay/components/core.py`
- Modify: `windsprig/gameplay/state_machine.py`
- Modify: `windsprig/gameplay/systems/input_command_system.py`
- Modify: `windsprig/gameplay/systems/movement_system.py`
- Modify: `windsprig/gameplay/systems/collision_system.py`
- Create: `windsprig/gameplay/systems/defense_system.py`
- Modify: `windsprig/gameplay/systems/damage_system.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_movement.py`
- Create: `tests/unit/gameplay/test_defense.py`

**Interfaces:**
- Consumes: Task 1 tuning, `MoveCommand(axis: int)`, `JumpCommand(pressed: bool)`, `HoverCommand(held: bool)`, `GuardCommand(held: bool)`, `DodgeCommand(pressed: bool)`, and the existing tile `move_body` result.
- Produces: `MovementState`, `DefenseState`, and damage-queue items with exact keys `source_id`, `target_id`, `amount`, `knockback_x`, `knockback_y`, `guard_break`.

- [ ] **Step 1: Write movement and defense tests before changing systems**

```python
# tests/unit/gameplay/test_movement.py
def test_coyote_buffer_and_finite_hover_use_configured_windows() -> None:
    runtime, player = grounded_runtime()
    movement = runtime.world.get_component(player, MovementState)
    collider = runtime.world.get_component(player, Collider)
    velocity = runtime.world.get_component(player, Velocity)
    collider.on_ground = False
    movement.coyote_remaining_ms = 80
    runtime.step(frame(1, JumpCommand(player_slot=1, pressed=True)))
    assert velocity.vy < -100.0
    assert movement.coyote_remaining_ms == 0

    velocity.vy = 80.0
    movement.hover_remaining_ms = 32
    runtime.step(frame(1, HoverCommand(player_slot=1, held=True)))
    runtime.step(frame(1, HoverCommand(player_slot=1, held=True)))
    runtime.step(frame(1, HoverCommand(player_slot=1, held=True)))
    assert movement.hover_remaining_ms == 0
    assert velocity.vy > 0.0


def test_jump_pressed_120_ms_before_landing_is_consumed_after_landing() -> None:
    runtime, player = falling_runtime(bottom_gap_px=2)
    runtime.step(frame(1, JumpCommand(player_slot=1, pressed=True)))
    assert runtime.world.get_component(player, MovementState).jump_buffer_remaining_ms > 0
    runtime.step(InputFrame.empty())
    assert runtime.world.get_component(player, Velocity).vy < 0.0
```

```python
# tests/unit/gameplay/test_defense.py
def test_front_guard_reduces_damage_and_knockback_but_back_attack_does_not() -> None:
    runtime, player, front_enemy, back_enemy = defense_runtime()
    hold_guard(runtime, slot=1)
    queue_damage(runtime, front_enemy, player, amount=5, knockback_x=-200.0)
    runtime.step(InputFrame.empty())
    assert player_health(runtime, player) == 8
    assert last_event(runtime, "PlayerDamaged").payload["guarded"] is True
    clear_invulnerability(runtime, player)
    queue_damage(runtime, back_enemy, player, amount=5, knockback_x=200.0)
    runtime.step(InputFrame.empty())
    assert player_health(runtime, player) == 3


def test_dodge_has_128_ms_iframes_and_520_ms_cooldown() -> None:
    runtime, player, enemy = defense_runtime()[:3]
    runtime.step(frame(1, DodgeCommand(player_slot=1, pressed=True)))
    defense = runtime.world.get_component(player, DefenseState)
    assert (defense.dodge_remaining_ms, defense.dodge_cooldown_ms) == (160, 520)
    queue_damage(runtime, enemy, player, amount=4)
    runtime.step(InputFrame.empty())
    assert player_health(runtime, player) == 10
    for _ in range(8):
        runtime.step(InputFrame.empty())
    queue_damage(runtime, enemy, player, amount=4)
    runtime.step(InputFrame.empty())
    assert player_health(runtime, player) == 6
```

- [ ] **Step 2: Run movement/defense tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_movement.py tests/unit/gameplay/test_defense.py -q`

Expected: FAIL because ECS players have no movement timers or defense state, hover is infinite, and damage ignores direction/guard/dodge.

- [ ] **Step 3: Implement timers and movement without bypassing collision**

At the start of each `MovementSystem.update`, apply this exact timer/jump logic, then the existing acceleration/deceleration and one gravity application:

```python
if collider.on_ground:
    movement.coyote_remaining_ms = config.coyote_time_ms
    movement.hover_remaining_ms = config.hover_duration_ms
    movement.hover_ready = True
else:
    movement.coyote_remaining_ms = max(0, movement.coyote_remaining_ms - dt_ms)

if intent.jump_pressed:
    movement.jump_buffer_remaining_ms = config.jump_buffer_ms
else:
    movement.jump_buffer_remaining_ms = max(0, movement.jump_buffer_remaining_ms - dt_ms)

can_jump = collider.on_ground or movement.coyote_remaining_ms > 0
if can_jump and movement.jump_buffer_remaining_ms > 0 and defense.dodge_remaining_ms == 0:
    velocity.vy = -config.jump_velocity
    collider.on_ground = False
    movement.coyote_remaining_ms = 0
    movement.jump_buffer_remaining_ms = 0
    state.name = "Jump"

gravity_scale = 1.0
if intent.hover_held and not collider.on_ground and movement.hover_remaining_ms > 0:
    movement.hover_remaining_ms = max(0, movement.hover_remaining_ms - dt_ms)
    gravity_scale = config.hover_gravity_scale
    state.name = "Hover"
velocity.vy = min(velocity.vy + config.gravity * gravity_scale * (dt_ms / 1000.0), 1600.0)
```

`CollisionSystem` must skip every entity with `Attack`, because Task 8 makes `AttackMotionSystem` the only attack mover. Preserve slope/one-way behavior through `move_body`; set `collider.on_ground` from its result and never directly teleport a normal movement step.

- [ ] **Step 4: Implement directional guard and dodge rejection**

```python
def _is_front_guard(world: World, target_id: int, source_id: int, item: dict[str, object]) -> bool:
    defense = world.try_component(target_id, DefenseState)
    facing = world.try_component(target_id, Facing)
    target = world.try_component(target_id, Transform)
    source = world.try_component(source_id, Transform)
    if defense is None or facing is None or target is None or source is None:
        return False
    return defense.guarding and not bool(item["guard_break"]) and (source.x - target.x) * facing.direction >= 0

if defense is not None and defense.dodge_remaining_ms > config.dodge_duration_ms - config.dodge_invulnerable_ms:
    continue
guarded = _is_front_guard(world, target_id, source_id, item)
amount = max(1, math.ceil(int(item["amount"]) * config.guard_damage_multiplier)) if guarded else int(item["amount"])
knockback_scale = config.guard_knockback_multiplier if guarded else 1.0
```

`DefenseSystem` sets `guarding` only while grounded and not dodging/hurt; `MovementSystem` multiplies target speed by `guard_speed_multiplier`. A valid dodge chooses nonzero move axis, otherwise facing, sets velocity to `dodge_speed * direction`, publishes `PlayerDodged`, and does not restart until cooldown reaches zero. Actor-state transitions use public values `Guard` and `Dodge`.

- [ ] **Step 5: Run the focused suite and confirm GREEN**

Run: `uv run pytest tests/unit/gameplay/test_movement.py tests/unit/gameplay/test_defense.py tests/unit/test_physics.py -q`

Expected: all tests PASS; coyote is 100 ms, buffer 120 ms, hover exhausts at 850 ms, front guard reduces 5 damage to 2, and dodge rejects hits for exactly eight 16 ms steps.

- [ ] **Step 6: Commit movement and defense**

```bash
git add windsprig/gameplay/components windsprig/gameplay/state_machine.py windsprig/gameplay/systems tests/helpers/gameplay.py tests/unit/gameplay/test_movement.py tests/unit/gameplay/test_defense.py
git commit -m "feat: add buffered movement guard and dodge"
```

### Task 5: Implement draw/capture release-launch-harmonize and recoverable echo drops

**Files:**
- Modify: `windsprig/gameplay/components/core.py`
- Modify: `windsprig/gameplay/factory.py`
- Create: `windsprig/gameplay/systems/capture_system.py`
- Modify: `windsprig/gameplay/systems/input_command_system.py`
- Modify: `windsprig/gameplay/systems/pickup_system.py`
- Modify: `windsprig/gameplay/systems/__init__.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_capture.py`
- Modify: `tests/integration/test_inhale_copy_new.py` (rename test functions and imports to draw/harmonize, then rename file to `tests/integration/test_draw_harmonize.py`)

**Interfaces:**
- Consumes: canonical `DrawStartCommand`, `DrawReleaseCommand`, `AbilityUseCommand`, `DropAbilityCommand`, Task 1 draw range, `EnemySpawn.ability_id`, and the semantic event table.
- Produces: `CaptureState`, `CapturedBy`, `EchoPickup`, `EntityFactory.spawn_echo_pickup(ability_id: str, x: float, y: float) -> int`, and `world.resources["attack_requests"]: list[AttackRequest]`.

- [ ] **Step 1: Write the three choice tests and echo recovery test**

```python
# tests/unit/gameplay/test_capture.py
def test_release_with_nothing_captured_is_safe_and_spawns_no_attack() -> None:
    runtime, player = capture_runtime(enemy_ability=None, enemy_offset=None)
    runtime.step(frame(1, DrawStartCommand(player_slot=1)))
    result = runtime.step(frame(1, DrawReleaseCommand(player_slot=1)))
    assert event_topics(result) == ("CaptureReleased",)
    assert result.events[0].payload["outcome"] == "empty"
    assert result.view.attacks == ()


def test_release_with_captured_enemy_launches_instead_of_equipping() -> None:
    runtime, player, enemy = capture_runtime(enemy_ability=None, enemy_offset=16.0)
    runtime.step(frame(1, DrawStartCommand(player_slot=1)))
    result = runtime.step(frame(1, DrawReleaseCommand(player_slot=1)))
    assert enemy not in runtime.world.alive_entities
    assert "EnemyLaunched" in event_topics(result)
    request = runtime.world.resources["attack_requests"][0]
    assert (request.attack_kind, request.visual_id, request.damage) == ("launched_enemy", "wind_launch", 4)


def test_ability_while_holding_compatible_capture_harmonizes() -> None:
    runtime, player, enemy = capture_runtime(enemy_ability="cinder", enemy_offset=16.0)
    runtime.step(frame(1, DrawStartCommand(player_slot=1)))
    result = runtime.step(frame(1, AbilityUseCommand(player_slot=1, pressed=True)))
    assert runtime.world.get_component(player, AbilityState).current_id == "cinder"
    assert last_topic(result) == "AbilityEquipped"
    assert enemy not in runtime.world.alive_entities


def test_drop_creates_recoverable_echo_pickup() -> None:
    runtime, player = equipped_runtime("galehook")
    dropped = runtime.step(frame(1, DropAbilityCommand(player_slot=1, pressed=True)))
    pickup = dropped.view.echo_pickups[0]
    assert pickup.ability_id == "galehook"
    move_player_onto(runtime, player, pickup.x, pickup.y)
    picked = runtime.step(InputFrame.empty())
    assert runtime.world.get_component(player, AbilityState).current_id == "galehook"
    assert last_topic(picked) == "AbilityEquipped"
```

- [ ] **Step 2: Run capture tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_capture.py tests/integration/test_draw_harmonize.py -q`

Expected: FAIL because prototype release incorrectly creates an attack when empty, destroys/equips on the wrong action, and drops abilities without a pickup.

- [ ] **Step 3: Implement mutually exclusive capture outcomes**

```python
if intent.draw_started and capture.phase == "idle":
    capture.phase = "drawing"
    capture.draw_elapsed_ms = 0

if capture.phase == "drawing":
    capture.draw_elapsed_ms += dt_ms
    self._capture_nearest_eligible_enemy(world, player_id, capture, transform, facing.direction)

if capture.phase == "holding" and intent.ability_pressed:
    if capture.captured_ability_id is None:
        publish(world, GameplayTopic.HARMONIZE_UNAVAILABLE,
                player_id=player_id, enemy_id=capture.captured_entity_id)
    else:
        ability.previous_id = ability.current_id
        ability.current_id = capture.captured_ability_id
        world.resources.setdefault("discovered_ability_ids", set()).add(ability.current_id)
        publish(world, GameplayTopic.ABILITY_EQUIPPED,
                player_id=player_id, ability_id=ability.current_id, source="capture")
        world.destroy_entity(capture.captured_entity_id)
        intent.ability_consumed = True
        capture.phase = "idle"
        capture.captured_entity_id = None

if intent.draw_released:
    if capture.phase == "holding":
        self._queue_launched_enemy(world, player_id, transform, facing.direction, capture)
    else:
        publish(world, GameplayTopic.CAPTURE_RELEASED, player_id=player_id, outcome="empty")
    capture.phase = "idle"
    capture.draw_elapsed_ms = 0
```

Capture selection sorts candidates by `(abs(dx), enemy_id)`, adds `CapturedBy`, disables its collider/AI motion, and publishes `EnemyCaptured`. Empty release queues nothing. Launch destroys the captured enemy and appends one `AttackRequest` with `ability_id="none"`, `damage=4`, `vx=520.0 * facing`, `ttl_ms=480`, and `visual_id="wind_launch"`. Dropping calls `spawn_echo_pickup` at the player position, equips `none`, and publishes `AbilityDropped`; `PickupSystem` equips and destroys that pickup on overlap.

- [ ] **Step 4: Run capture and migrated integration tests**

Run: `uv run pytest tests/unit/gameplay/test_capture.py tests/integration/test_draw_harmonize.py -q`

Expected: `5 passed`; event order is capture then exactly one of empty release, launch, or harmonize, and dropped ability state is recoverable.

- [ ] **Step 5: Commit the capture choice loop**

```bash
git add windsprig/gameplay/components windsprig/gameplay/factory.py windsprig/gameplay/systems tests/helpers/gameplay.py tests/unit/gameplay/test_capture.py tests/integration/test_draw_harmonize.py
git rm tests/integration/test_inhale_copy_new.py
git commit -m "feat: add draw capture and harmonize choices"
```

### Task 6: Replace generic abilities with Bloomblade and Cinder strategies

**Files:**
- Modify: `windsprig/input/commands.py`
- Modify: `windsprig/input/devices.py`
- Modify: `windsprig/gameplay/abilities/base.py`
- Create: `windsprig/gameplay/abilities/bloomblade.py`
- Create: `windsprig/gameplay/abilities/cinder.py`
- Modify: `windsprig/gameplay/abilities/registry.py`
- Modify: `windsprig/gameplay/systems/ability_system.py`
- Modify: `windsprig/content/abilities.json`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_bloomblade_cinder.py`

**Interfaces:**
- Consumes: `AbilityState`, `AttackRequest`, player transform/facing/grounded state, and `AbilityUseCommand` from foundation.
- Produces: `AbilityUseCommand(player_slot: int, pressed: bool = False, held: bool = False, released: bool = False)`, `AbilityContext`, `AbilityExecution`, and behavior-specific `AbilityStrategy.activate(context) -> AbilityExecution`.

```python
@dataclass(frozen=True, slots=True)
class AbilityContext:
    actor_id: int
    frame_index: int
    x: float
    y: float
    facing: int
    on_ground: bool
    charge_ms: int
    combo_step: int
    meter: int

@dataclass(frozen=True, slots=True)
class AbilityExecution:
    attacks: tuple[AttackRequest, ...]
    cooldown_ms: int
    next_combo_step: int
    combo_window_ms: int = 0
    armor_ms: int = 0
    meter_cost: int = 0
    restore_previous: bool = False
```

- [ ] **Step 1: Write tests proving the first two families are not generic projectiles**

```python
# tests/unit/gameplay/test_bloomblade_cinder.py
def test_bloomblade_is_three_step_melee_arc_and_cuts_projectiles() -> None:
    strategy = BloombladeStrategy()
    first = strategy.activate(context(ability="bloomblade", combo_step=0))
    second = strategy.activate(context(ability="bloomblade", combo_step=first.next_combo_step))
    third = strategy.activate(context(ability="bloomblade", combo_step=second.next_combo_step))
    assert tuple(item.attacks[0].attack_kind for item in (first, second, third)) == (
        "melee_arc", "melee_arc", "melee_arc"
    )
    assert tuple(item.attacks[0].damage for item in (first, second, third)) == (2, 2, 4)
    assert all(item.attacks[0].cuts_projectiles for item in (first, second, third))


def test_cinder_charge_changes_ember_and_creates_lingering_burn_on_hit() -> None:
    tap = CinderStrategy().activate(context(ability="cinder", charge_ms=0))
    charged = CinderStrategy().activate(context(ability="cinder", charge_ms=640))
    assert tap.attacks[0].attack_kind == charged.attacks[0].attack_kind == "charged_ember"
    assert charged.attacks[0].damage > tap.attacks[0].damage
    assert charged.attacks[0].width > tap.attacks[0].width
    assert charged.attacks[0].interaction_kind == "spawn_burn_zone"
```

- [ ] **Step 2: Run strategy tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_bloomblade_cinder.py -q`

Expected: FAIL because only `DataDrivenAbilityStrategy` exists and every ability returns the same attack shape.

- [ ] **Step 3: Implement typed strategies and button phases**

Bloomblade returns arcs at offsets `(28, 2)`, sizes `(38, 30)`, damages `(2, 2, 4)`, cooldowns `(120, 120, 260)`, a `260 ms` combo window, `ttl_ms=80`, and `cuts_projectiles=True`. Cinder clamps charge to `640 ms` and returns:

```python
charge_ratio = min(1.0, context.charge_ms / 640.0)
attack = AttackRequest(
    owner_entity_id=context.actor_id, team="player", ability_id="cinder", attack_kind="charged_ember",
    visual_id="cinder_ember_charged" if charge_ratio == 1.0 else "cinder_ember",
    x=context.x + 20 * context.facing, y=context.y + 8,
    width=18 + int(14 * charge_ratio), height=14 + int(10 * charge_ratio),
    vx=(360.0 + 160.0 * charge_ratio) * context.facing, vy=-20.0,
    damage=2 + int(3 * charge_ratio), knockback_x=220.0 * context.facing,
    knockback_y=-100.0, ttl_ms=900, pierce=0,
    interaction_kind="spawn_burn_zone",
)
return AbilityExecution((attack,), cooldown_ms=320, next_combo_step=0)
```

`InputDeviceMux` emits held every render frame and pressed/released edges. `AbilitySystem` accumulates Cinder charge only while held, activates it only on release, activates Bloomblade on press, ignores `intent.ability_consumed`, resets expired combo state, and queues returned `AttackRequest` values. Replace `abilities.json` with six rows keyed by public IDs and fields `strategy`, `icon_id`, `palette_token`, `enemy_source_tag`; code timing stays in each strategy.

- [ ] **Step 4: Run ability/input tests and confirm GREEN**

Run: `uv run pytest tests/unit/gameplay/test_bloomblade_cinder.py tests/unit/test_input_commands_new.py -q`

Expected: all tests PASS; Bloomblade cycles three arcs and Cinder releases one charge-scaled ember.

- [ ] **Step 5: Commit the first distinct abilities**

```bash
git add windsprig/input windsprig/gameplay/abilities windsprig/gameplay/systems/ability_system.py windsprig/content/abilities.json tests/helpers/gameplay.py tests/unit/gameplay/test_bloomblade_cinder.py tests/unit/test_input_commands_new.py
git commit -m "feat: add Bloomblade and Cinder abilities"
```

### Task 7: Implement Voltsong, Galehook, Stoneheart, and Tempest distinctions

**Files:**
- Create: `windsprig/gameplay/abilities/voltsong.py`
- Create: `windsprig/gameplay/abilities/galehook.py`
- Create: `windsprig/gameplay/abilities/stoneheart.py`
- Create: `windsprig/gameplay/abilities/tempest.py`
- Modify: `windsprig/gameplay/abilities/registry.py`
- Create: `windsprig/gameplay/systems/interaction_system.py`
- Modify: `windsprig/gameplay/systems/ability_system.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_voltsong_galehook.py`
- Create: `tests/unit/gameplay/test_stoneheart_tempest.py`

**Interfaces:**
- Consumes: Task 1 `InteractionSpec`, Task 6 strategy protocol, actor grounded state, and the `AttackRequest.interaction_kind`, `pull_strength`, `guard_break`, and `meter` fields.
- Produces: four registered strategies, `select_chain_targets(origin: tuple[float, float], candidates: Sequence[tuple[int, float, float]], radius_px: float = 132.0, limit: int = 3) -> tuple[int, ...]`, conductor/switch/breakable-floor state transitions, Stoneheart armor, and the one-shot Tempest restore rule.

- [ ] **Step 1: Write distinction tests for all four families**

```python
# tests/unit/gameplay/test_voltsong_galehook.py
def test_voltsong_chains_by_distance_and_energizes_conductor() -> None:
    execution = VoltsongStrategy().activate(context(ability="voltsong"))
    attack = execution.attacks[0]
    assert (attack.attack_kind, attack.damage, attack.interaction_kind) == ("chain_pulse", 2, "conductor")
    assert select_chain_targets((0.0, 0.0), ((9, 140.0, 0.0), (4, 40.0, 0.0), (7, 80.0, 0.0))) == (4, 7)


def test_galehook_returns_pulls_light_enemy_and_activates_switch() -> None:
    attack = GalehookStrategy().activate(context(ability="galehook")).attacks[0]
    assert (attack.attack_kind, attack.ttl_ms, attack.pull_strength, attack.interaction_kind) == (
        "boomerang", 800, 260.0, "switch"
    )
```

```python
# tests/unit/gameplay/test_stoneheart_tempest.py
def test_stoneheart_slam_grants_armor_and_breaks_floor_only_on_landing() -> None:
    execution = StoneheartStrategy().activate(context(ability="stoneheart", on_ground=False))
    attack = execution.attacks[0]
    assert execution.armor_ms == 420
    assert (attack.attack_kind, attack.damage, attack.guard_break, attack.interaction_kind) == (
        "ground_slam", 6, True, "breakable_floor"
    )


def test_tempest_requires_full_meter_hits_each_enemy_once_and_restores_previous() -> None:
    refused = TempestStrategy().activate(context(ability="tempest", meter=99))
    execution = TempestStrategy().activate(context(ability="tempest", meter=100))
    assert refused.attacks == ()
    assert (execution.attacks[0].attack_kind, execution.meter_cost, execution.restore_previous) == (
        "screen_tempest", 100, True
    )
```

- [ ] **Step 2: Run distinction tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_voltsong_galehook.py tests/unit/gameplay/test_stoneheart_tempest.py -q`

Expected: FAIL because these strategies and interaction semantics do not exist.

- [ ] **Step 3: Implement the exact four executions**

- Voltsong returns `chain_pulse`, radius `132 px`, maximum `3` targets sorted by `(distance_squared, entity_id)`, damage `2`, and `interaction_kind="conductor"`; each conductor overlap changes `idle -> energized`.
- Galehook returns `boomerang`, outbound `360 ms`, return-to-owner phase until `800 ms`, damage `2`, `pull_strength=260.0`, and `interaction_kind="switch"`; only enemies whose `EnemyAI.kind != "brute"` are pulled.
- Stoneheart requires airborne activation, sets `armor_ms=420`, and creates `ground_slam` with `damage=6`, `guard_break=True`, and `interaction_kind="breakable_floor"`; the interaction becomes `broken` only when the owner lands while the slam exists.
- Tempest returns one `screen_tempest` volume covering stage bounds, `damage=5`, `pierce=10_000`, `meter_cost=100`, `restore_previous=True`, and refuses activation when `context.meter < 100`.

Register exactly these classes:

```python
def create_default_registry(content_dir: Path) -> AbilityRegistry:
    registry = AbilityRegistry()
    for strategy in (
        NoneAbilityStrategy(), BloombladeStrategy(), CinderStrategy(),
        VoltsongStrategy(), GalehookStrategy(), StoneheartStrategy(), TempestStrategy(),
    ):
        registry.register(strategy)
    registry.validate_metadata(content_dir / "abilities.json")
    return registry
```

`select_chain_targets` filters candidates whose squared distance is at most `132 ** 2`, sorts by `(distance_squared, entity_id)`, and returns the first three IDs. `InteractionSystem` sorts attack/interaction pairs by `(attack_id, interaction_id)`, applies each state transition once, and never publishes presentation-only particles or sounds. Task 8 adds the integration assertions for boomerang return/pull, chain hits, landing break, and Tempest once-per-target damage after visible attacks exist.

- [ ] **Step 4: Run all six strategy tests and confirm GREEN**

Run: `uv run pytest tests/unit/gameplay/test_bloomblade_cinder.py tests/unit/gameplay/test_voltsong_galehook.py tests/unit/gameplay/test_stoneheart_tempest.py -q`

Expected: all tests PASS; every public family has a different attack kind, timing, interaction, and state effect.

- [ ] **Step 5: Commit the remaining distinct abilities**

```bash
git add windsprig/gameplay/abilities windsprig/gameplay/systems/interaction_system.py windsprig/gameplay/systems/ability_system.py tests/helpers/gameplay.py tests/unit/gameplay/test_voltsong_galehook.py tests/unit/gameplay/test_stoneheart_tempest.py
git commit -m "feat: complete six distinct ability families"
```

### Task 8: Make attacks visible and advance/resolve them exactly once per step

**Files:**
- Create: `windsprig/gameplay/systems/attack_spawn_system.py`
- Create: `windsprig/gameplay/systems/attack_motion_system.py`
- Modify: `windsprig/gameplay/systems/collision_system.py`
- Modify: `windsprig/gameplay/systems/combat_system.py`
- Modify: `windsprig/gameplay/systems/damage_system.py`
- Modify: `windsprig/gameplay/snapshot.py`
- Modify: `windsprig/gameplay/systems/__init__.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_attack_pipeline.py`
- Create: `tests/integration/test_gameplay_action_flow.py`

**Interfaces:**
- Consumes: `world.resources["attack_requests"]`, `AttackRequest`, `Attack`, Task 4 damage items, six strategy attack kinds, and `StageSnapshot.attacks`.
- Produces: visible `AttackView` entries, exactly one motion owner, once-per-attack/target damage, projectile cutting, lingering Cinder burn zones, and `AttackSpawned`/`AttackHit`/`ProjectileCut`/`EnemyDefeated` events.

- [ ] **Step 1: Write exactly-once and event-order tests**

```python
# tests/unit/gameplay/test_attack_pipeline.py
def test_new_projectile_is_visible_and_advances_once_on_birth_step() -> None:
    runtime, player = equipped_runtime("cinder")
    start_x = entity_x(runtime, player) + 20.0
    result = runtime.step(frame(1, AbilityUseCommand(player_slot=1, released=True)))
    attack = result.view.attacks[0]
    component = runtime.world.get_component(attack.entity_id, Attack)
    assert attack.x == pytest.approx(start_x + component_velocity_x(runtime, attack.entity_id) * 0.016)
    assert component.last_advanced_frame == result.simulation.frame_index
    assert event_topics(result)[:2] == ("AttackSpawned", "AbilityUsed")


def test_stationary_overlap_damages_target_once_per_attack_entity() -> None:
    runtime, player, enemy = overlapping_attack_runtime()
    first = runtime.step(InputFrame.empty())
    hp_after_first = entity_health(runtime, enemy)
    second = runtime.step(InputFrame.empty())
    assert entity_health(runtime, enemy) == hp_after_first
    assert count_topic(first, "AttackHit") == 1
    assert count_topic(second, "AttackHit") == 0


def test_bloomblade_cuts_hostile_projectile_without_hurting_player() -> None:
    runtime, player, hostile = projectile_cut_runtime()
    result = runtime.step(frame(1, AbilityUseCommand(player_slot=1, pressed=True)))
    assert hostile not in runtime.world.alive_entities
    assert count_topic(result, "ProjectileCut") == 1
    assert entity_health(runtime, player) == 10
```

- [ ] **Step 2: Run pipeline tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_attack_pipeline.py -q`

Expected: FAIL because requests are still generic resources, collision and combat both move velocity-bearing entities, and no visible attack snapshot/event contract exists.

- [ ] **Step 3: Create attacks, then move each once with a frame guard**

```python
class AttackMotionSystem:
    def update(self, world: World, dt_ms: int) -> None:
        dt_seconds = dt_ms / 1000.0
        expired: list[int] = []
        for entity_id, attack, transform, velocity in world.query(Attack, Transform, Velocity):
            if attack.last_advanced_frame == world.frame_index:
                raise AssertionError(f"attack {entity_id} advanced twice in frame {world.frame_index}")
            transform.x += velocity.vx * dt_seconds
            transform.y += velocity.vy * dt_seconds
            attack.ttl_ms = max(0, attack.ttl_ms - dt_ms)
            attack.last_advanced_frame = world.frame_index
            if attack.ttl_ms == 0:
                expired.append(entity_id)
        for entity_id in expired:
            world.destroy_entity(entity_id)
```

`AttackSpawnSystem` drains requests FIFO, assigns entity IDs through `World.create_entity`, adds `Transform`, `Velocity`, non-solid `Collider`, `Team`, and `Attack`, publishes `AttackSpawned`, then publishes `AbilityUsed(player_id=request.owner_entity_id, ability_id=request.ability_id, attack_ids=(attack_id,))` when `ability_id != "none"`. `AbilitySystem` does not publish `AbilityUsed` before IDs exist. The new entity remains in the same step for exactly one `AttackMotionSystem` update. `CollisionSystem` begins each row with `if world.has_component(entity_id, Attack): continue`.

- [ ] **Step 4: Resolve sorted overlaps and publish post-mitigation hits**

`CombatSystem` sorts attacks by ID and target rows by ID, skips owner/friendly/dead/already-hit targets, records the target in `hit_entity_ids`, and appends:

```python
damage_queue.append({
    "attack_id": attack_id,
    "source_id": attack.owner_entity_id,
    "target_id": target_id,
    "amount": attack.damage,
    "knockback_x": attack.knockback_x,
    "knockback_y": attack.knockback_y,
    "guard_break": attack.guard_break,
})
```

`DamageSystem`, after dodge/guard calculation, publishes `AttackHit` with the applied amount and guarded flag, then `PlayerDamaged` for a player target. At zero HP it publishes `EnemyDefeated` or `PlayerDefeated`. Bloomblade overlap with a hostile attack destroys the hostile attack and publishes `ProjectileCut`. A Cinder ember hit appends one `burn_zone` request (`48x30`, `damage=1`, `ttl_ms=960`, zero velocity); Galehook reverses velocity at `born_frame + 23` steps and homes toward its owner; chain pulse and Tempest use sorted deterministic target selection.

- [ ] **Step 5: Run pipeline and complete-action integration tests**

Add `test_move_draw_launch_harmonize_each_ability_guard_dodge_and_damage()` to `tests/integration/test_gameplay_action_flow.py`; drive only `StageRuntime.step` and assert all action events appear in the expected order.

Run: `uv run pytest tests/unit/gameplay/test_attack_pipeline.py tests/integration/test_gameplay_action_flow.py -q`

Expected: all tests PASS; every attack is present in `StageSnapshot.attacks`, moves once per frame, and hits a given target once.

- [ ] **Step 6: Commit visible deterministic combat**

```bash
git add windsprig/gameplay/systems windsprig/gameplay/snapshot.py tests/helpers/gameplay.py tests/unit/gameplay/test_attack_pipeline.py tests/integration/test_gameplay_action_flow.py
git commit -m "feat: add visible single-step combat events"
```

### Task 9: Add checkpoints, explicit victory/defeat, retries, and raw results

**Files:**
- Modify: `windsprig/gameplay/factory.py`
- Create: `windsprig/gameplay/systems/checkpoint_system.py`
- Modify: `windsprig/gameplay/systems/coop_respawn_system.py`
- Modify: `windsprig/gameplay/systems/stage_goal_system.py`
- Modify: `windsprig/gameplay/runtime.py`
- Modify: `windsprig/gameplay/session.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_checkpoints_outcomes.py`
- Create: `tests/integration/test_gameplay_session_flow.py`

**Interfaces:**
- Consumes: stable `CheckpointSpec`, team active slots, Task 3 phases, Task 8 death events, and the Task 1 `StageResult` fields.
- Produces: `StageRuntime.can_retry_checkpoint: bool`, functional `retry_from_checkpoint`/`reset_stage`, one active team checkpoint, frozen completion/failure outcomes, and populated `StageResult`.

- [ ] **Step 1: Write checkpoint, result, and freeze tests**

```python
# tests/unit/gameplay/test_checkpoints_outcomes.py
def test_checkpoint_retry_costs_one_life_and_restores_safe_state() -> None:
    runtime, player, checkpoint = checkpoint_runtime()
    move_player_onto_checkpoint(runtime, player, checkpoint)
    reached = runtime.step(InputFrame.empty())
    assert last_topic(reached) == "CheckpointReached"
    defeat_player(runtime, player)
    assert runtime.snapshot().outcome is StageOutcome.FAILED
    before = runtime.world.get_component(player, PlayerSlot).lives
    retried = runtime.retry_from_checkpoint()
    assert runtime.world.get_component(player, PlayerSlot).lives == before - 1
    assert (retried.players[0].x, retried.players[0].y) == checkpoint_position(runtime, checkpoint)


def test_solo_goal_creates_result_once_and_freezes_world() -> None:
    runtime, player = goal_runtime()
    move_player_to_goal(runtime, player)
    completed = runtime.step(InputFrame.empty())
    assert completed.view.outcome is StageOutcome.COMPLETED
    assert completed.result == StageResult(
        stage_id=runtime.stage.stage_id, world_id=runtime.stage.world_id,
        node_id=runtime.stage.node_id, clear_time_ms=16,
        collected_mote_ids=(), discovered_ability_ids=(), active_slots=(1,), deaths_by_slot=((1, 0),),
    )
    frame_index = runtime.world.frame_index
    assert runtime.step(InputFrame.empty()).simulation.frame_index == frame_index
    assert count_topic(completed, "StageCompleted") == 1


def test_final_scheduler_order_matches_the_gameplay_contract() -> None:
    runtime, _ = goal_runtime()
    assert tuple(type(system).__name__ for system in runtime.world.scheduler.systems) == tuple(
        system_type.__name__ for system_type in runtime.SYSTEM_ORDER
    )
    assert tuple(type(system).__name__ for system in runtime.world.scheduler.systems).count(
        "AttackMotionSystem"
    ) == 1
```

- [ ] **Step 2: Run outcome tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_checkpoints_outcomes.py tests/integration/test_gameplay_session_flow.py -q`

Expected: FAIL because there are no stable checkpoint entities, result DTO creation, explicit retry cost, or frozen session outcomes.

- [ ] **Step 3: Activate checkpoints and implement deterministic retry**

At construction, spawn all stage checkpoints and set the first one active in `world.resources["active_checkpoint_id"]`. `CheckpointSystem` checks live active players and inactive checkpoints in sorted entity order; the first overlap deactivates the prior checkpoint, activates the new one, stores its ID, and publishes `CheckpointReached` once.

```python
def retry_from_checkpoint(self) -> StageSnapshot:
    if not self.can_retry_checkpoint:
        raise ValueError("checkpoint retry is unavailable")
    checkpoint = self._active_checkpoint()
    for entity_id, slot, health, transform, velocity, defense in self.world.query(
        PlayerSlot, Health, Transform, Velocity, DefenseState
    ):
        slot.lives -= 1
        health.current = health.maximum
        health.dead = False
        health.invulnerable_ms = self.config.respawn_invulnerable_ms
        transform.x, transform.y = checkpoint.x, checkpoint.y
        velocity.vx = velocity.vy = 0.0
        defense.dodge_remaining_ms = 0
        publish(self.world, GameplayTopic.PLAYER_RESPAWNED, entity_id=entity_id,
                slot=slot.slot, checkpoint_id=checkpoint.checkpoint_id, cost=1)
    self.world.resources["stage_outcome"] = StageOutcome.RUNNING
    self._result = None
    return self.snapshot()
```

`can_retry_checkpoint` is true only when outcome is failed and every required active player has at least one life. `reset_stage` reconstructs the world with the original seed and current active-player sequence, so replay state starts at frame zero.

- [ ] **Step 4: Complete/fail once and create raw results**

For a valid solo goal, store `StageOutcome.COMPLETED`, build `StageResult` from sorted resource sets/slot counters, publish `StageCompleted`, and make later `step` calls return the same snapshot/result with no scheduler run. When every active player is dead, store `FAILED`, publish `StageFailed` once, and let `GameSession.step` enter `DEFEAT`. `GameSession.allowed_actions` omits `RETRY_CHECKPOINT` when `can_retry_checkpoint` is false. Victory requires `SHOW_RESULTS` before the results choices; completion/save services in subproject 3 consume `StageResult` after that transition. At this point assign `StageRuntime.SYSTEM_ORDER = SYSTEM_ORDER` and construct the scheduler from the exact 17-class tuple in “ECS component and system-order contract.”

- [ ] **Step 5: Run session outcome tests and confirm GREEN**

Run: `uv run pytest tests/unit/gameplay/test_checkpoints_outcomes.py tests/unit/gameplay/test_session.py tests/integration/test_gameplay_session_flow.py -q`

Expected: all tests PASS; checkpoint retry has a visible one-life cost, stage retry resets deterministically, and completed/failed worlds do not advance.

- [ ] **Step 6: Commit checkpoint and result flow**

```bash
git add windsprig/gameplay/factory.py windsprig/gameplay/runtime.py windsprig/gameplay/session.py windsprig/gameplay/systems tests/helpers/gameplay.py tests/unit/gameplay/test_checkpoints_outcomes.py tests/integration/test_gameplay_session_flow.py
git commit -m "feat: add checkpoints outcomes and results"
```

### Task 10: Implement co-op respawn and leader-confirmed goal gathering

**Files:**
- Modify: `windsprig/input/commands.py`
- Modify: `windsprig/input/devices.py`
- Modify: `windsprig/gameplay/components/core.py`
- Modify: `windsprig/gameplay/systems/input_command_system.py`
- Modify: `windsprig/gameplay/systems/coop_respawn_system.py`
- Modify: `windsprig/gameplay/systems/stage_goal_system.py`
- Modify: `windsprig/gameplay/runtime.py`
- Modify: `tests/helpers/gameplay.py`
- Create: `tests/unit/gameplay/test_coop_goal.py`
- Modify: `tests/integration/test_gameplay_session_flow.py`

**Interfaces:**
- Consumes: active-player `is_leader`, stable active checkpoint, `GatherState`, goal collider, and `InputFrame`.
- Produces: `GatherConfirmCommand(player_slot: int, pressed: bool)`, living-anchor respawn, exact 3000 ms gather countdown/cancel semantics, and `GoalGatherView`.

- [ ] **Step 1: Write co-op recovery and gather tests**

```python
# tests/unit/gameplay/test_coop_goal.py
def test_dead_partner_respawns_near_living_anchor_after_delay_with_cost() -> None:
    runtime, p1, p2 = coop_runtime()
    defeat_player(runtime, p2)
    p1_x = entity_x(runtime, p1)
    step_until(runtime, lambda: player_view(runtime, slot=2).actor_state != "Defeated", max_steps=114)
    view = player_view(runtime, slot=2)
    assert view.lives_remaining == 2
    assert view.x == pytest.approx(p1_x + 18.0)
    assert last_published_topic(runtime) == "PlayerRespawned"


def test_one_player_at_goal_does_not_clear_without_leader_gather() -> None:
    runtime, p1, p2 = coop_runtime()
    move_player_to_goal(runtime, p1)
    runtime.step(InputFrame.empty())
    assert runtime.snapshot().outcome is StageOutcome.RUNNING
    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    step_count(runtime, 187)
    assert runtime.snapshot().outcome is StageOutcome.RUNNING
    final = runtime.step(InputFrame.empty())
    assert final.view.outcome is StageOutcome.COMPLETED
    assert "GatherCompleted" in event_topics(final)


def test_nonleader_cannot_gather_and_leader_leaving_goal_cancels() -> None:
    runtime, p1, p2 = coop_runtime()
    move_player_to_goal(runtime, p1)
    ignored = runtime.step(frame(2, GatherConfirmCommand(player_slot=2, pressed=True)))
    assert "GatherStarted" not in event_topics(ignored)
    runtime.step(frame(1, GatherConfirmCommand(player_slot=1, pressed=True)))
    move_player_away_from_goal(runtime, p1)
    cancelled = runtime.step(InputFrame.empty())
    assert last_topic(cancelled) == "GatherCancelled"
```

- [ ] **Step 2: Run co-op tests and confirm RED**

Run: `uv run pytest tests/unit/gameplay/test_coop_goal.py -q`

Expected: FAIL because any one player currently clears the goal and respawn/gather does not use active roster leadership.

- [ ] **Step 3: Implement living-anchor recovery**

`CoopRespawnSystem` derives active entities from `world.resources["active_players"]`, sorted by slot. While at least one active teammate is alive, a dead player with `lives > 0` counts down `respawn_delay_ms`, pays one life, respawns `18 * slot` px beside the lowest-slot living anchor, receives `respawn_invulnerable_ms`, and publishes `PlayerRespawned`. If all active players are dead, do not auto-respawn; Task 9 failure/retry owns that decision. Inactive/removed slots are never anchors or respawn candidates.

- [ ] **Step 4: Implement all-at-goal or leader-confirmed gather**

```python
required_slots = tuple(sorted(
    slot.slot for _, slot, health in world.query(PlayerSlot, Health)
    if not (health.dead and slot.lives == 0)
))
at_goal_slots = tuple(sorted(self._slots_overlapping_goal(world, include_dead=False)))
if required_slots and at_goal_slots == required_slots:
    self._complete_stage(world)
    return

leader = next((player for player in world.resources["active_players"] if player.is_leader), None)
leader_confirmed = leader is not None and leader.slot in intent.gather_confirmed_slots
if gather.countdown_remaining_ms == 0 and leader_confirmed and leader.slot in at_goal_slots:
    gather.leader_slot = leader.slot
    gather.leader_confirmed = True
    gather.countdown_remaining_ms = world.resources["config"].gather_countdown_ms
    publish(world, GameplayTopic.GATHER_STARTED, leader_slot=leader.slot,
            countdown_ms=gather.countdown_remaining_ms,
            waiting_slots=tuple(slot for slot in required_slots if slot not in at_goal_slots))
```

Decrease the countdown by `dt_ms` while the same leader remains active/alive/at goal. On zero, teleport living waiting players to deterministic goal offsets, revive dead players that have lives with the normal one-life cost, publish `GatherCompleted`, then complete the stage. Publish `GatherCancelled` with the table’s exact reason when leader/roster validity changes; `sync_active_players` cancels before applying a roster mutation. `GoalGatherView` reports the current exact state every snapshot.

- [ ] **Step 5: Run co-op and session flow tests**

Run: `uv run pytest tests/unit/gameplay/test_coop_goal.py tests/integration/test_gameplay_session_flow.py -q`

Expected: all tests PASS; inactive/dead players never trigger the goal, ordinary co-op requires everyone, and a leader-confirmed gather expires after 188 fixed steps (`3008 ms`, the first step at or past 3000 ms).

- [ ] **Step 6: Commit co-op recovery and gather**

```bash
git add windsprig/input windsprig/gameplay/components windsprig/gameplay/runtime.py windsprig/gameplay/systems tests/helpers/gameplay.py tests/unit/gameplay/test_coop_goal.py tests/integration/test_gameplay_session_flow.py
git commit -m "feat: add co-op respawn and goal gather"
```

### Task 11: Move replay/flow evidence to the ECS and delete the competing runtime

**Files:**
- Create: `windsprig/gameplay/replay.py`
- Modify: `tools/replay_runner.py`
- Create: `tests/fixtures/replays/production_flow_v1.json`
- Create: `tests/integration/test_gameplay_replay.py`
- Create: `tests/architecture/test_single_gameplay_runtime.py`
- Modify: `pyproject.toml`
- Delete: all files listed in “Delete only in Task 11” above, after the replacement assertions are green

**Interfaces:**
- Consumes: `derive_stage_seed`, `StageRuntime`, public command classes, `StageFrame.simulation.world_state_hash`, and semantic events.
- Produces: `ReplayRecord`, `ReplayStep`, `ReplayReport`, `load_replay(path: Path) -> ReplayRecord`, `ReplayRunner.run(record: ReplayRecord) -> ReplayReport`, and CLI record/verify behavior.

Use this exact schema:

```python
@dataclass(frozen=True, slots=True)
class ReplayStep:
    commands_by_slot: tuple[tuple[int, tuple[dict[str, object], ...]], ...]
    expected_world_hash: str | None = None
    expected_topics: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ReplayRecord:
    schema_version: int
    stage_id: str
    base_seed: int
    active_slots: tuple[int, ...]
    steps: tuple[ReplayStep, ...]

@dataclass(frozen=True, slots=True)
class ReplayReport:
    hashes: tuple[str, ...]
    topics_by_step: tuple[tuple[str, ...], ...]
    matched: bool
```

- [ ] **Step 1: Write replay parity, full-flow, and architecture tests**

```python
# tests/integration/test_gameplay_replay.py
def test_production_fixture_matches_every_recorded_hash_and_event_step() -> None:
    record = load_replay(Path("tests/fixtures/replays/production_flow_v1.json"))
    report = ReplayRunner(test_catalog(), test_registry()).run(record)
    assert len(report.hashes) == len(record.steps) == 240
    assert report.matched is True


def test_same_fixture_is_identical_across_two_fresh_ecs_worlds() -> None:
    record = load_replay(Path("tests/fixtures/replays/production_flow_v1.json"))
    runner = ReplayRunner(test_catalog(), test_registry())
    assert runner.run(record) == runner.run(record)
```

```python
# tests/architecture/test_single_gameplay_runtime.py
from pathlib import Path

FORBIDDEN = ("simulation.py", "player.py", "enemies.py", "entities.py", "combat.py")

def test_only_ecs_gameplay_runtime_remains() -> None:
    package = Path("windsprig")
    assert all(not (package / name).exists() for name in FORBIDDEN)
    imports = "\n".join(path.read_text(encoding="utf-8") for path in package.rglob("*.py"))
    assert "from windsprig.simulation" not in imports
    assert "from windsprig.player" not in imports
    assert "from windsprig.combat" not in imports
```

Also add `test_title_profile_map_intro_play_pause_defeat_retry_victory_results_choices()` to `tests/integration/test_gameplay_session_flow.py`. Use a headless screen harness implementing foundation `Screen.fixed_update`; assert the exact phase sequence and that `NEXT_STAGE`/`WORLD_MAP` become `ScreenTransition` payloads containing the same `StageResult` object.

- [ ] **Step 2: Run replay/architecture tests and confirm RED**

Run: `uv run pytest tests/integration/test_gameplay_replay.py tests/architecture/test_single_gameplay_runtime.py -q`

Expected: FAIL because the replay tool still imports `Simulation`, the fixture lacks ECS hashes, and competing modules still exist.

- [ ] **Step 3: Implement the deterministic replay codec and runner**

```python
def run(self, record: ReplayRecord) -> ReplayReport:
    stage = self.catalog.stages[record.stage_id]
    players = tuple(make_replay_player(slot, leader=index == 0)
                    for index, slot in enumerate(record.active_slots))
    runtime = StageRuntime(GameConfig(), stage, self.registry, players,
                           derive_stage_seed(record.base_seed, record.stage_id))
    hashes: list[str] = []
    topics: list[tuple[str, ...]] = []
    matched = True
    for step in record.steps:
        frame = runtime.step(decode_input_frame(step.commands_by_slot))
        hashes.append(frame.simulation.world_state_hash)
        frame_topics = tuple(event.topic for event in frame.events)
        topics.append(frame_topics)
        if step.expected_world_hash is not None:
            matched = matched and step.expected_world_hash == hashes[-1]
        if step.expected_topics:
            matched = matched and step.expected_topics == frame_topics
    return ReplayReport(tuple(hashes), tuple(topics), matched)
```

The JSON fixture has `schema_version: 1`, stage `world_1_stage_1`, base seed `1337`, active slots `[1, 2]`, and exactly 240 input steps covering move, buffered jump, hover exhaustion, guard, dodge, draw-empty release, capture launch, one harmonize/use sequence from an authored enemy source, damage, the deterministic start checkpoint, partner respawn, gather, and completion. All six abilities remain covered by Tasks 6–8 rather than by non-player replay commands. `tools/replay_runner.py --record-hashes` writes each currently null expected hash and observed nonempty topic tuple; normal invocation is verify-only and never rewrites the fixture.

- [ ] **Step 4: Record once, then verify the immutable fixture twice**

Run: `uv run python tools/replay_runner.py tests/fixtures/replays/production_flow_v1.json --record-hashes`

Expected: `Recorded 240 gameplay steps in tests/fixtures/replays/production_flow_v1.json` and exit code 0.

Run: `uv run python tools/replay_runner.py tests/fixtures/replays/production_flow_v1.json`

Expected: `Replay OK: 240/240 gameplay hashes matched` and exit code 0 on two consecutive invocations.

- [ ] **Step 5: Delete the absorbed runtime and migrate/remove its tests**

```bash
git rm windsprig/simulation.py windsprig/player.py windsprig/enemies.py windsprig/entities.py windsprig/combat.py
git rm tests/unit/test_player.py tests/unit/test_enemy.py tests/unit/test_combat.py tests/unit/test_determinism.py
git rm tests/integration/test_game_flow.py tests/integration/test_replay_runner.py tests/integration/replay_sample.json
```

Run: `rg -n "windsprig\.(simulation|player|enemies|entities|combat)|Simulation\(|InputState" windsprig tests tools`

Expected: exit code 1 and no matches. If a behavior assertion existed only in a deleted test, move that assertion into the named production-ECS test covering the same behavior before running the deletion; do not retain an adapter or second runtime.

- [ ] **Step 6: Run all gameplay flow/replay gates**

Run: `uv run pytest tests/unit/gameplay tests/integration/test_gameplay_action_flow.py tests/integration/test_gameplay_session_flow.py tests/integration/test_gameplay_replay.py tests/architecture/test_single_gameplay_runtime.py -q`

Expected: all tests PASS, including the 240-step fixture, full action loop, both result choices, checkpoint/stage retries, and co-op gather.

- [ ] **Step 7: Run the complete suite and coverage gate**

Run: `uv run coverage run --branch -m pytest -q`

Expected: the complete repository suite passes with no collection warnings or import of deleted modules.

Run: `uv run coverage report --fail-under=85`

Expected: exit code 0 and `TOTAL` branch-inclusive coverage at or above `85%` for `windsprig` production modules.

- [ ] **Step 8: Commit replay evidence and single-runtime consolidation**

```bash
git add windsprig/gameplay/replay.py tools/replay_runner.py tests/fixtures/replays/production_flow_v1.json tests/integration/test_gameplay_replay.py tests/integration/test_gameplay_session_flow.py tests/architecture/test_single_gameplay_runtime.py pyproject.toml
git add -u
git commit -m "test: prove production gameplay flow and replay"
```

## Final verification checklist

- [ ] Run `uv run pytest -q`; expected: every repository test passes.
- [ ] Run `uv run coverage report --fail-under=85`; expected: exit code 0 with branch coverage at least 85%.
- [ ] Run `uv run python tools/replay_runner.py tests/fixtures/replays/production_flow_v1.json` twice; expected both outputs are `Replay OK: 240/240 gameplay hashes matched`.
- [ ] Run `rg -n "kirby|nintendo|return to dream land|energy_sphere|inhale|copy_ability" windsprig tests tools`; expected: no public/runtime legacy identifier matches (license/history documents outside these paths are not part of this check).
- [ ] Run `rg -n "windsprig\.(simulation|player|enemies|entities|combat)|Simulation\(|InputState" windsprig tests tools`; expected: no competing-runtime matches.
- [ ] Inspect `StageRuntime.SYSTEM_ORDER`; expected: it equals the 17-system tuple in this plan and contains `AttackMotionSystem` exactly once.
- [ ] Inspect the six ability test files; expected: all six IDs have a named behavioral test and no two families assert the same attack-kind/timing/interaction tuple.
- [ ] Inspect `tests/integration/test_gameplay_session_flow.py`; expected: named assertions cover intro, playing, paused, checkpoint retry, stage retry, defeat, victory, results, replay, next stage, world map, co-op join/leave, respawn, and gather.
