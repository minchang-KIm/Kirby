"""Deterministic builders for production gameplay tests."""

from __future__ import annotations

from windsprig.config import GameConfig
from windsprig.content.loader import (
    CheckpointSpec,
    EnemySpawn,
    InteractionSpec,
    MoteSpec,
    StageSpec,
)
from windsprig.core.events import GameEvent
from windsprig.gameplay.abilities import AbilityContext, create_default_registry
from windsprig.gameplay.components import DamageRecord, Health, StageGoal, Transform
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.session import GameSession
from windsprig.gameplay.snapshot import PlayerView, StageFrame
from windsprig.input.commands import InputCommand, InputFrame
from windsprig.input.roster import ActivePlayer, DeviceRef


class _RecordingStageRuntime(StageRuntime):
    """Stage runtime subtype carrying only test-observer state."""

    test_events: list[GameEvent]


def frame(slot: int, *commands: InputCommand) -> InputFrame:
    """Build one deterministic command frame without routing through devices."""
    return InputFrame(commands_by_slot={slot: list(commands)})


def ability_context(
    *,
    actor_id: int = 1,
    frame_index: int = 0,
    x: float = 100.0,
    y: float = 50.0,
    facing: int = 1,
    on_ground: bool = True,
    charge_ms: int = 0,
    combo_step: int = 0,
    meter: int = 0,
) -> AbilityContext:
    """Build an exact immutable ability activation context."""
    return AbilityContext(
        actor_id=actor_id,
        frame_index=frame_index,
        x=x,
        y=y,
        facing=facing,
        on_ground=on_ground,
        charge_ms=charge_ms,
        combo_step=combo_step,
        meter=meter,
    )


def make_active_player(slot: int, leader: bool = False) -> ActivePlayer:
    """Build a stable keyboard-backed player identity for ``slot``."""
    return ActivePlayer(
        slot=slot,
        device=DeviceRef(
            kind="keyboard",
            uid=f"test-kb-{slot}",
            label=f"Test Keyboard {slot}",
        ),
        color_token=f"player-{slot}",
        icon_token=f"sprig-{slot}",
        is_leader=leader,
    )


def make_stage(
    *,
    player_spawns: tuple[tuple[float, float], ...] = ((64.0, 160.0),),
    enemy_spawns: tuple[EnemySpawn, ...] = (),
    motes: tuple[MoteSpec, ...] = (),
    checkpoints: tuple[CheckpointSpec, ...] = (CheckpointSpec("test_stage:checkpoint:1", 2, 7),),
    interactions: tuple[InteractionSpec, ...] = (),
) -> StageSpec:
    """Build a compact flat stage without coupling tests to campaign content."""
    return StageSpec(
        stage_id="test_stage",
        world_id="test_world",
        node_id="test_node",
        width_tiles=20,
        height_tiles=10,
        tile_size=32,
        ground_y_tile=8,
        player_spawns=player_spawns,
        enemy_spawns=enemy_spawns,
        motes=motes,
        checkpoints=checkpoints,
        interactions=interactions,
        goal_tile=(18, 7),
        hazards=(),
        one_way_tiles=(),
        solids=tuple((tile_x, 8) for tile_x in range(20)),
    )


def make_runtime(
    players: tuple[ActivePlayer, ...] | None = None,
    stage: StageSpec | None = None,
) -> _RecordingStageRuntime:
    """Build a fresh seeded runtime and attach a test-only event recorder."""
    active_players = players if players is not None else (make_active_player(1, leader=True),)
    config = GameConfig()
    runtime = _RecordingStageRuntime(
        config,
        stage or make_stage(),
        create_default_registry(config.content_dir),
        active_players,
        seed=77,
    )
    recorded_events: list[GameEvent] = []
    runtime.world.events.subscribe("*", recorded_events.append)
    runtime.test_events = recorded_events
    return runtime


def make_coop_runtime(player_count: int = 2) -> _RecordingStageRuntime:
    """Build a flat stage with canonical slots and distinct spawn anchors."""

    if type(player_count) is not int or not 2 <= player_count <= 4:
        raise ValueError("co-op player count must be an integer in [2, 4]")
    players = tuple(make_active_player(slot, leader=slot == 1) for slot in range(1, player_count + 1))
    spawns = tuple((64.0 + (slot - 1) * 48.0, 160.0) for slot in range(1, player_count + 1))
    return make_runtime(players, make_stage(player_spawns=spawns))


def player_view(runtime: StageRuntime, slot: int) -> PlayerView:
    """Return the immutable view for one active test slot."""

    return next(player for player in runtime.snapshot().players if player.slot == slot)


def move_player_to_goal(runtime: StageRuntime, slot: int) -> None:
    """Place one player inside the production goal collider."""

    entity_id = runtime.player_entities[slot]
    _, _, goal = runtime.world.query(StageGoal, Transform)[0]
    transform = runtime.world.get_component(entity_id, Transform)
    transform.x, transform.y = goal.x, goal.y


def move_player_away_from_goal(runtime: StageRuntime, slot: int) -> None:
    """Place one player at a stable non-goal floor position."""

    transform = runtime.world.get_component(runtime.player_entities[slot], Transform)
    transform.x, transform.y = 64.0 + (slot - 1) * 48.0, 160.0


def defeat_player(runtime: StageRuntime, slot: int) -> StageFrame:
    """Defeat one player through the typed production damage queue."""

    entity_id = runtime.player_entities[slot]
    health = runtime.world.get_component(entity_id, Health)
    queue = runtime.world.resources["damage_queue"]
    if not isinstance(queue, list):
        raise TypeError("damage_queue must be a list")
    queue.append(DamageRecord(0, entity_id, health.maximum, 0.0, -220.0, True))
    return runtime.step(InputFrame.empty())


def step_count(runtime: StageRuntime, count: int) -> StageFrame:
    """Advance exactly ``count`` fixed steps and return the final frame."""

    if type(count) is not int or count <= 0:
        raise ValueError("step count must be a positive integer")
    frame_result = runtime.step(InputFrame.empty())
    for _ in range(count - 1):
        frame_result = runtime.step(InputFrame.empty())
    return frame_result


def make_session() -> GameSession:
    """Build a fresh solo session in its explicit introduction phase."""
    config = GameConfig()
    return GameSession.create(
        config,
        make_stage(),
        create_default_registry(config.content_dir),
        (make_active_player(1, leader=True),),
        seed=77,
    )


def enter_victory(session: GameSession) -> None:
    """Complete through one normal goal-gated production step."""
    player_id = session.runtime.player_entities[min(session.runtime.player_entities)]
    _, _, goal = session.runtime.world.query(StageGoal, Transform)[0]
    player = session.runtime.world.get_component(player_id, Transform)
    player.x, player.y = goal.x, goal.y
    session.step(InputFrame.empty())


def enter_defeat(session: GameSession) -> None:
    """Defeat through one normal typed damage and outcome step."""
    player_id = session.runtime.player_entities[min(session.runtime.player_entities)]
    health = session.runtime.world.get_component(player_id, Health)
    queue = session.runtime.world.resources["damage_queue"]
    if not isinstance(queue, list):
        raise TypeError("damage_queue must be a list")
    queue.append(DamageRecord(0, player_id, health.maximum, 0.0, -220.0, True))
    session.step(InputFrame.empty())
