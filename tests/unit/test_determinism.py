from __future__ import annotations

from hypothesis import given, strategies as st

from kirby_clone.input import InputState
from kirby_clone.level import LevelLoader
from kirby_clone.settings import GameConfig
from kirby_clone.simulation import Simulation


def _input_from_tuple(values: tuple[int, bool, bool]) -> InputState:
    move_x, jump_pressed, attack_pressed = values
    return InputState(
        move_x=move_x,
        jump_pressed=jump_pressed,
        jump_held=jump_pressed,
        attack_pressed=attack_pressed,
        pause_pressed=False,
        restart_pressed=False,
    )


@given(
    steps=st.lists(
        st.tuples(
            st.integers(min_value=-1, max_value=1),
            st.booleans(),
            st.booleans(),
        ),
        min_size=10,
        max_size=80,
    )
)
def test_same_seed_and_inputs_produce_same_hash(steps: list[tuple[int, bool, bool]]) -> None:
    config = GameConfig()
    level = LevelLoader().load_level(str(config.level_path))

    sim_a = Simulation(config=config, level=level, seed=2026)
    sim_b = Simulation(config=config, level=level, seed=2026)

    for step in steps:
        inp = _input_from_tuple(step)
        sim_a.step(inp)
        sim_b.step(inp)

    assert sim_a.world_state_hash() == sim_b.world_state_hash()
