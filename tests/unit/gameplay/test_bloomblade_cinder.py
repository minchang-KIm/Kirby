"""Exact contracts for the first two behavior-specific ability families."""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

import windsprig.gameplay.abilities as ability_types
from tests.helpers.gameplay import ability_context
from windsprig.config import GameConfig
from windsprig.core.ecs import World
from windsprig.gameplay.abilities import (
    AbilityContext,
    AbilityExecution,
    BloombladeStrategy,
    CinderStrategy,
    create_default_registry,
)
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    AttackRequest,
    Collider,
    ControlIntent,
    Facing,
    Health,
    Team,
    Transform,
)
from windsprig.gameplay.systems import AbilitySystem


def _add_player(
    world: World,
    *,
    ability_id: str,
    x: float = 100.0,
    facing: int = 1,
    actor_state: str = "Idle",
    dead: bool = False,
    cooldown_ms: int = 0,
) -> int:
    entity_id = world.create_entity()
    for component in (
        Team("player"),
        Transform(x, 50.0),
        Facing(facing),
        Collider(28, 28, on_ground=True),
        Health(0 if dead else 10, 10, dead=dead),
        ControlIntent(),
        AbilityState(current_id=ability_id, cooldown_remaining_ms=cooldown_ms),
        ActorState(actor_state),
    ):
        world.add_component(entity_id, component)
    return entity_id


def _ability_world() -> World:
    world = World()
    world.resources["ability_registry"] = create_default_registry(GameConfig().content_dir)
    world.resources["attack_requests"] = []
    return world


def _request(owner: int) -> AttackRequest:
    return AttackRequest(
        owner_entity_id=owner,
        team="player",
        ability_id="none",
        attack_kind="existing",
        visual_id="existing",
        x=0.0,
        y=0.0,
        width=1,
        height=1,
        vx=0.0,
        vy=0.0,
        damage=1,
        knockback_x=0.0,
        knockback_y=0.0,
        ttl_ms=1,
    )


def test_ability_boundary_values_are_frozen_slotted_and_exact() -> None:
    assert tuple(field.name for field in fields(AbilityContext)) == (
        "actor_id",
        "frame_index",
        "x",
        "y",
        "facing",
        "on_ground",
        "charge_ms",
        "combo_step",
        "meter",
    )
    assert tuple(field.name for field in fields(AbilityExecution)) == (
        "attacks",
        "cooldown_ms",
        "next_combo_step",
        "combo_window_ms",
        "armor_ms",
        "meter_cost",
        "restore_previous",
    )
    execution = AbilityExecution((), cooldown_ms=0, next_combo_step=0)
    context = ability_context()
    assert execution == AbilityExecution(
        attacks=(),
        cooldown_ms=0,
        next_combo_step=0,
        combo_window_ms=0,
        armor_ms=0,
        meter_cost=0,
        restore_previous=False,
    )
    with pytest.raises(FrozenInstanceError):
        execution.cooldown_ms = 9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        context.charge_ms = 9  # type: ignore[misc]
    assert not hasattr(execution, "__dict__")
    assert not hasattr(context, "__dict__")


def test_bloomblade_is_the_exact_three_press_melee_arc_combo() -> None:
    strategy = BloombladeStrategy()
    executions: list[AbilityExecution] = []
    combo_step = 0
    for _ in range(3):
        execution = strategy.activate(ability_context(combo_step=combo_step))
        executions.append(execution)
        combo_step = execution.next_combo_step

    assert tuple(
        (
            execution.attacks[0].attack_kind,
            execution.attacks[0].x,
            execution.attacks[0].y,
            execution.attacks[0].width,
            execution.attacks[0].height,
            execution.attacks[0].damage,
            execution.attacks[0].ttl_ms,
            execution.attacks[0].cuts_projectiles,
            execution.cooldown_ms,
            execution.next_combo_step,
            execution.combo_window_ms,
        )
        for execution in executions
    ) == (
        ("melee_arc", 128.0, 52.0, 38, 30, 2, 80, True, 120, 1, 260),
        ("melee_arc", 128.0, 52.0, 38, 30, 2, 80, True, 120, 2, 260),
        ("melee_arc", 128.0, 52.0, 38, 30, 4, 80, True, 260, 0, 260),
    )
    assert all(execution.attacks[0].ability_id == "bloomblade" for execution in executions)
    assert BloombladeStrategy().activate(ability_context(facing=-1)).attacks[0].x == 72.0


