from __future__ import annotations

from dataclasses import dataclass
import pygame


@dataclass(frozen=True)
class KeyboardProfile:
    move_left: int
    move_right: int
    jump: int
    inhale: int
    ability: int
    guard: int
    dodge: int
    drop_ability: int


KEYBOARD_BINDINGS: dict[int, KeyboardProfile] = {
    1: KeyboardProfile(
        move_left=pygame.K_a,
        move_right=pygame.K_d,
        jump=pygame.K_w,
        inhale=pygame.K_s,
        ability=pygame.K_f,
        guard=pygame.K_g,
        dodge=pygame.K_h,
        drop_ability=pygame.K_t,
    ),
    2: KeyboardProfile(
        move_left=pygame.K_LEFT,
        move_right=pygame.K_RIGHT,
        jump=pygame.K_UP,
        inhale=pygame.K_DOWN,
        ability=pygame.K_PERIOD,
        guard=pygame.K_SLASH,
        dodge=pygame.K_RSHIFT,
        drop_ability=pygame.K_COMMA,
    ),
}


@dataclass(frozen=True)
class GamepadProfile:
    axis_move_x: int
    jump_button: int
    inhale_button: int
    ability_button: int
    guard_button: int
    dodge_button: int
    drop_button: int


GAMEPAD_BINDING = GamepadProfile(
    axis_move_x=0,
    jump_button=0,      # A
    inhale_button=2,    # X
    ability_button=1,   # B
    guard_button=4,     # LB
    dodge_button=5,     # RB
    drop_button=3,      # Y
)
