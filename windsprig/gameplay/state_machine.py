"""Validate deterministic actor-state transitions."""

from __future__ import annotations

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Idle": {"Run", "Jump", "Hover", "Attack", "Draw", "Guard", "Dodge", "Hurt", "Dead"},
    "Run": {"Idle", "Jump", "Hover", "Attack", "Draw", "Guard", "Dodge", "Hurt", "Dead"},
    "Jump": {"Hover", "Fall", "Attack", "Draw", "Dodge", "Hurt", "Dead"},
    "Hover": {"Fall", "Attack", "Draw", "Dodge", "Hurt", "Dead"},
    "Fall": {"Idle", "Run", "Draw", "Attack", "Dodge", "Hurt", "Dead"},
    "Draw": {"Harmonize", "Idle", "Run", "Fall", "Hurt", "Dead"},
    "Harmonize": {"Idle", "Run", "Attack", "Hurt", "Dead"},
    "Attack": {"Idle", "Run", "Fall", "Hurt", "Dead"},
    "Guard": {"Idle", "Run", "Fall", "Dodge", "Hurt", "Dead"},
    "Dodge": {"Idle", "Run", "Fall", "Hurt", "Dead"},
    "Hurt": {"Idle", "Run", "Fall", "Dead"},
    "Dead": {"Idle"},
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(current: str, target: str) -> str:
    if current == target:
        return current
    if can_transition(current, target):
        return target
    return current
