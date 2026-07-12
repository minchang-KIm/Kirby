"""Deterministic unit contract for the gameplay-owned boss director."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from windsprig.content.models import BossAttackSpec, BossPhaseSpec, BossSpec
from windsprig.core.ecs import World
from windsprig.core.rng import DeterministicRng
from windsprig.gameplay.bosses import (
    BossCommand,
    BossDirector,
    BossState,
    BossStep,
    BossSystem,
    validate_boss_commands,
)
from windsprig.gameplay.components import Health


def _boss() -> BossSpec:
    """Build a compact three-phase boss without filesystem dependencies."""

    return BossSpec(
        boss_id="test_boss",
        name_key="boss.test.name",
        max_hp=100,
        visual_id="boss.test",
        phases=(
            _phase("test.phase_1", 1.0, "vulnerable", "test.attack_1", 700),
            _phase("test.phase_2", 0.66, "armored", "test.attack_2", 800),
            _phase("test.phase_3", 0.33, "hidden", "test.attack_3", 900),
        ),
    )


def _phase(
    phase_id: str,
    ratio: float,
    vulnerability: str,
    attack_id: str,
    telegraph_ms: int,
) -> BossPhaseSpec:
    return BossPhaseSpec(
        phase_id=phase_id,
        enter_at_hp_ratio=ratio,
        vulnerability=vulnerability,  # type: ignore[arg-type]
        arena_rule=f"{phase_id}.arena",
        attacks=(
            BossAttackSpec(
                attack_id=attack_id,
                telegraph_ms=telegraph_ms,
                active_ms=400,
                recovery_ms=500,
                marker="ground",
                cue_id="sfx.test",
                parameters=(("count", 2), ("speed", 180)),
            ),
            BossAttackSpec(
                attack_id=f"{attack_id}.next",
                telegraph_ms=telegraph_ms + 50,
                active_ms=300,
                recovery_ms=450,
                marker="lane",
                cue_id="sfx.test.next",
                parameters=(("lanes", 3),),
            ),
        ),
    )


def _director() -> BossDirector:
    spec = _boss()
    return BossDirector({spec.boss_id: spec})


def test_complete_attack_cycle_telegraphs_executes_and_recovers_once() -> None:
    director = _director()
    rng = DeterministicRng(7)
    initial_rng = rng.state_hash()
    ready = director.start("test_boss", entity_id=41)

    telegraph = director.step(ready, hp=100, dt_ms=16, rng=rng)
    after_telegraph_rng = rng.state_hash()
    waiting = director.step(telegraph.state, hp=100, dt_ms=699, rng=rng)
    after_waiting_rng = rng.state_hash()
    active = director.step(waiting.state, hp=100, dt_ms=1, rng=rng)
    after_execute_rng = rng.state_hash()
    recovering = director.step(active.state, hp=100, dt_ms=400, rng=rng)
    next_telegraph = director.step(recovering.state, hp=100, dt_ms=500, rng=rng)

    assert ready.mode == "ready"
    assert [event.topic for event in telegraph.events] == ["BossAttackTelegraphed"]
    assert telegraph.events[0].payload == {
        "boss_id": "test_boss",
        "phase_id": "test.phase_1",
        "attack_id": "test.attack_1",
        "marker": "ground",
        "telegraph_ms": 700,
        "cue_id": "sfx.test",
    }
    assert waiting.state.remaining_ms == 1
    assert waiting.commands == waiting.events == ()
    assert active.commands == (
        BossCommand(
            command="execute",
            attack_id="test.attack_1",
            parameters=(("count", 2), ("speed", 180)),
        ),
    )
    assert active.events == ()
    assert recovering.state.mode == "recovery"
    assert recovering.state.active_attack_id is None
    assert recovering.commands == recovering.events == ()
    assert initial_rng == after_telegraph_rng == after_waiting_rng == after_execute_rng
    assert rng.state_hash() != initial_rng
    assert [event.topic for event in next_telegraph.events] == ["BossAttackTelegraphed"]
    assert next_telegraph.events[0].payload["attack_id"] == "test.attack_1.next"
    assert next_telegraph.state.attack_index == 1


@pytest.mark.parametrize("mode", ["telegraph", "active"])
def test_phase_jump_cancels_current_attack_and_never_reverts(mode: str) -> None:
    director = _director()
    rng = DeterministicRng(11)
    phase_one = director.step(director.start("test_boss", 9), hp=100, dt_ms=0, rng=rng).state
    if mode == "active":
        phase_one = director.step(phase_one, hp=100, dt_ms=700, rng=rng).state

    changed = director.step(phase_one, hp=30, dt_ms=16, rng=rng)
    healed = director.step(changed.state, hp=100, dt_ms=0, rng=rng)

    assert changed.commands == ()
    assert [event.topic for event in changed.events] == ["BossPhaseChanged"]
    assert changed.events[0].payload == {
        "boss_id": "test_boss",
        "phase_id": "test.phase_3",
        "phase_index": 3,
    }
    assert changed.state.phase_index == 2
    assert changed.state.mode == "ready"
    assert changed.state.remaining_ms == 0
    assert changed.state.active_attack_id is None
    assert healed.state.phase_index == 2
    assert all(event.topic != "BossPhaseChanged" for event in healed.events)


def test_defeat_is_idempotent_and_does_not_advance_rng() -> None:
    director = _director()
    rng = DeterministicRng(13)
    started = director.start("test_boss", 4)
    before = rng.state_hash()

    defeated = director.step(started, hp=0, dt_ms=9999, rng=rng)
    repeated = director.step(defeated.state, hp=0, dt_ms=9999, rng=rng)

    assert [event.topic for event in defeated.events] == ["BossDefeated"]
    assert defeated.events[0].payload == {"boss_id": "test_boss"}
    assert defeated.state.defeated is True
    assert defeated.state.mode == "defeated"
    assert defeated.state.active_attack_id is None
    assert repeated.state is defeated.state
    assert repeated.commands == repeated.events == ()
    assert rng.state_hash() == before


def test_large_and_zero_timers_make_at_most_one_transition_per_step() -> None:
    director = _director()
    rng = DeterministicRng(17)
    ready = director.start("test_boss", 2)

    telegraph = director.step(ready, hp=100, dt_ms=100_000, rng=rng)
    unchanged = director.step(telegraph.state, hp=100, dt_ms=0, rng=rng)
    active = director.step(unchanged.state, hp=100, dt_ms=100_000, rng=rng)

    assert telegraph.state.mode == "telegraph"
    assert telegraph.state.remaining_ms == 700
    assert unchanged.state == telegraph.state
    assert unchanged.commands == unchanged.events == ()
    assert active.state.mode == "active"
    assert len(active.commands) == 1


def test_invalid_negative_delta_does_not_mutate_state_or_rng() -> None:
    director = _director()
    rng = DeterministicRng(19)
    state = director.start("test_boss", 7)
    before = rng.state_hash()

    with pytest.raises(ValueError, match="dt_ms must be non-negative"):
        director.step(state, hp=100, dt_ms=-1, rng=rng)

    assert rng.state_hash() == before


@pytest.mark.parametrize("invalid", ([], (object(),)))
def test_boss_system_rejects_invalid_retained_commands_before_mutation(
    invalid: object,
) -> None:
    director = _director()
    world = World(seed=29)
    entity_id = world.create_entity()
    initial = director.start("test_boss", entity_id)
    world.add_component(entity_id, initial)
    world.add_component(entity_id, Health(100, 100))
    world.resources["boss_commands"] = invalid
    before_rng = world.rng.state_hash()

    with pytest.raises(TypeError, match="boss_commands"):
        BossSystem(director).update(world, 16)

    assert world.get_component(entity_id, BossState) is initial
    assert world.resources["boss_commands"] is invalid
    assert world.rng.state_hash() == before_rng
    assert world.events.peek() == []


@pytest.mark.parametrize(
    ("field_name", "invalid", "error", "match"),
    (
        ("command", 7, TypeError, "BossCommand.command"),
        ("attack_id", 7, TypeError, "BossCommand.attack_id"),
        ("parameters", [], TypeError, "BossCommand.parameters"),
        ("parameters", (object(),), TypeError, "key-value tuples"),
        ("parameters", ((7, 1),), TypeError, "parameter keys"),
        ("parameters", (("", 1),), ValueError, "parameter keys"),
        (
            "parameters",
            (("same", 1), ("same", 2)),
            ValueError,
            "duplicate key",
        ),
        ("parameters", (("bad", object()),), TypeError, "JSON scalar"),
        (
            "parameters",
            (("z", 1), ("a", 2)),
            ValueError,
            "sorted canonically",
        ),
    ),
)
def test_boss_command_deep_field_validation_is_strict(
    field_name: str,
    invalid: object,
    error: type[Exception],
    match: str,
) -> None:
    command = BossCommand(
        "execute",
        "test.attack",
        (("count", 2), ("speed", 180)),
    )
    object.__setattr__(command, field_name, invalid)

    with pytest.raises(error, match=match):
        validate_boss_commands((command,))


def test_states_and_payloads_are_independent_and_immutable() -> None:
    director = _director()
    first = director.start("test_boss", 1)
    second = director.start("test_boss", 2)
    stepped = director.step(first, hp=100, dt_ms=0, rng=DeterministicRng(23))

    assert first.entity_id == 1
    assert second.entity_id == 2
    assert second.mode == "ready"
    assert stepped.state.entity_id == 1
    with pytest.raises(FrozenInstanceError):
        stepped.state.mode = "active"  # type: ignore[misc]
    with pytest.raises(TypeError):
        stepped.events[0].payload["attack_id"] = "mutated"  # type: ignore[index]


def test_public_director_dtos_keep_the_exact_frozen_slotted_contract() -> None:
    assert tuple(field.name for field in fields(BossState)) == (
        "boss_id",
        "entity_id",
        "phase_index",
        "phase_id",
        "attack_index",
        "mode",
        "remaining_ms",
        "active_attack_id",
        "defeated",
    )
    assert tuple(field.name for field in fields(BossCommand)) == (
        "command",
        "attack_id",
        "parameters",
    )
    assert tuple(field.name for field in fields(BossStep)) == (
        "state",
        "commands",
        "events",
    )
    assert not hasattr(_director().start("test_boss", 1), "__dict__")
