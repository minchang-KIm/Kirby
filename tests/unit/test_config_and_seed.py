from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from types import SimpleNamespace

import windsprig.app as app_module
from windsprig.app import GameApp
from windsprig.config import GameConfig
from windsprig.core.rng import derive_stage_seed
from windsprig.input.roster import ActivePlayer, ActiveRoster, DeviceRef


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


def test_selected_stage_start_and_restart_share_derived_seed(monkeypatch) -> None:
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

    restart_event = SimpleNamespace(type=2, key=5)
    quit_event = SimpleNamespace(type=1)
    fake_pygame = SimpleNamespace(
        QUIT=1,
        KEYDOWN=2,
        K_ESCAPE=3,
        K_RETURN=4,
        K_r=5,
        init=lambda: None,
        quit=lambda: None,
        display=SimpleNamespace(
            set_mode=lambda _resolution: object(),
            set_caption=lambda _caption: None,
            flip=lambda: None,
        ),
        time=SimpleNamespace(Clock=lambda: SimpleNamespace(tick=lambda _fps: 0)),
        event=SimpleNamespace(get=lambda: [restart_event, quit_event]),
        key=SimpleNamespace(get_pressed=lambda: object()),
        font=SimpleNamespace(SysFont=lambda *_args: object()),
    )
    input_mux = SimpleNamespace(collect_frame=lambda _events, _keys: object())

    app = GameApp.__new__(GameApp)
    app.config = config
    app.catalog = SimpleNamespace(stages={stage_id: stage})
    app.ability_registry = object()
    app.active_roster = ActiveRoster()
    app.active_roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    app.selected_node_index = 0
    app.mode = "world_map"
    monkeypatch.setattr(app, "_visible_nodes", lambda: [node])
    monkeypatch.setattr(app, "_render_stage", lambda *_args: None)
    monkeypatch.setattr(app, "_flush_save", lambda: None)
    monkeypatch.setattr(app_module, "pygame", fake_pygame)
    monkeypatch.setattr(app_module, "InputDeviceMux", lambda: input_mux)
    monkeypatch.setattr(app_module, "StageRuntime", RuntimeProbe)

    app._start_selected_stage()
    assert app.run() == 0

    expected_seed = derive_stage_seed(config.replay_seed, stage_id)
    assert created_seeds == [expected_seed, expected_seed]
    assert created_slots == [(1,), (1,)]
