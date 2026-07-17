"""Runtime-level capture choice, snapshot, and reset integration."""

from __future__ import annotations

from tests.helpers.gameplay import frame, make_active_player, make_runtime, make_stage
from windsprig.content.loader import AbilityId, EnemySpawn
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    CapturedBy,
    CaptureState,
    Collider,
    ControlIntent,
    EchoPickup,
    EnemyAI,
    Transform,
)
from windsprig.gameplay.runtime import StageRuntime
from windsprig.input.commands import (
    AbilityUseCommand,
    DrawReleaseCommand,
    DrawStartCommand,
    DropAbilityCommand,
    InputFrame,
)


def _runtime_with_enemy(ability_id: AbilityId | None = "cinder") -> tuple[StageRuntime, int, int]:
    stage = make_stage(
        enemy_spawns=(
            EnemySpawn(
                x=82.0,
                y=160.0,
                kind="grunt",
                ability_id=ability_id,
                patrol_left=70.0,
                patrol_right=100.0,
            ),
        )
    )
    runtime = make_runtime(stage=stage)
    enemy = runtime.world.query(EnemyAI)[0][0]
    return runtime, runtime.player_entities[1], enemy


def test_runtime_capture_snapshot_and_simultaneous_harmonize_are_canonical() -> None:
    runtime, player, enemy = _runtime_with_enemy()

    captured = runtime.step(frame(1, DrawStartCommand(1)))

    player_view = captured.view.players[0]
    enemy_view = next(view for view in captured.view.enemies if view.entity_id == enemy)
    assert player_view.captured_ability_id == "cinder"
    assert player_view.captured_visual_id == "grunt"
    assert enemy_view.captured_by == player
    assert [event.topic for event in captured.events] == ["EnemyCaptured"]

    result = runtime.step(
        frame(
            1,
            AbilityUseCommand(1, True),
            DrawReleaseCommand(1),
        )
    )

    assert [event.topic for event in result.events] == ["AbilityEquipped"]
    assert runtime.world.get_component(player, AbilityState).current_id == "cinder"
    assert enemy not in runtime.world.alive_entities
    assert runtime.world.resources["attack_requests"] == []
    assert result.view.attacks == ()


def test_launch_attack_uses_real_entity_id_and_later_empty_release_cannot_reuse_it() -> None:
    runtime, _, enemy = _runtime_with_enemy(None)
    runtime.step(frame(1, DrawStartCommand(1)))

    launched = runtime.step(frame(1, DrawReleaseCommand(1)))

    assert enemy not in runtime.world.alive_entities
    assert [event.topic for event in launched.events] == ["AttackSpawned", "EnemyLaunched"]
    assert len(launched.view.attacks) == 1
    assert launched.events[1].payload["attack_id"] == launched.view.attacks[0].entity_id
    assert runtime.world.resources["attack_requests"] == []

    empty = runtime.step(frame(1, DrawReleaseCommand(1)))

    assert [event.topic for event in empty.events] == ["CaptureReleased"]
    assert runtime.world.resources["attack_requests"] == []


def test_echo_pickup_snapshot_is_sorted_and_reset_matches_fresh_hash() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    ability = runtime.world.get_component(player, AbilityState)
    capture = runtime.world.get_component(player, CaptureState)
    ability.current_id = "galehook"
    ability.charge_ms = 77
    ability.meter = 43
    capture.phase = "drawing"
    capture.draw_elapsed_ms = 32
    second = runtime.factory.spawn_echo_pickup("stoneheart", 90.0, 80.0)
    first = runtime.factory.spawn_echo_pickup("cinder", 70.0, 60.0)

    snapshot = runtime.snapshot()

    assert [(view.entity_id, view.ability_id) for view in snapshot.echo_pickups] == [
        (second, "stoneheart"),
        (first, "cinder"),
    ]
    assert (snapshot.players[0].ability_charge_ms, snapshot.players[0].ability_meter) == (77, 43)
    mutated_hash = runtime.world.world_hash()

    reset = runtime.reset_stage()
    fresh = make_runtime()

    assert mutated_hash != fresh.world.world_hash()
    assert runtime.world.world_hash() == fresh.world.world_hash()
    assert reset == fresh.snapshot()
    assert runtime.world.query(EchoPickup, Transform) == []
    assert runtime.world.get_component(runtime.player_entities[1], CaptureState) == CaptureState()
    assert runtime.world.get_component(runtime.player_entities[1], AbilityState) == AbilityState()


def test_runtime_drop_remains_visible_for_one_frame_then_is_recoverable() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    ability = runtime.world.get_component(player, AbilityState)
    ability.current_id = "galehook"

    dropped = runtime.step(frame(1, DropAbilityCommand(1, True)))

    assert ability.current_id == "none"
    assert len(dropped.view.echo_pickups) == 1
    assert dropped.view.echo_pickups[0].ability_id == "galehook"
    assert [event.topic for event in dropped.events] == ["AbilityDropped"]

    recovered = runtime.step(InputFrame.empty())

    assert ability.current_id == "galehook"
    assert recovered.view.echo_pickups == ()
    assert [event.topic for event in recovered.events] == ["AbilityEquipped"]


def test_roster_removal_releases_capture_before_paused_snapshot() -> None:
    stage = make_stage(
        enemy_spawns=(
            EnemySpawn(
                x=82.0,
                y=160.0,
                kind="grunt",
                ability_id="cinder",
                patrol_left=70.0,
                patrol_right=100.0,
            ),
        )
    )
    first = make_active_player(1, leader=True)
    second = make_active_player(2)
    runtime = make_runtime(stage=stage, players=(first, second))
    owner = runtime.player_entities[1]
    enemy = runtime.world.query(EnemyAI)[0][0]
    runtime.step(frame(1, DrawStartCommand(1)))
    assert runtime.world.get_component(enemy, CapturedBy) == CapturedBy(owner)

    runtime.sync_active_players((second,))
    snapshot = runtime.snapshot()

    assert owner not in runtime.world.alive_entities
    assert not runtime.world.has_component(enemy, CapturedBy)
    assert runtime.world.get_component(enemy, Collider).solid is True
    assert next(view for view in snapshot.enemies if view.entity_id == enemy).captured_by is None


def test_idle_release_does_not_truncate_runtime_hurt_window() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    state = runtime.world.get_component(player, ActorState)
    state.name = "Hurt"
    state.timer_ms = 100

    runtime.step(frame(1, DrawReleaseCommand(1)))

    assert (state.name, state.timer_ms) == ("Hurt", 84)


def test_empty_input_clears_transient_capture_and_consumption_edges() -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    intent = runtime.world.get_component(player, ControlIntent)
    intent.draw_started = True
    intent.draw_released = True
    intent.ability_pressed = True
    intent.ability_consumed = True

    runtime.step(InputFrame.empty())

    assert intent.draw_started is False
    assert intent.draw_released is False
    assert intent.ability_pressed is False
    assert intent.ability_consumed is False