def test_cinder_tap_and_clamped_max_charge_use_the_exact_ember_formula() -> None:
    strategy = CinderStrategy()
    tap = strategy.activate(ability_context(charge_ms=0))
    charged = strategy.activate(ability_context(charge_ms=640))
    overcharged = strategy.activate(ability_context(charge_ms=50_000))

    assert tap.attacks == (
        AttackRequest(
            owner_entity_id=1,
            team="player",
            ability_id="cinder",
            attack_kind="charged_ember",
            visual_id="cinder_ember",
            x=120.0,
            y=58.0,
            width=18,
            height=14,
            vx=360.0,
            vy=-20.0,
            damage=2,
            knockback_x=220.0,
            knockback_y=-100.0,
            ttl_ms=900,
            pierce=0,
            interaction_kind="spawn_burn_zone",
        ),
    )
    assert charged.attacks == overcharged.attacks == (
        AttackRequest(
            owner_entity_id=1,
            team="player",
            ability_id="cinder",
            attack_kind="charged_ember",
            visual_id="cinder_ember_charged",
            x=120.0,
            y=58.0,
            width=32,
            height=24,
            vx=520.0,
            vy=-20.0,
            damage=5,
            knockback_x=220.0,
            knockback_y=-100.0,
            ttl_ms=900,
            pierce=0,
            interaction_kind="spawn_burn_zone",
        ),
    )
    assert (tap.cooldown_ms, charged.cooldown_ms) == (320, 320)


def test_registry_uses_six_metadata_only_rows_and_none_is_the_only_empty_sentinel() -> None:
    content_path = Path("windsprig/content/abilities.json")
    payload = json.loads(content_path.read_text(encoding="utf-8"))
    expected_ids = {
        "bloomblade",
        "cinder",
        "voltsong",
        "galehook",
        "stoneheart",
        "tempest",
    }
    assert set(payload) == {"abilities"}
    assert set(payload["abilities"]) == expected_ids
    assert all(
        set(metadata) == {"strategy", "icon_id", "palette_token", "enemy_source_tag"}
        for metadata in payload["abilities"].values()
    )
    registry = create_default_registry(GameConfig().content_dir)
    context = ability_context()
    assert registry.get("bloomblade").activate(context).attacks
    assert registry.get("cinder").activate(context).attacks
    assert registry.get("none").activate(context).attacks == ()
    assert registry.get("not-public").activate(context).attacks == ()
    assert not hasattr(ability_types, "AttackShape")
    assert not hasattr(ability_types, "DataDrivenAbilityStrategy")


_BLOOMBLADE_METADATA = """
    "bloomblade": {
      "strategy": "bloomblade",
      "icon_id": "ability.bloomblade",
      "palette_token": "bloomblade",
      "enemy_source_tag": "bloomblade"
    }
"""
_OTHER_ABILITY_METADATA = """
    "cinder": {
      "strategy": "cinder",
      "icon_id": "ability.cinder",
      "palette_token": "cinder",
      "enemy_source_tag": "cinder"
    },
    "voltsong": {
      "strategy": "voltsong",
      "icon_id": "ability.voltsong",
      "palette_token": "voltsong",
      "enemy_source_tag": "voltsong"
    },
    "galehook": {
      "strategy": "galehook",
      "icon_id": "ability.galehook",
      "palette_token": "galehook",
      "enemy_source_tag": "galehook"
    },
    "stoneheart": {
      "strategy": "stoneheart",
      "icon_id": "ability.stoneheart",
      "palette_token": "stoneheart",
      "enemy_source_tag": "stoneheart"
    },
    "tempest": {
      "strategy": "tempest",
      "icon_id": "ability.tempest",
      "palette_token": "tempest",
      "enemy_source_tag": "tempest"
    }
"""


def _metadata_document(bloomblade_member: str = _BLOOMBLADE_METADATA) -> str:
    return f'{{"abilities": {{{bloomblade_member}, {_OTHER_ABILITY_METADATA}}}}}'


