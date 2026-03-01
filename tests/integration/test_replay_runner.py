from __future__ import annotations

from pathlib import Path

from tools.replay_runner import run_replay


def test_replay_sample_matches_expected_hash() -> None:
    replay = Path("tests/integration/replay_sample.json")
    actual, expected = run_replay(replay)
    assert actual == expected
    assert expected == "44c4fd361eb8d979"
