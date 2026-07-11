from __future__ import annotations


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Idle": {"Run", "Jump", "Float", "Draw", "Guard", "Dodge", "Hurt", "Dead"},
    "Run": {"Idle", "Jump", "Float", "Draw", "Guard", "Dodge", "Hurt", "Dead"},
    "Jump": {"Float", "Fall", "Attack", "Draw", "Hurt", "Dead"},
    "Float": {"Fall", "Attack", "Draw", "Hurt", "Dead"},
    "Fall": {"Idle", "Run", "Draw", "Attack", "Hurt", "Dead"},
    "Draw": {"Harmonize", "Idle", "Run", "Hurt", "Dead"},
    "Harmonize": {"Idle", "Run", "Attack", "Hurt", "Dead"},
    "Attack": {"Idle", "Run", "Fall", "Hurt", "Dead"},
    "Guard": {"Idle", "Run", "Hurt", "Dead"},
    "Dodge": {"Idle", "Run", "Fall", "Hurt", "Dead"},
    "Hurt": {"Idle", "Run", "Dead"},
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