@pytest.mark.parametrize(
    ("source", "duplicate_path"),
    [
        (
            f'{{"abilities": {{{_BLOOMBLADE_METADATA}, {_OTHER_ABILITY_METADATA}}}, '
            f'"abilities": {{{_BLOOMBLADE_METADATA}, {_OTHER_ABILITY_METADATA}}}}}',
            "abilities",
        ),
        (
            _metadata_document(f"{_BLOOMBLADE_METADATA}, {_BLOOMBLADE_METADATA}"),
            "abilities.bloomblade",
        ),
        (
            _metadata_document(
                """
                "bloomblade": {
                  "strategy": "bloomblade",
                  "strategy": "bloomblade",
                  "icon_id": "ability.bloomblade",
                  "palette_token": "bloomblade",
                  "enemy_source_tag": "bloomblade"
                }
                """
            ),
            "abilities.bloomblade.strategy",
        ),
    ],
)
def test_registry_rejects_duplicate_json_members_at_every_metadata_level(
    tmp_path: Path,
    source: str,
    duplicate_path: str,
) -> None:
    metadata_path = tmp_path / "abilities.json"
    metadata_path.write_text(source, encoding="utf-8")
    registry = create_default_registry(GameConfig().content_dir)

    with pytest.raises(
        ValueError,
        match=rf"^duplicate ability metadata member: {re.escape(duplicate_path)}$",
    ):
        registry.validate_metadata(metadata_path)


def test_bloomblade_system_cycles_combo_and_expiry_restarts_at_step_one() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="bloomblade")
    intent = world.get_component(player, ControlIntent)
    ability = world.get_component(player, AbilityState)
    system = AbilitySystem()

    intent.ability_pressed = True
    system.update(world, 16)
    for _ in range(2):
        for _ in range(7):
            system.update(world, 16)
        intent.ability_pressed = True
        system.update(world, 16)

    requests = world.resources["attack_requests"]
    assert isinstance(requests, list)
    assert [request.damage for request in requests] == [2, 2, 4]
    assert (ability.combo_step, ability.combo_window_remaining_ms) == (0, 260)

    for _ in range(17):
        system.update(world, 16)
    assert (ability.cooldown_remaining_ms, ability.combo_step, ability.combo_window_remaining_ms) == (0, 0, 0)
    intent.ability_pressed = True
    system.update(world, 16)
    assert [request.damage for request in requests] == [2, 2, 4, 2]


def test_bloomblade_ignores_charge_and_release_phases() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="bloomblade")
    intent = world.get_component(player, ControlIntent)
    intent.ability_held = True
    intent.ability_released = True

    AbilitySystem().update(world, 16)

    assert world.resources["attack_requests"] == []
    assert world.get_component(player, AbilityState).charge_ms == 0
    assert world.get_component(player, ActorState).name == "Idle"


def test_cinder_charges_only_while_held_and_fires_once_on_release() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="cinder", facing=-1)
    intent = world.get_component(player, ControlIntent)
    ability = world.get_component(player, AbilityState)
    system = AbilitySystem()

    intent.ability_pressed = True
    intent.ability_held = True
    for _ in range(40):
        system.update(world, 16)
    system.update(world, 16)
    assert ability.charge_ms == 640
    assert world.resources["attack_requests"] == []

    intent.ability_held = False
    intent.ability_released = True
    system.update(world, 16)
    request = world.resources["attack_requests"][0]  # type: ignore[index]
    assert (request.damage, request.width, request.height, request.vx, request.x) == (5, 32, 24, -520.0, 80.0)
    assert (ability.charge_ms, ability.cooldown_remaining_ms) == (0, 320)

    for _ in range(21):
        system.update(world, 16)
    assert len(world.resources["attack_requests"]) == 1  # type: ignore[arg-type]


def test_cinder_tap_release_is_valid_and_press_alone_never_fires() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="cinder")
    intent = world.get_component(player, ControlIntent)
    system = AbilitySystem()

    intent.ability_pressed = True
    system.update(world, 16)
    assert world.resources["attack_requests"] == []

    intent.ability_released = True
    system.update(world, 16)
    requests = world.resources["attack_requests"]
    assert isinstance(requests, list)
    assert [(request.damage, request.width, request.height) for request in requests] == [(2, 18, 14)]


