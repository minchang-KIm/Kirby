from __future__ import annotations

from kirby_clone.gameplay.state_machine import can_transition, transition


def test_valid_state_transition() -> None:
    assert can_transition("Idle", "Run")
    assert transition("Idle", "Run") == "Run"


def test_invalid_state_transition_is_blocked() -> None:
    assert not can_transition("Inhale", "Guard")
    assert transition("Inhale", "Guard") == "Inhale"
