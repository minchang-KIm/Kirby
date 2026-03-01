from __future__ import annotations

import argparse
import json
from pathlib import Path

from kirby_clone.input import InputState
from kirby_clone.level import LevelLoader
from kirby_clone.settings import GameConfig
from kirby_clone.simulation import Simulation


def _frame_to_input(frame: dict[str, object]) -> InputState:
    return InputState(
        move_x=int(frame.get("move_x", 0)),
        jump_pressed=bool(frame.get("jump_pressed", False)),
        jump_held=bool(frame.get("jump_held", False)),
        attack_pressed=bool(frame.get("attack_pressed", False)),
        pause_pressed=bool(frame.get("pause_pressed", False)),
        restart_pressed=bool(frame.get("restart_pressed", False)),
    )


def run_replay(replay_path: Path) -> tuple[str, str]:
    payload = json.loads(replay_path.read_text(encoding="utf-8"))
    config = GameConfig()
    level = LevelLoader().load_level(str(config.level_path))
    sim = Simulation(config=config, level=level, seed=int(payload.get("seed", config.replay_seed)))
    for frame in payload["frames"]:
        sim.step(_frame_to_input(frame))
    actual = sim.world_state_hash()
    expected = str(payload["expected_world_state_hash"])
    return actual, expected


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic replay and verify world hash.")
    parser.add_argument("replay", type=Path, help="Path to replay json file.")
    args = parser.parse_args()

    actual, expected = run_replay(args.replay)
    if actual != expected:
        print(f"Replay mismatch: expected={expected} actual={actual}")
        return 1
    print(f"Replay OK: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
