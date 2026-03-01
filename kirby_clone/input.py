from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputState:
    move_x: int = 0
    jump_pressed: bool = False
    jump_held: bool = False
    attack_pressed: bool = False
    pause_pressed: bool = False
    restart_pressed: bool = False

    @staticmethod
    def neutral() -> "InputState":
        return InputState()
