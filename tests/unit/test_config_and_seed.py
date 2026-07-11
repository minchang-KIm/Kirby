from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from types import SimpleNamespace

import windsprig.screens.foundation as foundation_module
from windsprig.config import GameConfig
from windsprig.core.rng import derive_stage_seed
from windsprig.input.commands import ConfirmCommand, InputFrame
from windsprig.input.roster import ActivePlayer, ActiveRoster, DeviceRef
from windsprig.screens.base import ScreenTransition
from windsprig.screens.foundation import FoundationScreen


def test_release_runtime_defaults_are_bounded() -> None:
    config = GameConfig()
    assert config.resolution == (1280, 720)
    assert config.fixed_dt_ms == 16
    assert config.max_catch_up_steps == 5
    assert config.max_frame_elapsed_ms == 250
    assert config.fixed_dt_seconds == 0.016


def test_stage_seed_has_a_locked_digest_value() -> None:
    assert derive_stage_seed(1337, "world_1_stage_1") == 17674047013880078487
    assert derive_stage_seed(1337, "world_1_stage_2") == 16524485793878410478


def test_stage_seed_is_independent_of_python_hash_seed() -> None:
    code = (
        "from windsprig.core.rng import derive_stage_seed; "
        "print(derive_stage_seed(77, 'foundation_probe'))"
    )
    values: list[str] = []
    for hash_seed in ("1", "999"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = hash_seed
        values.append(subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip())
    assert values == ["17908035134853811437", "17908035134853811437"]


def test_selected_stage_start_and_paused_restart_share_derived_seed(monkeypatch) -> None:
    config = GameConfig()
    stage_id = "world_1_stage_1"
    stage = SimpleNamespace(stage_id=stage_id)
    node = SimpleNamespace(stage_id=stage_id)
    created_seeds: list[int] = []
    created_slots: list[tuple[int, ...]] = []

    class RuntimeProbe:
        def __init__(
            self,
            *,
            config: GameConfig,
            stage: object,
            ability_registry: object,
            active_players: Sequence[ActivePlayer],
            seed: int,
        ) -> None:
            del config, ability_registry
            self.stage = stage
            created_seeds.append(seed)
            created_slots.append(tuple(player.slot for player in active_players))

    screen = FoundationScreen.__new__(FoundationScreen)
    screen.config = config
    screen.catalog = SimpleNamespace(stages={stage_id: stage})
    screen.ability_registry = object()
    screen.roster = ActiveRoster()
    screen.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    screen.selected_node_index = 0
    screen.screen_id = "world_map"
    screen.runtime = None
    monkeypatch.setattr(screen, "_visible_nodes", lambda: [node])
    monkeypatch.setattr(foundation_module, "StageRuntime", RuntimeProbe)

    assert screen._start_selected_stage() is True
    screen.screen_id = "paused"
    transition = screen.fixed_update(
        config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [ConfirmCommand(player_slot=1)]}),
    )

    expected_seed = derive_stage_seed(config.replay_seed, stage_id)
    assert transition == ScreenTransition("playing")
    assert created_seeds == [expected_seed, expected_seed]
    assert created_slots == [(1,), (1,)]
