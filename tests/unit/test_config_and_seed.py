from __future__ import annotations

import os
import subprocess
import sys

from windsprig.config import GameConfig
from windsprig.core.rng import derive_stage_seed


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
