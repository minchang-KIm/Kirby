from __future__ import annotations

from typing import get_args

import pytest

from windsprig.screens.base import ScreenId, ScreenTransition


def test_screen_ids_are_the_locked_foundation_transition_vocabulary() -> None:
    assert get_args(ScreenId) == (
        "boot",
        "title",
        "profile",
        "hub",
        "world_map",
        "stage_intro",
        "playing",
        "paused",
        "results",
        "defeat",
        "settings",
        "controls",
        "credits",
        "recovery",
    )


def test_transition_copies_and_freezes_its_payload() -> None:
    source: dict[str, object] = {"stage_id": "world_1_stage_1"}

    transition = ScreenTransition("playing", source)
    source["stage_id"] = "changed"

    assert transition.payload["stage_id"] == "world_1_stage_1"
    with pytest.raises(TypeError):
        transition.payload["stage_id"] = "mutated"  # type: ignore[index]
