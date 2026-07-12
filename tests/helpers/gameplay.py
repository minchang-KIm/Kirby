"""Deterministic builders for production gameplay tests."""

from __future__ import annotations

from windsprig.config import GameConfig
from windsprig.content.loader import CheckpointSpec, EnemySpawn, MoteSpec, StageSpec
from windsprig.core.events import GameEvent
from windsprig.gameplay.abilities import AbilityContext, create_default_registry
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.session import GameSession
from windsprig.gameplay.snapshot import StageOutcome
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
    checkpoints: tuple[CheckpointSpec, ...] = (),
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
        interactions=(),
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
    """Drive the session through the same typed outcome seam as a normal step."""
    session.runtime.world.resources["stage_outcome"] = StageOutcome.COMPLETED
    session._synchronize_outcome()


def enter_defeat(session: GameSession) -> None:
    """Drive the session into defeat through its typed outcome seam."""
    session.runtime.world.resources["stage_outcome"] = StageOutcome.FAILED
    session._synchronize_outcome()