def test_harmonize_consumption_suppresses_activation_without_overwriting_draw() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="bloomblade", actor_state="Draw")
    intent = world.get_component(player, ControlIntent)
    intent.ability_pressed = True
    intent.ability_held = True
    intent.ability_consumed = True

    AbilitySystem().update(world, 16)

    assert world.resources["attack_requests"] == []
    assert world.get_component(player, ActorState).name == "Draw"
    assert world.get_component(player, AbilityState) == AbilityState(current_id="bloomblade")


def test_consumed_cinder_release_clears_charge_without_firing() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="cinder", actor_state="Draw")
    intent = world.get_component(player, ControlIntent)
    intent.ability_released = True
    intent.ability_consumed = True
    ability = world.get_component(player, AbilityState)
    ability.charge_ms = 240

    AbilitySystem().update(world, 16)

    assert world.resources["attack_requests"] == []
    assert ability.charge_ms == 0
    assert world.get_component(player, ActorState).name == "Draw"


@pytest.mark.parametrize("actor_state", ["Guard", "Dodge", "Hurt", "Dead"])
def test_cooldown_dead_and_illegal_actor_states_refuse_activation(actor_state: str) -> None:
    world = _ability_world()
    player = _add_player(
        world,
        ability_id="bloomblade",
        actor_state=actor_state,
        dead=actor_state == "Dead",
        cooldown_ms=32 if actor_state == "Guard" else 0,
    )
    intent = world.get_component(player, ControlIntent)
    intent.ability_pressed = True

    AbilitySystem().update(world, 16)

    assert world.resources["attack_requests"] == []
    assert world.get_component(player, ActorState).name == actor_state


def test_cooldown_refuses_press_without_replaying_it_after_expiry() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="bloomblade", cooldown_ms=32)
    intent = world.get_component(player, ControlIntent)
    intent.ability_pressed = True
    system = AbilitySystem()

    system.update(world, 16)
    system.update(world, 16)

    assert world.resources["attack_requests"] == []
    assert world.get_component(player, AbilityState).cooldown_remaining_ms == 0
    assert world.get_component(player, ActorState).name == "Idle"

    intent.ability_pressed = True
    system.update(world, 16)
    assert len(world.resources["attack_requests"]) == 1  # type: ignore[arg-type]


def test_draw_refuses_attack_when_harmonize_did_not_consume_the_press() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="bloomblade", actor_state="Draw")
    world.get_component(player, ControlIntent).ability_pressed = True

    AbilitySystem().update(world, 16)

    assert world.resources["attack_requests"] == []
    assert world.get_component(player, ActorState).name == "Draw"


def test_attack_queue_keeps_existing_request_then_player_entity_order() -> None:
    world = _ability_world()
    first = _add_player(world, ability_id="bloomblade", x=100.0)
    second = _add_player(world, ability_id="bloomblade", x=200.0)
    world.resources["attack_requests"] = [_request(99)]
    world.get_component(first, ControlIntent).ability_pressed = True
    world.get_component(second, ControlIntent).ability_pressed = True

    AbilitySystem().update(world, 16)

    requests = world.resources["attack_requests"]
    assert isinstance(requests, list)
    assert [request.owner_entity_id for request in requests] == [99, first, second]
    assert world.events.peek() == []
    assert "projectile_requests" not in world.resources


def test_fixed_step_timers_clamp_at_zero_and_attack_recovers_to_resting_state() -> None:
    world = _ability_world()
    player = _add_player(world, ability_id="bloomblade", actor_state="Attack", cooldown_ms=5)
    ability = world.get_component(player, AbilityState)
    ability.combo_step = 2
    ability.combo_window_remaining_ms = 5
    ability.armor_remaining_ms = 5

    AbilitySystem().update(world, 16)

    assert (
        ability.cooldown_remaining_ms,
        ability.combo_step,
        ability.combo_window_remaining_ms,
        ability.armor_remaining_ms,
    ) == (0, 0, 0, 0)
    assert world.get_component(player, ActorState).name == "Idle"
