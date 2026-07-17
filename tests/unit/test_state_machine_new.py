from __future__ import annotations

from windsprig.gameplay.state_machine import ALLOWED_TRANSITIONS, can_transition, transition


def test_valid_state_transition() -> None:
    assert can_transition("Idle", "Run")
    assert transition("Idle", "Run") == "Run"


def test_invalid_state_transition_is_blocked() -> None:
    assert not can_transition("Draw", "Guard")
    assert transition("Draw", "Guard") == "Draw"


def test_hover_guard_and_dodge_use_only_the_public_legal_vocabulary() -> None:
    assert "Float" not in ALLOWED_TRANSITIONS
    assert can_transition("Idle", "Hover")
    assert can_transition("Hover", "Fall")
    assert can_transition("Guard", "Fall")
    assert can_transition("Guard", "Dodge")
    assert can_transition("Dodge", "Fall")
    assert not can_transition("Draw", "Attack")
