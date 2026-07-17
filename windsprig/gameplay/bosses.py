"""Drive authored boss phases at the deterministic gameplay boundary."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from types import MappingProxyType
from typing import cast

from windsprig.content.models import BossAttackSpec, BossSpec, ParameterValue
from windsprig.core.ecs import World
from windsprig.core.events import GameEvent
from windsprig.core.rng import DeterministicRng
from windsprig.gameplay.components import Health


@dataclass(frozen=True, slots=True)
class BossState:
    """Canonical immutable state for one live boss director instance."""

    boss_id: str
    entity_id: int
    phase_index: int
    phase_id: str
    attack_index: int
    mode: str
    remaining_ms: int
    active_attack_id: str | None
    defeated: bool = False


@dataclass(frozen=True, slots=True)
class BossCommand:
    """One immutable authored attack request retained for the attack factory."""

    command: str
    attack_id: str
    parameters: tuple[tuple[str, ParameterValue], ...]

    def __post_init__(self) -> None:
        parameters = tuple(self.parameters)
        seen: set[str] = set()
        for pair in parameters:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError("boss command parameters must be key-value tuples")
            key, value = pair
            if type(key) is not str or not key:
                raise TypeError("boss command parameter keys must be non-empty strings")
            if type(value) not in {bool, int, float, str}:
                raise TypeError("boss command parameter values must be JSON scalars")
            if key in seen:
                raise ValueError(f"duplicate boss command parameter: {key}")
            seen.add(key)
        object.__setattr__(self, "parameters", tuple(sorted(parameters)))


@dataclass(frozen=True, slots=True)
class BossStep:
    """Pure director output for one fixed simulation step."""

    state: BossState
    commands: tuple[BossCommand, ...]
    events: tuple[GameEvent, ...]


def boss_command_sort_key(command: BossCommand) -> str:
    """Return a cross-type-safe canonical key for gameplay resource ordering."""

    return json.dumps(asdict(command), sort_keys=True, separators=(",", ":"))


def validate_boss_commands(value: object) -> tuple[BossCommand, ...]:
    """Validate exact command DTOs, deep parameters, and canonical ordering."""

    if type(value) is not tuple:
        raise TypeError("boss_commands must be a tuple of BossCommand values")
    raw_commands = cast(tuple[object, ...], value)
    commands: list[BossCommand] = []
    for member in raw_commands:
        if type(member) is not BossCommand:
            raise TypeError("boss_commands must be a tuple of BossCommand values")
        command = member
        if type(command.command) is not str:
            raise TypeError("BossCommand.command must be a string")
        if not command.command:
            raise ValueError("BossCommand.command must be non-empty")
        if type(command.attack_id) is not str:
            raise TypeError("BossCommand.attack_id must be a string")
        if not command.attack_id:
            raise ValueError("BossCommand.attack_id must be non-empty")

        raw_parameters = cast(object, command.parameters)
        if type(raw_parameters) is not tuple:
            raise TypeError("BossCommand.parameters must be a tuple")
        parameters = cast(tuple[object, ...], raw_parameters)
        validated_parameters: list[tuple[str, ParameterValue]] = []
        seen: set[str] = set()
        for raw_pair in parameters:
            if type(raw_pair) is not tuple or len(raw_pair) != 2:
                raise TypeError("BossCommand.parameters must contain key-value tuples")
            key, parameter = cast(tuple[object, object], raw_pair)
            if type(key) is not str:
                raise TypeError("BossCommand parameter keys must be strings")
            if not key:
                raise ValueError("BossCommand parameter keys must be non-empty")
            if key in seen:
                raise ValueError(f"BossCommand.parameters has duplicate key: {key}")
            if type(parameter) not in {bool, int, float, str}:
                raise TypeError(f"BossCommand.parameters.{key} must be a JSON scalar")
            if type(parameter) is float and not math.isfinite(parameter):
                raise ValueError(f"BossCommand.parameters.{key} must be finite")
            seen.add(key)
            validated_parameters.append((key, cast(ParameterValue, parameter)))
        canonical_parameters = tuple(sorted(validated_parameters))
        if tuple(validated_parameters) != canonical_parameters:
            raise ValueError("BossCommand.parameters must be sorted canonically")
        commands.append(command)

    validated = tuple(commands)
    if validated != tuple(sorted(validated, key=boss_command_sort_key)):
        raise ValueError("boss_commands must be sorted canonically")
    return validated


class BossDirector:
    """Apply deterministic phase thresholds and authored attack timing."""

    def __init__(self, specs: Mapping[str, BossSpec]) -> None:
        copied = dict(specs)
        if any(key != spec.boss_id for key, spec in copied.items()):
            raise ValueError("boss catalog keys must match BossSpec.boss_id")
        self.specs: Mapping[str, BossSpec] = MappingProxyType(copied)

    def start(self, boss_id: str, entity_id: int) -> BossState:
        """Create the independent phase-one ready state for ``entity_id``."""

        spec = self.specs[boss_id]
        return BossState(
            boss_id=boss_id,
            entity_id=entity_id,
            phase_index=0,
            phase_id=spec.phases[0].phase_id,
            attack_index=0,
            mode="ready",
            remaining_ms=0,
            active_attack_id=None,
        )

    def step(
        self,
        state: BossState,
        hp: int,
        dt_ms: int,
        rng: DeterministicRng,
    ) -> BossStep:
        """Advance at most one mode transition and consume RNG only after an attack."""

        if type(dt_ms) is not int:
            raise TypeError("dt_ms must be an integer")
        if dt_ms < 0:
            raise ValueError("dt_ms must be non-negative")
        if type(hp) is not int:
            raise TypeError("hp must be an integer")
        spec = self.specs[state.boss_id]
        self._validate_state(state, spec)

        if state.defeated:
            return BossStep(state, (), ())
        if hp <= 0:
            ended = replace(
                state,
                mode="defeated",
                remaining_ms=0,
                active_attack_id=None,
                defeated=True,
            )
            return BossStep(
                ended,
                (),
                (GameEvent("BossDefeated", {"boss_id": state.boss_id}),),
            )

        desired = self._desired_phase_index(spec, state.phase_index, hp)
        if desired > state.phase_index:
            phase_state = replace(
                state,
                phase_index=desired,
                phase_id=spec.phases[desired].phase_id,
                attack_index=0,
                mode="ready",
                remaining_ms=0,
                active_attack_id=None,
            )
            return BossStep(
                phase_state,
                (),
                (
                    GameEvent(
                        "BossPhaseChanged",
                        {
                            "boss_id": state.boss_id,
                            "phase_id": phase_state.phase_id,
                            "phase_index": desired + 1,
                        },
                    ),
                ),
            )

        phase = spec.phases[state.phase_index]
        attack = phase.attacks[state.attack_index % len(phase.attacks)]
        if state.mode == "ready":
            return self._begin_telegraph(state, attack)

        remaining = max(0, state.remaining_ms - dt_ms)
        if remaining > 0:
            return BossStep(replace(state, remaining_ms=remaining), (), ())
        if state.mode == "telegraph":
            command = BossCommand("execute", attack.attack_id, attack.parameters)
            active = replace(
                state,
                mode="active",
                remaining_ms=attack.active_ms,
            )
            return BossStep(active, (command,), ())
        if state.mode == "active":
            recovery = replace(
                state,
                mode="recovery",
                remaining_ms=attack.recovery_ms,
                attack_index=(state.attack_index + 1) % len(phase.attacks),
                active_attack_id=None,
            )
            # One draw marks the authored attack-cycle boundary without allowing
            # invalid, telegraph, active, or defeated calls to perturb replay state.
            rng.randint(0, 0xFFFFFFFF)
            return BossStep(recovery, (), ())
        return self._begin_telegraph(state, attack)

    @staticmethod
    def _desired_phase_index(
        spec: BossSpec,
        current_index: int,
        hp: int,
    ) -> int:
        ratio = max(0.0, hp / spec.max_hp)
        desired = current_index
        for index in range(current_index + 1, len(spec.phases)):
            if ratio <= spec.phases[index].enter_at_hp_ratio:
                desired = index
        return desired

    @staticmethod
    def _begin_telegraph(
        state: BossState,
        attack: BossAttackSpec,
    ) -> BossStep:
        telegraph = replace(
            state,
            mode="telegraph",
            remaining_ms=attack.telegraph_ms,
            active_attack_id=attack.attack_id,
        )
        event = GameEvent(
            "BossAttackTelegraphed",
            {
                "boss_id": state.boss_id,
                "phase_id": state.phase_id,
                "attack_id": attack.attack_id,
                "marker": attack.marker,
                "telegraph_ms": attack.telegraph_ms,
                "cue_id": attack.cue_id,
            },
        )
        return BossStep(telegraph, (), (event,))

    @staticmethod
    def _validate_state(state: BossState, spec: BossSpec) -> None:
        if not 0 <= state.phase_index < len(spec.phases):
            raise ValueError("boss phase_index is out of range")
        if state.phase_id != spec.phases[state.phase_index].phase_id:
            raise ValueError("boss phase_id does not match phase_index")
        if state.attack_index < 0:
            raise ValueError("boss attack_index must be non-negative")
        if state.mode not in {"ready", "telegraph", "active", "recovery", "defeated"}:
            raise ValueError(f"unknown boss mode: {state.mode}")
        if state.remaining_ms < 0:
            raise ValueError("boss remaining_ms must be non-negative")


class BossSystem:
    """Commit one director step to ECS state, events, and command resources."""

    def __init__(self, director: BossDirector) -> None:
        self._director = director

    def update(self, world: World, dt_ms: int) -> None:
        rows = world.query(BossState, Health)
        if len(rows) != 1:
            raise RuntimeError("boss stages must retain exactly one boss entity")
        entity_id, state, health = rows[0]
        if state.entity_id != entity_id:
            raise ValueError("BossState.entity_id must match its ECS owner")

        retained = validate_boss_commands(world.resources.get("boss_commands"))

        result = self._director.step(state, health.current, dt_ms, world.rng)
        result_commands = validate_boss_commands(result.commands)
        world.add_component(entity_id, result.state)
        commands = tuple(
            sorted(
                set(retained).union(result_commands),
                key=boss_command_sort_key,
            )
        )
        world.resources["boss_commands"] = commands
        for event in result.events:
            world.events.publish(event.topic, event.payload)


__all__ = [
    "BossCommand",
    "BossDirector",
    "BossState",
    "BossStep",
    "validate_boss_commands",
]
