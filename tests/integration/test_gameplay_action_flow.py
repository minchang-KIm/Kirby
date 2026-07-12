"""Complete runtime action flow for visible ability attacks."""

from __future__ import annotations

import pytest

from tests.helpers.gameplay import frame, make_runtime, make_session
from windsprig.gameplay.components import AbilityState, Collider, Transform
from windsprig.gameplay.session import SessionAction
from windsprig.input.commands import AbilityUseCommand


@pytest.mark.parametrize(
    ("ability_id", "command"),
    (
        ("bloomblade", AbilityUseCommand(1, pressed=True)),
        ("cinder", AbilityUseCommand(1, released=True)),
        ("galehook", AbilityUseCommand(1, pressed=True)),
        ("voltsong", AbilityUseCommand(1, pressed=True)),
        ("stoneheart", AbilityUseCommand(1, pressed=True)),
        ("tempest", AbilityUseCommand(1, pressed=True)),
    ),
)
def test_each_ability_materializes_visible_attack_and_ordered_events(
    ability_id: str,
    command: AbilityUseCommand,
) -> None:
    runtime = make_runtime()
    player = runtime.player_entities[1]
    ability = runtime.world.get_component(player, AbilityState)
    ability.current_id = ability_id
    if ability_id == "stoneheart":
        runtime.world.get_component(player, Transform).y = 80.0
        runtime.world.get_component(player, Collider).on_ground = False
    if ability_id == "tempest":
        ability.previous_id = "bloomblade"
        ability.meter = 100

    result = runtime.step(frame(1, command))

    assert len(result.view.attacks) == 1
    assert [event.topic for event in result.events][:2] == ["AttackSpawned", "AbilityUsed"]
    assert result.events[1].payload["ability_id"] == ability_id
    assert result.events[1].payload["attack_ids"] == (result.view.attacks[0].entity_id,)


def test_paused_session_freezes_live_attack_state_and_hash() -> None:
    session = make_session()
    player = session.runtime.player_entities[1]
    session.runtime.world.get_component(player, AbilityState).current_id = "cinder"
    session.dispatch(SessionAction.START)
    session.step(frame(1, AbilityUseCommand(1, released=True)))
    session.dispatch(SessionAction.PAUSE)
    before = session.runtime.snapshot()
    before_hash = session.runtime.world.world_hash()
    before_frame = session.runtime.world.frame_index
    before_input = session.runtime.world.frame_input

    paused = session.step(frame(1, AbilityUseCommand(1, released=True)))

    assert paused.stage == before
    assert session.runtime.world.world_hash() == before_hash
    assert session.runtime.world.frame_index == before_frame
    assert session.runtime.world.frame_input is before_input
