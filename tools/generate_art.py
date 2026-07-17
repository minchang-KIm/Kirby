"""Generate and verify Windsprig's original deterministic raster atlases."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.generate_font_subset import RUNTIME_FONT, RUNTIME_FONT_SHA256
from windsprig.content.loader import load_asset_manifest

type Color = tuple[int, int, int]
type Point = tuple[int, int]

DEFAULT_ROOT: Final = Path(__file__).resolve().parents[1]
ALGORITHM: Final = "procedural-vector-v1"
LICENSE_TEXT: Final = "Original project art distributed under the root MIT license"
FONT_PATH: Final = RUNTIME_FONT.relative_to("assets").as_posix()
OUTLINE: Final[Color] = (22, 32, 43)
INK_LIGHT: Final[Color] = (245, 247, 226)
SPRIG_MINT: Final[Color] = (119, 222, 153)
SPRIG_DARK: Final[Color] = (54, 145, 91)
SPRIG_GOLD: Final[Color] = (248, 194, 67)

CLIPS: Final[Mapping[str, int]] = {
    "idle": 4,
    "run": 6,
    "jump": 2,
    "fall": 2,
    "hover": 4,
    "draw": 4,
    "captured": 4,
    "harmonize": 6,
    "attack": 6,
    "guard": 2,
    "dodge": 4,
    "hurt": 2,
    "defeated": 4,
    "victory": 6,
}

WORLD_ART: Final[Mapping[str, Mapping[str, Color]]] = {
    "world_1": {
        "sky": (151, 220, 214),
        "far": (91, 177, 123),
        "near": (45, 111, 76),
        "accent": (244, 198, 76),
        "paper": (239, 229, 180),
    },
    "world_2": {
        "sky": (82, 43, 70),
        "far": (148, 60, 50),
        "near": (55, 29, 43),
        "accent": (255, 137, 54),
        "paper": (232, 120, 74),
    },
    "world_3": {
        "sky": (25, 50, 91),
        "far": (43, 89, 119),
        "near": (18, 43, 72),
        "accent": (130, 224, 220),
        "paper": (111, 173, 191),
    },
    "world_4": {
        "sky": (42, 51, 88),
        "far": (72, 79, 123),
        "near": (28, 35, 66),
        "accent": (245, 224, 82),
        "paper": (135, 155, 184),
    },
    "world_5": {
        "sky": (93, 68, 128),
        "far": (85, 153, 155),
        "near": (48, 83, 92),
        "accent": (244, 145, 218),
        "paper": (177, 222, 181),
    },
    "world_6": {
        "sky": (19, 25, 54),
        "far": (49, 54, 91),
        "near": (15, 19, 41),
        "accent": (190, 227, 255),
        "paper": (116, 119, 160),
    },
}

ENEMY_SHAPES: Final[Mapping[str, tuple[Point, ...]]] = {
    "breezeling": ((8, 34), (22, 12), (45, 18), (55, 36), (33, 54), (14, 48)),
    "bramblekin": ((9, 48), (14, 18), (25, 26), (32, 7), (39, 27), (53, 17), (55, 49), (31, 56)),
    "millmite": (
        (8, 24),
        (18, 17),
        (24, 7),
        (34, 16),
        (45, 9),
        (48, 22),
        (57, 30),
        (48, 38),
        (51, 51),
        (37, 49),
        (29, 57),
        (20, 47),
        (8, 45),
        (14, 33),
    ),
    "cinderling": ((16, 53), (12, 35), (23, 24), (28, 7), (38, 24), (49, 31), (47, 52), (31, 57)),
    "slagroller": ((7, 32), (14, 14), (31, 7), (50, 15), (57, 32), (49, 51), (30, 57), (13, 49)),
    "shutterimp": ((10, 13), (52, 13), (55, 51), (36, 45), (31, 57), (26, 45), (7, 51)),
    "bubblefin": ((6, 31), (18, 17), (39, 15), (55, 31), (39, 48), (18, 46)),
    "shellskiff": ((7, 39), (17, 18), (32, 8), (47, 19), (57, 39), (46, 52), (18, 52)),
    "moonjelly": ((13, 13), (31, 6), (50, 14), (56, 34), (47, 31), (43, 54), (34, 35), (26, 55), (20, 32), (8, 35)),
    "coilbird": ((7, 35), (23, 25), (28, 8), (38, 25), (56, 31), (45, 40), (51, 54), (31, 46), (14, 53)),
    "railrunner": ((7, 22), (23, 11), (45, 14), (57, 29), (48, 41), (54, 54), (33, 49), (17, 56), (20, 42), (7, 36)),
    "stormlens": ((7, 31), (18, 17), (31, 11), (47, 18), (57, 31), (46, 45), (31, 52), (17, 45)),
    "petalisk": (
        (7, 34),
        (20, 25),
        (15, 10),
        (31, 20),
        (45, 8),
        (43, 25),
        (57, 34),
        (43, 43),
        (47, 56),
        (31, 47),
        (16, 55),
        (20, 42),
    ),
    "mirrormite": ((31, 5), (55, 31), (31, 57), (7, 31)),
    "gravitybud": ((9, 46), (14, 24), (27, 29), (31, 7), (36, 29), (50, 23), (55, 46), (41, 56), (22, 56)),
    "hushshade": ((10, 52), (13, 20), (24, 9), (32, 21), (40, 8), (52, 21), (55, 52), (42, 44), (33, 56), (23, 44)),
    "lockwarden": ((10, 27), (18, 13), (24, 7), (40, 7), (47, 14), (54, 28), (50, 55), (14, 55)),
    "riftling": ((7, 49), (17, 15), (29, 24), (35, 6), (43, 29), (57, 18), (50, 54), (29, 47)),
}

BOSS_SHAPES: Final[Mapping[str, tuple[Point, ...]]] = {
    "rootjaw": ((4, 51), (10, 20), (22, 10), (31, 24), (43, 7), (59, 21), (61, 52), (39, 45), (31, 61), (22, 45)),
    "crucible_crab": ((4, 43), (13, 21), (25, 26), (31, 9), (38, 26), (51, 20), (60, 43), (49, 57), (15, 57)),
    "luma_eel": ((3, 35), (14, 18), (28, 12), (43, 18), (61, 9), (52, 30), (61, 48), (42, 43), (27, 55), (12, 49)),
    "volt_roc": (
        (3, 35),
        (20, 24),
        (26, 5),
        (34, 22),
        (45, 9),
        (43, 27),
        (61, 34),
        (45, 43),
        (49, 60),
        (31, 49),
        (14, 59),
        (19, 42),
    ),
    "prism_warden": ((32, 3), (59, 22), (51, 54), (32, 62), (12, 53), (5, 22)),
    "the_stillness": ((5, 53), (11, 15), (25, 22), (32, 3), (39, 22), (54, 14), (59, 53), (43, 46), (32, 61), (20, 46)),
}

ABILITY_COLORS: Final[Mapping[str, Color]] = {
    "bloomblade": (126, 224, 132),
    "cinder": (255, 112, 63),
    "voltsong": (255, 226, 73),
    "galehook": (100, 218, 214),
    "stoneheart": (154, 144, 134),
    "tempest": (190, 155, 255),
}

ICON_IDS: Final = (
    "move",
    "jump",
    "hover",
    "draw",
    "release",
    "harmonize",
    "attack",
    "guard",
    "dodge",
    "hurt",
    "defeated",
    "victory",
    "mote",
    "checkpoint",
    "goal",
    "boss",
    "bloomblade",
    "cinder",
    "voltsong",
    "galehook",
    "stoneheart",
    "tempest",
    "player_1",
    "player_2",
    "player_3",
    "player_4",
    "keyboard",
    "gamepad",
    "locked",
    "available",
    "cleared",
    "audio_muted",
)

_GLYPHS: Final[Mapping[str, tuple[str, ...]]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "N": ("10001", "11001", "11001", "10101", "10011", "10011", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
}


@dataclass(frozen=True, slots=True)
class ArtEntry:
    """One generated surface and its stable publication metadata."""

    asset_id: str
    path: PurePosixPath
    surface: pygame.Surface
    frames: int
    seed: int
    recipe: str


def pixel_hash(surface: pygame.Surface) -> str:
    """Hash decoded RGBA pixels rather than encoder-dependent PNG bytes."""

    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA", False)).hexdigest()


def _surface(size: tuple[int, int], color: Color | None = None) -> pygame.Surface:
    flags = pygame.SRCALPHA if color is None else 0
    result = pygame.Surface(size, flags)
    if color is not None:
        result.fill(color)
    return result


def _outlined_polygon(surface: pygame.Surface, points: Sequence[Point], fill: Color, width: int = 4) -> None:
    pygame.draw.polygon(surface, OUTLINE, points)
    center_x = sum(point[0] for point in points) / len(points)
    center_y = sum(point[1] for point in points) / len(points)
    inset = [(round(center_x + (x - center_x) * 0.86), round(center_y + (y - center_y) * 0.86)) for x, y in points]
    pygame.draw.polygon(surface, fill, inset)
    pygame.draw.lines(surface, OUTLINE, True, points, width)


def _sprig_pose(state: str, frame: int) -> tuple[int, int, int]:
    count = CLIPS[state]
    phase = frame / count * math.tau
    lean = {"run": 4, "jump": 2, "fall": -2, "attack": 5, "dodge": 8, "hurt": -6, "defeated": 10}.get(state, 0)
    bob_amount = 3 if state in {"idle", "hover", "victory"} else 1
    bob = round(math.sin(phase) * bob_amount)
    stride = round(math.sin(phase) * 8) if state == "run" else 0
    return lean, bob, stride


def draw_sprig(cell: pygame.Surface, state: str, frame: int) -> None:
    """Draw one leaf-bodied Sprig pose with a state-specific readable accent."""

    lean, bob, stride = _sprig_pose(state, frame)
    body = [
        (31 + lean, 72 + bob),
        (23 + lean, 51 + bob),
        (28 + lean, 29 + bob),
        (43 + lean, 15 + bob),
        (61 + lean, 27 + bob),
        (68 + lean, 54 + bob),
        (54 + lean, 77 + bob),
    ]
    _outlined_polygon(cell, body, SPRIG_MINT, 4)
    pygame.draw.polygon(
        cell,
        SPRIG_DARK,
        ((42 + lean, 20 + bob), (48 + lean, 8 + bob), (57 + lean, 22 + bob), (52 + lean, 29 + bob)),
    )
    pygame.draw.lines(
        cell,
        OUTLINE,
        True,
        ((42 + lean, 20 + bob), (48 + lean, 8 + bob), (57 + lean, 22 + bob), (52 + lean, 29 + bob)),
        3,
    )

    phase = frame / CLIPS[state] * math.tau
    scarf_y = 32 + bob + round(math.sin(phase) * 4)
    scarf = ((57 + lean, 31 + bob), (89, scarf_y - 8), (80, scarf_y + 7), (58 + lean, 42 + bob))
    _outlined_polygon(cell, scarf, SPRIG_GOLD, 3)

    left_hand = (15 + lean, 53 + bob)
    right_hand = (75 + lean, 52 + bob)
    if state in {"draw", "captured", "harmonize"}:
        right_hand = (82 + lean, 36 + bob)
    elif state in {"guard", "hurt"}:
        left_hand = (33 + lean, 41 + bob)
        right_hand = (62 + lean, 40 + bob)
    elif state == "victory":
        left_hand = (24 + lean, 20 + bob)
        right_hand = (70 + lean, 18 + bob)
    pygame.draw.line(cell, OUTLINE, (31 + lean, 48 + bob), left_hand, 4)
    pygame.draw.line(cell, OUTLINE, (62 + lean, 47 + bob), right_hand, 4)
    pygame.draw.circle(cell, SPRIG_GOLD, left_hand, 3)
    pygame.draw.circle(cell, SPRIG_GOLD, right_hand, 3)

    left_foot = (27 + lean - stride, 92)
    right_foot = (66 + lean + stride, 92)
    if state == "jump":
        left_foot, right_foot = (31 + lean, 84), (66 + lean, 82)
    elif state == "fall":
        left_foot, right_foot = (20 + lean, 88), (76 + lean, 88)
    elif state == "defeated":
        left_foot, right_foot = (43, 88), (76, 88)
    pygame.draw.line(cell, OUTLINE, (38 + lean, 70 + bob), left_foot, 4)
    pygame.draw.line(cell, OUTLINE, (57 + lean, 70 + bob), right_foot, 4)

    eye_y = 44 + bob
    pygame.draw.ellipse(cell, OUTLINE, pygame.Rect(39 + lean, eye_y, 4, 7))
    pygame.draw.ellipse(cell, OUTLINE, pygame.Rect(54 + lean, eye_y, 4, 7))
    pygame.draw.line(cell, SPRIG_DARK, (40 + lean, 59 + bob), (55 + lean, 62 + bob), 2)

    accent = list(ABILITY_COLORS.values())[frame % len(ABILITY_COLORS)]
    if state == "hover":
        pygame.draw.arc(cell, (204, 247, 225), pygame.Rect(10, 60, 76, 28), math.pi, math.tau, 4)
    elif state == "draw":
        pygame.draw.arc(cell, ABILITY_COLORS["galehook"], pygame.Rect(60, 23, 28 + frame * 2, 38), -1.2, 1.2, 4)
    elif state == "captured":
        pygame.draw.circle(cell, ABILITY_COLORS["galehook"], (82, 26), 10, 4)
        pygame.draw.line(cell, INK_LIGHT, (78, 26), (86, 26), 2)
    elif state == "harmonize":
        pygame.draw.circle(cell, accent, (48, 50), 42, 4)
        pygame.draw.circle(cell, INK_LIGHT, (48, 50), 35, 2)
    elif state == "attack":
        pygame.draw.arc(cell, ABILITY_COLORS["bloomblade"], pygame.Rect(48, 7, 46, 76), -1.4, 1.4, 7)
    elif state == "guard":
        pygame.draw.arc(cell, (225, 244, 197), pygame.Rect(8, 8, 80, 80), -1.3, 1.3, 6)
        pygame.draw.line(cell, (225, 244, 197), (76, 20), (76, 77), 3)
    elif state == "dodge":
        for offset in range(3):
            y = 24 + frame * 4 + offset * 16
            pygame.draw.line(cell, ABILITY_COLORS["galehook"], (3, y), (24, y), 3)
    elif state == "hurt":
        pygame.draw.line(cell, (255, 110, 92), (10, 18), (23, 31), 5)
        pygame.draw.line(cell, (255, 110, 92), (23, 18), (10, 31), 5)
    elif state == "defeated":
        pygame.draw.line(cell, (125, 143, 150), (12, 87), (87, 87), 3)
    elif state == "victory":
        for index in range(3):
            x = 12 + ((frame * 17 + index * 29) % 75)
            y = 8 + ((frame * 11 + index * 19) % 26)
            pygame.draw.circle(cell, SPRIG_GOLD, (x, y), 3)


def player_atlas() -> pygame.Surface:
    """Return the canonical 8-by-7 atlas of 56 named Sprig frames."""

    atlas = _surface((96 * 8, 96 * 7))
    cursor = 0
    for state, count in CLIPS.items():
        for frame in range(count):
            cell = _surface((96, 96))
            draw_sprig(cell, state, frame)
            atlas.blit(cell, ((cursor % 8) * 96, (cursor // 8) * 96))
            cursor += 1
    if cursor != 56:
        raise AssertionError(f"player atlas expected 56 frames, received {cursor}")
    return atlas


def silhouette_atlas(
    points: tuple[Point, ...],
    color: Color,
    *,
    shape_index: int,
) -> pygame.Surface:
    """Draw four animation frames while preserving one distinct enemy outline."""

    atlas = _surface((96 * 4, 96))
    for frame in range(4):
        cell = _surface((96, 96))
        bob = (0, -2, 0, 2)[frame]
        shifted = tuple((round(x * 1.38 + 4), round(y * 1.38 + 4 + bob)) for x, y in points)
        _outlined_polygon(cell, shifted, color, 4)
        eye_x = 34 + (shape_index % 4) * 5
        eye_y = 42 + bob
        pygame.draw.circle(cell, INK_LIGHT, (eye_x, eye_y), 6)
        pygame.draw.circle(cell, OUTLINE, (eye_x + 1, eye_y), 3)
        motif = shape_index % 6
        if motif == 0:
            pygame.draw.arc(cell, INK_LIGHT, pygame.Rect(20, 53 + bob, 52, 22), 0.1, 3.0, 3)
        elif motif == 1:
            pygame.draw.line(cell, INK_LIGHT, (22, 62 + bob), (69, 36 + bob), 4)
        elif motif == 2:
            pygame.draw.circle(cell, INK_LIGHT, (61, 58 + bob), 8, 3)
        elif motif == 3:
            pygame.draw.polygon(cell, INK_LIGHT, ((22, 65 + bob), (45, 49 + bob), (70, 68 + bob)), 3)
        elif motif == 4:
            pygame.draw.line(cell, INK_LIGHT, (30, 30 + bob), (65, 67 + bob), 4)
            pygame.draw.line(cell, INK_LIGHT, (65, 30 + bob), (30, 67 + bob), 4)
        else:
            pygame.draw.arc(cell, INK_LIGHT, pygame.Rect(26, 27 + bob, 44, 43), 0.4, 5.8, 3)
        atlas.blit(cell, (frame * 96, 0))
    return atlas


def boss_atlas(points: tuple[Point, ...], color: Color, *, boss_index: int) -> pygame.Surface:
    """Draw six readable frames for each of three increasingly ornate phases."""

    atlas = _surface((128 * 6, 128 * 3))
    for frame in range(18):
        phase = frame // 6
        phase_frame = frame % 6
        bob = round(math.sin(phase_frame / 6 * math.tau) * (2 + phase))
        cell = _surface((128, 128))
        shifted = tuple((round(x * 1.72 + 9), round(y * 1.72 + 8 + bob)) for x, y in points)
        phase_color: Color = (
            min(255, color[0] + phase * 18),
            min(255, color[1] + phase * 18),
            min(255, color[2] + phase * 18),
        )
        _outlined_polygon(cell, shifted, phase_color, 6)
        pygame.draw.circle(cell, INK_LIGHT, (48 + boss_index * 4, 56 + bob), 8)
        pygame.draw.circle(cell, OUTLINE, (50 + boss_index * 4, 56 + bob), 4)
        if phase >= 1:
            for orbit in range(3):
                angle = phase_frame / 6 * math.tau + orbit * math.tau / 3
                center = (64 + round(math.cos(angle) * 49), 64 + round(math.sin(angle) * 42))
                pygame.draw.circle(cell, SPRIG_GOLD, center, 7, 3)
        if phase == 2:
            crown = ((42, 24 + bob), (51, 8 + bob), (63, 25 + bob), (75, 7 + bob), (87, 25 + bob))
            pygame.draw.lines(cell, INK_LIGHT, False, crown, 6)
            pygame.draw.circle(cell, color, (64, 64 + bob), 20, 5)
        marker_color = list(ABILITY_COLORS.values())[boss_index]
        if boss_index % 2 == 0:
            pygame.draw.arc(cell, marker_color, pygame.Rect(18, 18, 92, 92), 0.2, 2.9, 4)
        else:
            pygame.draw.line(cell, marker_color, (21, 108), (107, 108), 4)
        atlas.blit(cell, ((frame % 6) * 128, (frame // 6) * 128))
    return atlas


def vertical_gradient(size: tuple[int, int], top: Color, bottom: Color) -> pygame.Surface:
    """Draw a deterministic inclusive vertical RGB gradient."""

    surface = _surface(size, top)
    for y in range(size[1]):
        amount = y / max(1, size[1] - 1)
        color = tuple(round(top[index] + (bottom[index] - top[index]) * amount) for index in range(3))
        pygame.draw.line(surface, color, (0, y), (size[0], y))
    return surface


def _world_motif(
    panel: pygame.Surface,
    world_index: int,
    layer: int,
    palette: Mapping[str, Color],
    rng: random.Random,
) -> None:
    accent = palette["accent"]
    paper = palette["paper"]
    near = palette["near"]
    if world_index == 1:
        ridge_y = 390 - layer * 34
        pygame.draw.polygon(
            panel,
            near,
            (
                (0, 720),
                (0, ridge_y),
                (230, ridge_y - 90),
                (470, ridge_y),
                (760, ridge_y - 125),
                (1030, ridge_y - 25),
                (1280, ridge_y - 110),
                (1280, 720),
            ),
        )
        for x in (170, 530, 970):
            pygame.draw.line(panel, OUTLINE, (x, 500), (x, 290), 11)
            pygame.draw.circle(panel, paper, (x, 290), 55, 5)
            for angle in (0, math.pi / 2, math.pi, math.pi * 1.5):
                end = (x + round(math.cos(angle) * 75), 290 + round(math.sin(angle) * 75))
                pygame.draw.line(panel, accent, (x, 290), end, 10)
    elif world_index == 2:
        for x in range(-80, 1360, 210):
            height = rng.randrange(150, 360)
            pygame.draw.rect(panel, near, pygame.Rect(x, 720 - height, 145, height))
            pygame.draw.arc(panel, accent, pygame.Rect(x + 24, 720 - height - 50, 96, 96), 0, math.pi, 8)
            for window_y in range(720 - height + 40, 680, 72):
                pygame.draw.rect(panel, paper, pygame.Rect(x + 48, window_y, 34, 18), 3)
        pygame.draw.line(panel, accent, (0, 570 - layer * 20), (1280, 570 - layer * 20), 9)
    elif world_index == 3:
        pygame.draw.circle(panel, paper, (1030, 150), 94, 5)
        for _index in range(22):
            x = rng.randrange(20, 1260)
            y = rng.randrange(90, 650)
            radius = rng.randrange(8, 34)
            pygame.draw.circle(panel, accent, (x, y), radius, 3)
        pygame.draw.polygon(
            panel,
            near,
            (
                (0, 0),
                (0, 135),
                (180, 85),
                (320, 190),
                (470, 78),
                (680, 180),
                (900, 70),
                (1100, 145),
                (1280, 60),
                (1280, 0),
            ),
        )
    elif world_index == 4:
        for x in (120, 390, 720, 1030):
            top = 120 + rng.randrange(0, 120)
            pygame.draw.polygon(
                panel, near, ((x - 55, 720), (x - 42, top), (x, top - 70), (x + 42, top), (x + 60, 720))
            )
            pygame.draw.circle(panel, paper, (x, top), 33, 5)
        bolt = ((80, 110), (370, 270), (560, 120), (770, 310), (1150, 120))
        pygame.draw.lines(panel, accent, False, bolt, 9)
    elif world_index == 5:
        for _ in range(18):
            x = rng.randrange(0, 1280)
            y = rng.randrange(100, 670)
            radius = rng.randrange(18, 55)
            petals = [
                (x + round(math.cos(i * math.tau / 6) * radius), y + round(math.sin(i * math.tau / 6) * radius))
                for i in range(6)
            ]
            pygame.draw.polygon(panel, paper, petals, 4)
            pygame.draw.circle(panel, accent, (x, y), max(5, radius // 5))
        pygame.draw.polygon(
            panel,
            near,
            ((0, 720), (190, 450), (380, 620), (580, 330), (760, 590), (1020, 390), (1280, 560), (1280, 720)),
        )
    else:
        for _ in range(28):
            x = rng.randrange(20, 1260)
            y = rng.randrange(40, 650)
            size = rng.randrange(5, 17)
            pygame.draw.line(panel, accent, (x - size, y), (x + size, y), 3)
            pygame.draw.line(panel, accent, (x, y - size), (x, y + size), 3)
        fractures = ((0, 590), (210, 410), (420, 565), (600, 290), (820, 515), (1030, 350), (1280, 480))
        pygame.draw.lines(panel, paper, False, fractures, 9)
        pygame.draw.lines(panel, near, False, tuple((x, y + 32) for x, y in fractures), 20)


def _tile_atlas(world_index: int, palette: Mapping[str, Color]) -> pygame.Surface:
    tiles = _surface((64 * 8, 64))
    for index in range(8):
        rect = pygame.Rect(index * 64, 0, 64, 64)
        pygame.draw.rect(tiles, palette["near"], rect)
        pygame.draw.rect(tiles, OUTLINE, rect, 4)
        top = rect.top + 7 + (index % 3) * 3
        if world_index in {1, 5}:
            pygame.draw.polygon(
                tiles,
                palette["paper"],
                (
                    (rect.left + 3, top + 13),
                    (rect.centerx, top),
                    (rect.right - 3, top + 15),
                    (rect.right - 3, top + 25),
                    (rect.left + 3, top + 25),
                ),
            )
        elif world_index in {2, 4}:
            pygame.draw.line(tiles, palette["accent"], (rect.left + 8, top), (rect.right - 8, top), 7)
            pygame.draw.circle(tiles, palette["paper"], (rect.centerx, 39), 12, 3)
        elif world_index == 3:
            pygame.draw.arc(tiles, palette["accent"], pygame.Rect(rect.left + 7, 11, 50, 45), 0, math.pi, 5)
            pygame.draw.circle(tiles, palette["paper"], (rect.centerx, 26), 7)
        else:
            pygame.draw.lines(
                tiles,
                palette["paper"],
                False,
                ((rect.left + 5, 55), (rect.left + 25, 17), (rect.left + 42, 45), (rect.right - 4, 8)),
                5,
            )
    return tiles


def _prop_atlas(world_index: int, palette: Mapping[str, Color]) -> pygame.Surface:
    props = _surface((96 * 6, 96))
    for index in range(6):
        cell = _surface((96, 96))
        cx = 48
        if world_index == 1:
            pygame.draw.line(cell, OUTLINE, (cx, 88), (cx, 36), 8)
            pygame.draw.circle(cell, palette["accent"], (cx, 27), 17 + index, 4)
            pygame.draw.line(cell, OUTLINE, (cx, 27), (20, 12 + index * 2), 6)
            pygame.draw.line(cell, OUTLINE, (cx, 27), (76, 12 + index * 2), 6)
        elif world_index == 2:
            pygame.draw.rect(cell, palette["near"], pygame.Rect(18, 25, 60, 62))
            pygame.draw.rect(cell, OUTLINE, pygame.Rect(18, 25, 60, 62), 5)
            pygame.draw.arc(cell, palette["accent"], pygame.Rect(25, 10, 46, 42), 0, math.pi, 7)
        elif world_index == 3:
            pygame.draw.ellipse(cell, palette["paper"], pygame.Rect(18, 30, 60, 50))
            pygame.draw.ellipse(cell, OUTLINE, pygame.Rect(18, 30, 60, 50), 5)
            pygame.draw.circle(cell, palette["accent"], (35 + index * 5, 28), 10, 3)
        elif world_index == 4:
            pygame.draw.line(cell, OUTLINE, (48, 90), (48, 18), 9)
            pygame.draw.circle(cell, palette["paper"], (48, 18), 14, 4)
            pygame.draw.line(cell, palette["accent"], (22, 48), (74, 48), 6)
        elif world_index == 5:
            petals = [
                (
                    48 + round(math.cos(i * math.tau / 6) * (24 + index)),
                    45 + round(math.sin(i * math.tau / 6) * (24 + index)),
                )
                for i in range(6)
            ]
            pygame.draw.polygon(cell, palette["paper"], petals)
            pygame.draw.lines(cell, OUTLINE, True, petals, 5)
            pygame.draw.circle(cell, palette["accent"], (48, 45), 13)
        else:
            shard = ((15 + index * 2, 80), (32, 17), (50, 52), (71, 8 + index * 2), (82, 81))
            pygame.draw.lines(cell, palette["paper"], False, shard, 8)
            pygame.draw.circle(cell, palette["accent"], (50, 52), 8, 3)
        props.blit(cell, (index * 96, 0))
    return props


def world_set(world_id: str, palette: Mapping[str, Color], seed: int) -> Mapping[str, pygame.Surface]:
    """Build one four-part world set with world-specific geometric motifs."""

    world_index = int(world_id[-1])
    background = _surface((1280, 720 * 4), palette["sky"])
    for layer in range(4):
        panel = vertical_gradient((1280, 720), palette["sky"], palette["far"])
        _world_motif(panel, world_index, layer, palette, random.Random(seed + layer * 97))
        background.blit(panel, (0, layer * 720))

    transition = vertical_gradient((1280, 720), palette["sky"], palette["near"])
    silhouette = (
        (0, 620),
        (180, 470),
        (390, 575),
        (610, 350),
        (830, 550),
        (1030, 400),
        (1280, 520),
        (1280, 720),
        (0, 720),
    )
    pygame.draw.polygon(transition, palette["paper"], silhouette)
    pygame.draw.arc(transition, palette["accent"], pygame.Rect(340, 105, 600, 350), 0.15, 2.95, 15)
    pygame.draw.circle(transition, OUTLINE, (640, 300), 78)
    pygame.draw.circle(transition, palette["accent"], (640, 300), 64, 8)
    for ray in range(world_index + 2):
        angle = ray / (world_index + 2) * math.tau
        end = (640 + round(math.cos(angle) * 55), 300 + round(math.sin(angle) * 55))
        pygame.draw.line(transition, OUTLINE, (640, 300), end, 6)
    return {
        "background": background,
        "tiles": _tile_atlas(world_index, palette),
        "props": _prop_atlas(world_index, palette),
        "transition": transition,
    }


def _draw_icon(cell: pygame.Surface, icon_id: str, index: int) -> None:
    color = list(ABILITY_COLORS.values())[index % len(ABILITY_COLORS)]
    pygame.draw.circle(cell, OUTLINE, (32, 32), 27)
    pygame.draw.circle(cell, (42, 59, 68), (32, 32), 22)
    if icon_id in ABILITY_COLORS:
        color = ABILITY_COLORS[icon_id]
        sides = 3 + list(ABILITY_COLORS).index(icon_id)
        points = [
            (
                32 + round(math.cos(i * math.tau / sides - math.pi / 2) * 17),
                32 + round(math.sin(i * math.tau / sides - math.pi / 2) * 17),
            )
            for i in range(sides)
        ]
        pygame.draw.polygon(cell, color, points)
        pygame.draw.lines(cell, INK_LIGHT, True, points, 3)
    elif icon_id.startswith("player_"):
        slot = int(icon_id[-1])
        pygame.draw.circle(cell, color, (32, 25), 10)
        pygame.draw.polygon(cell, color, ((16, 52), (22, 35), (42, 35), (49, 52)))
        for pip in range(slot):
            pygame.draw.circle(cell, INK_LIGHT, (22 + pip * 7, 54), 2)
    elif icon_id == "guard":
        pygame.draw.polygon(cell, color, ((32, 10), (50, 18), (46, 43), (32, 54), (18, 43), (14, 18)))
        pygame.draw.line(cell, INK_LIGHT, (32, 17), (32, 46), 4)
    elif icon_id in {"jump", "hover", "dodge", "move"}:
        motion_points = ((12, 38), (34, 16), (34, 28), (53, 28), (53, 47), (34, 47), (34, 56))
        pygame.draw.polygon(cell, color, motion_points)
        if icon_id == "hover":
            pygame.draw.arc(cell, INK_LIGHT, pygame.Rect(13, 38, 39, 17), math.pi, math.tau, 3)
        if icon_id == "dodge":
            pygame.draw.line(cell, INK_LIGHT, (8, 18), (28, 18), 3)
    elif icon_id in {"locked", "available", "cleared"}:
        pygame.draw.rect(cell, color, pygame.Rect(18, 28, 28, 24), border_radius=4)
        pygame.draw.arc(cell, INK_LIGHT, pygame.Rect(22, 12, 20, 27), math.pi, math.tau, 4)
        if icon_id == "cleared":
            pygame.draw.lines(cell, OUTLINE, False, ((20, 38), (29, 47), (46, 27)), 5)
        elif icon_id == "available":
            pygame.draw.circle(cell, INK_LIGHT, (32, 39), 5)
    elif icon_id == "audio_muted":
        pygame.draw.polygon(cell, color, ((12, 27), (25, 27), (38, 16), (38, 48), (25, 37), (12, 37)))
        pygame.draw.line(cell, INK_LIGHT, (43, 22), (54, 43), 4)
        pygame.draw.line(cell, INK_LIGHT, (54, 22), (43, 43), 4)
    else:
        sides = 3 + index % 6
        polygon_points = [
            (
                32 + round(math.cos(i * math.tau / sides - math.pi / 2) * 18),
                32 + round(math.sin(i * math.tau / sides - math.pi / 2) * 18),
            )
            for i in range(sides)
        ]
        pygame.draw.polygon(cell, color, polygon_points)
        pygame.draw.circle(cell, INK_LIGHT, (32, 32), 6, 2)
    # A five-notch index pattern keeps status icons distinguishable even when
    # their larger action silhouettes share a geometric family.
    for bit in range(5):
        notch = pygame.Rect(17 + bit * 7, 55, 4, 4)
        pygame.draw.rect(cell, OUTLINE, notch)
        if index & (1 << bit):
            pygame.draw.rect(cell, SPRIG_GOLD, notch.inflate(-2, -2))


def icon_atlas() -> pygame.Surface:
    atlas = _surface((64 * len(ICON_IDS), 64))
    for index, icon_id in enumerate(ICON_IDS):
        cell = _surface((64, 64))
        _draw_icon(cell, icon_id, index)
        atlas.blit(cell, (index * 64, 0))
    return atlas


def _draw_bitmap_text(surface: pygame.Surface, text: str, position: Point, scale: int, color: Color) -> None:
    x, y = position
    cursor = x
    for character in text:
        if character == " ":
            cursor += 4 * scale
            continue
        glyph = _GLYPHS[character]
        for row, bits in enumerate(glyph):
            for column, bit in enumerate(bits):
                if bit == "1":
                    pygame.draw.rect(
                        surface, color, pygame.Rect(cursor + column * scale, y + row * scale, scale, scale)
                    )
        cursor += 6 * scale


def favicon() -> pygame.Surface:
    surface = _surface((192, 192), (16, 35, 30))
    leaf = ((38, 146), (27, 91), (55, 39), (96, 20), (139, 50), (161, 108), (126, 159), (77, 169))
    _outlined_polygon(surface, leaf, SPRIG_MINT, 10)
    pygame.draw.polygon(surface, SPRIG_DARK, ((93, 27), (109, 4), (125, 43), (112, 58)))
    pygame.draw.lines(surface, OUTLINE, True, ((93, 27), (109, 4), (125, 43), (112, 58)), 7)
    pygame.draw.line(surface, SPRIG_GOLD, (69, 150), (137, 55), 11)
    pygame.draw.arc(surface, SPRIG_GOLD, pygame.Rect(92, 70, 88, 66), -1.2, 1.1, 10)
    return surface


def social_card(player: pygame.Surface) -> pygame.Surface:
    surface = vertical_gradient((1200, 630), WORLD_ART["world_1"]["sky"], WORLD_ART["world_6"]["near"])
    for offset in range(4):
        pygame.draw.arc(
            surface, (214, 244, 218), pygame.Rect(420 - offset * 20, 95 + offset * 22, 690, 390), 0.15, 2.95, 7
        )
    first_frame = player.subsurface(pygame.Rect(0, 0, 96, 96))
    surface.blit(pygame.transform.scale(first_frame, (420, 420)), (38, 130))
    pygame.draw.rect(surface, (15, 29, 42), pygame.Rect(468, 154, 670, 280), border_radius=34)
    pygame.draw.rect(surface, SPRIG_GOLD, pygame.Rect(468, 154, 670, 280), 7, border_radius=34)
    _draw_bitmap_text(surface, "WINDSPRIG", (518, 210), 11, INK_LIGHT)
    _draw_bitmap_text(surface, "ECHOES OF THE GALE", (525, 345), 5, SPRIG_GOLD)
    pygame.draw.circle(surface, SPRIG_MINT, (1086, 505), 42)
    pygame.draw.line(surface, SPRIG_GOLD, (1068, 522), (1102, 484), 7)
    return surface


def build_entries() -> tuple[ArtEntry, ...]:
    """Build the exact in-memory inventory without touching publication paths."""

    pygame.init()
    entries: list[ArtEntry] = []
    player = player_atlas()
    entries.append(
        ArtEntry("player.sprig", PurePosixPath("generated/player/sprig.png"), player, 56, 1101, "sprig-atlas")
    )

    enemy_colors = [palette["accent"] for palette in WORLD_ART.values() for _ in range(3)]
    for index, ((enemy_id, points), color) in enumerate(zip(ENEMY_SHAPES.items(), enemy_colors, strict=True), 1):
        entries.append(
            ArtEntry(
                f"enemy.{enemy_id}",
                PurePosixPath(f"generated/enemies/{enemy_id}.png"),
                silhouette_atlas(points, color, shape_index=index - 1),
                4,
                2000 + index,
                f"enemy-silhouette-{index:02d}",
            )
        )

    for index, (boss_id, points) in enumerate(BOSS_SHAPES.items(), 1):
        color = list(WORLD_ART.values())[index - 1]["accent"]
        entries.append(
            ArtEntry(
                f"boss.{boss_id}",
                PurePosixPath(f"generated/bosses/{boss_id}.png"),
                boss_atlas(points, color, boss_index=index - 1),
                18,
                3000 + index,
                f"boss-three-phase-{index:02d}",
            )
        )

    for index, (world_id, palette) in enumerate(WORLD_ART.items(), 1):
        seed = 4000 + index
        for kind, surface in world_set(world_id, palette, seed).items():
            frames = {"background": 4, "tiles": 8, "props": 6, "transition": 1}[kind]
            entries.append(
                ArtEntry(
                    f"world.{world_id}.{kind}",
                    PurePosixPath(f"generated/worlds/{world_id}-{kind}.png"),
                    surface,
                    frames,
                    seed,
                    f"world-{kind}-{index:02d}",
                )
            )

    icons = icon_atlas()
    entries.extend(
        (
            ArtEntry("ui.icons", PurePosixPath("generated/ui/icons.png"), icons, len(ICON_IDS), 5001, "ui-icon-atlas"),
            ArtEntry("ui.favicon", PurePosixPath("generated/ui/favicon.png"), favicon(), 1, 5002, "leaf-favicon"),
            ArtEntry(
                "ui.social_card",
                PurePosixPath("generated/ui/social-card.png"),
                social_card(player),
                1,
                5003,
                "launch-social-card",
            ),
        )
    )
    if len(entries) != 52:
        raise AssertionError(f"art inventory expected 52 PNGs, received {len(entries)}")
    return tuple(entries)


def _manifest_art(entries: Sequence[ArtEntry]) -> dict[str, object]:
    return {
        entry.asset_id: {
            "frames": entry.frames,
            "height": entry.surface.get_height(),
            "mandatory": True,
            "path": entry.path.as_posix(),
            "pixel_sha256": pixel_hash(entry.surface),
            "provenance": ALGORITHM,
            "width": entry.surface.get_width(),
        }
        for entry in sorted(entries, key=lambda item: item.asset_id)
    }


def _art_provenance(entries: Sequence[ArtEntry]) -> dict[str, object]:
    clip_frames: dict[str, list[int]] = {}
    cursor = 0
    for state, count in CLIPS.items():
        clip_frames[state] = list(range(cursor, cursor + count))
        cursor += count
    return {
        "algorithm": ALGORITHM,
        "assets": {
            entry.asset_id: {
                "algorithm": ALGORITHM,
                "frames": entry.frames,
                "height": entry.surface.get_height(),
                "license": LICENSE_TEXT,
                "mandatory": True,
                "path": entry.path.as_posix(),
                "pixel_sha256": pixel_hash(entry.surface),
                "recipe": entry.recipe,
                "seed": entry.seed,
                "width": entry.surface.get_width(),
            }
            for entry in sorted(entries, key=lambda item: item.asset_id)
        },
        "clip_frames": clip_frames,
        "clips": dict(sorted(CLIPS.items())),
        "generator": "tools/generate_art.py",
        "icon_frames": {icon_id: index for index, icon_id in enumerate(ICON_IDS)},
        "license": LICENSE_TEXT,
        "schema_version": 1,
        "world_seeds": {world_id: 4000 + index for index, world_id in enumerate(WORLD_ART, 1)},
    }


def _manifest_document(root: Path, entries: Sequence[ArtEntry]) -> dict[str, object]:
    manifest_path = _safe_existing_path(root, PurePosixPath("windsprig/content/assets.json"))
    audio: dict[str, object] = {}
    provenance_files: set[str] = set()
    if manifest_path.exists():
        existing = load_asset_manifest(manifest_path)
        audio = {
            cue_id: {
                "bus": spec.bus,
                "mandatory": spec.mandatory,
                "path": spec.path,
                "sha256": spec.sha256,
            }
            for cue_id, spec in existing.audio.items()
        }
        provenance_files.update(existing.provenance_files)
    provenance_files.add("generated/art-provenance.json")
    return {
        "art": _manifest_art(entries),
        "audio": dict(sorted(audio.items())),
        "font": {
            "license": "fonts/OFL-NotoSansKR.txt",
            "mandatory": True,
            "path": FONT_PATH,
            "sha256": RUNTIME_FONT_SHA256,
        },
        "provenance_files": sorted(provenance_files),
    }


def _canonical_json(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _write_stage(stage_root: Path, entries: Sequence[ArtEntry], manifest: Mapping[str, object]) -> None:
    for entry in entries:
        path = stage_root / "assets" / Path(entry.path.as_posix())
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(entry.surface, path)
    provenance_path = stage_root / "assets/generated/art-provenance.json"
    provenance_path.write_bytes(_canonical_json(_art_provenance(entries)))
    manifest_path = stage_root / "windsprig/content/assets.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(_canonical_json(manifest))


def _decoded_hash(path: Path) -> tuple[tuple[int, int], str]:
    try:
        surface = pygame.image.load(path)
    except (OSError, pygame.error) as error:
        raise ValueError(f"could not decode PNG: {path}: {error}") from error
    return surface.get_size(), pixel_hash(surface)


def _validate_stage(stage_root: Path, entries: Sequence[ArtEntry], manifest: Mapping[str, object]) -> None:
    for entry in entries:
        path = stage_root / "assets" / Path(entry.path.as_posix())
        size, digest = _decoded_hash(path)
        expected_size = entry.surface.get_size()
        if size != expected_size or digest != pixel_hash(entry.surface):
            raise RuntimeError(f"staged art failed semantic validation: {entry.asset_id}")
    provenance = json.loads((stage_root / "assets/generated/art-provenance.json").read_text(encoding="utf-8"))
    if provenance != _art_provenance(entries):
        raise RuntimeError("staged art provenance failed canonical validation")
    staged_manifest = json.loads((stage_root / "windsprig/content/assets.json").read_text(encoding="utf-8"))
    if staged_manifest != manifest:
        raise RuntimeError("staged asset manifest failed canonical validation")


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction) and isjunction(path):
        return True
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _safe_root(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    lexical = Path(os.path.abspath(root))
    if not lexical.exists():
        raise FileNotFoundError(f"art publication root does not exist: {lexical}")
    if _is_link_or_reparse(lexical) or not lexical.is_dir():
        raise ValueError(f"art publication root must be a regular directory: {lexical}")
    return lexical


def _safe_existing_path(root: Path, relative: PurePosixPath) -> Path:
    """Return one lexical child only when every existing ancestor is no-follow safe."""

    current = root
    for part in relative.parts:
        current = current / part
        if _is_link_or_reparse(current):
            raise ValueError(f"art read path is unsafe: {current}")
    return current


def _ensure_directory(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() or _is_link_or_reparse(current):
            if _is_link_or_reparse(current) or not current.is_dir():
                raise ValueError(f"art publication directory is unsafe: {current}")
        else:
            current.mkdir()
    return current


def _validate_publication_targets(root: Path) -> None:
    _ensure_directory(root, PurePosixPath("assets"))
    _ensure_directory(root, PurePosixPath("assets/generated"))
    _ensure_directory(root, PurePosixPath("windsprig/content"))
    expected_directories = (
        PurePosixPath("assets/generated/player"),
        PurePosixPath("assets/generated/enemies"),
        PurePosixPath("assets/generated/bosses"),
        PurePosixPath("assets/generated/worlds"),
        PurePosixPath("assets/generated/ui"),
    )
    for relative in expected_directories:
        target = root / Path(relative.as_posix())
        if target.exists() or _is_link_or_reparse(target):
            if _is_link_or_reparse(target) or not target.is_dir():
                raise ValueError(f"art publication target is unsafe: {target}")
    for relative in (
        PurePosixPath("assets/generated/art-provenance.json"),
        PurePosixPath("windsprig/content/assets.json"),
    ):
        target = root / Path(relative.as_posix())
        if target.exists() or _is_link_or_reparse(target):
            if _is_link_or_reparse(target) or not target.is_file():
                raise ValueError(f"art publication target is unsafe: {target}")


def _replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _remove_owned(path: Path) -> None:
    if _is_link_or_reparse(path) or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _publish(root: Path, stage_root: Path) -> None:
    _validate_publication_targets(root)
    owned = (
        PurePosixPath("assets/generated/player"),
        PurePosixPath("assets/generated/enemies"),
        PurePosixPath("assets/generated/bosses"),
        PurePosixPath("assets/generated/worlds"),
        PurePosixPath("assets/generated/ui"),
        PurePosixPath("assets/generated/art-provenance.json"),
        PurePosixPath("windsprig/content/assets.json"),
    )
    backup_root = stage_root / "backup"
    published: list[tuple[Path, Path, bool]] = []
    try:
        for relative in owned:
            staged = stage_root / Path(relative.as_posix())
            target = root / Path(relative.as_posix())
            backup = backup_root / Path(relative.as_posix())
            backup.parent.mkdir(parents=True, exist_ok=True)
            existed = target.exists()
            if existed:
                _replace(target, backup)
            try:
                _replace(staged, target)
            except BaseException:
                if existed:
                    _replace(backup, target)
                raise
            published.append((target, backup, existed))
    except BaseException:
        for target, backup, existed in reversed(published):
            _remove_owned(target)
            if existed:
                _replace(backup, target)
        raise


def _canonical_bytes_match(committed: Path, generated: Path) -> bool:
    try:
        return committed.read_bytes() == generated.read_bytes()
    except OSError:
        return False


def _check_against_stage(root: Path, stage_root: Path, entries: Sequence[ArtEntry]) -> tuple[str, ...]:
    findings: list[str] = []
    expected_paths = {entry.path.as_posix(): entry for entry in entries}
    generated_root = _safe_existing_path(root, PurePosixPath("assets/generated"))
    if generated_root.is_dir():
        for path in generated_root.rglob("*"):
            if _is_link_or_reparse(path):
                raise ValueError(f"art read path is unsafe: {path}")
    actual_pngs = (
        {path.relative_to(root / "assets").as_posix() for path in generated_root.rglob("*.png") if path.is_file()}
        if generated_root.is_dir() and not _is_link_or_reparse(generated_root)
        else set()
    )
    for unexpected in sorted(actual_pngs - expected_paths.keys()):
        findings.append(f"UNEXPECTED art {unexpected}")
    for relative, entry in sorted(expected_paths.items()):
        committed = _safe_existing_path(root / "assets", PurePosixPath(relative))
        generated = stage_root / "assets" / Path(relative)
        if not committed.is_file() or _is_link_or_reparse(committed):
            findings.append(f"STALE art {entry.asset_id}: missing or unsafe")
            continue
        try:
            committed_size, committed_hash = _decoded_hash(committed)
            generated_size, generated_hash = _decoded_hash(generated)
        except ValueError:
            findings.append(f"STALE art {entry.asset_id}: unreadable PNG")
            continue
        if committed_size != generated_size:
            findings.append(f"STALE art {entry.asset_id}: dimensions")
        elif committed_hash != generated_hash:
            findings.append(f"STALE art {entry.asset_id}: decoded pixels")

    comparisons = (
        (
            "provenance",
            root / "assets/generated/art-provenance.json",
            stage_root / "assets/generated/art-provenance.json",
        ),
        ("manifest", root / "windsprig/content/assets.json", stage_root / "windsprig/content/assets.json"),
    )
    for label, committed, generated in comparisons:
        committed = _safe_existing_path(root, PurePosixPath(committed.relative_to(root).as_posix()))
        if _is_link_or_reparse(committed) or not _canonical_bytes_match(committed, generated):
            findings.append(f"STALE {label}: canonical JSON")
    return tuple(findings)


def generate(root: Path) -> tuple[ArtEntry, ...]:
    """Validate, stage, and transactionally publish all owned art outputs."""

    lexical_root = _safe_root(root)
    entries = build_entries()
    manifest = _manifest_document(lexical_root, entries)
    with tempfile.TemporaryDirectory(prefix=".windsprig-art-", dir=lexical_root) as temporary:
        stage_root = Path(temporary) / "stage"
        _write_stage(stage_root, entries, manifest)
        _validate_stage(stage_root, entries, manifest)
        _publish(lexical_root, stage_root)
    return entries


def check(root: Path) -> tuple[str, ...]:
    """Regenerate in isolation and report every semantic difference without writes."""

    lexical_root = _safe_root(root)
    _safe_existing_path(lexical_root, PurePosixPath("assets/generated"))
    _safe_existing_path(lexical_root, PurePosixPath("windsprig/content"))
    entries = build_entries()
    manifest = _manifest_document(lexical_root, entries)
    with tempfile.TemporaryDirectory(prefix="windsprig-art-check-") as temporary:
        stage_root = Path(temporary) / "stage"
        _write_stage(stage_root, entries, manifest)
        _validate_stage(stage_root, entries, manifest)
        return _check_against_stage(lexical_root, stage_root, entries)


def _qa_label(surface: pygame.Surface, text: str, position: Point) -> None:
    pygame.font.init()
    font = pygame.font.Font(None, 22)
    surface.blit(font.render(text, True, INK_LIGHT), position)


def write_montages(root: Path, entries: Sequence[ArtEntry]) -> tuple[Path, ...]:
    """Write ignored contact sheets used for mandatory human visual inspection."""

    output = _ensure_directory(root, PurePosixPath("artifacts/visual-qa"))
    by_id = {entry.asset_id: entry.surface for entry in entries}
    paths: list[Path] = []

    player_sheet = _surface((96 * 8 + 220, 96 * len(CLIPS)), (18, 28, 37))
    player = by_id["player.sprig"]
    cursor = 0
    for row, (state, count) in enumerate(CLIPS.items()):
        _qa_label(player_sheet, f"{state} ({count})", (10, row * 96 + 35))
        for column in range(count):
            source_index = cursor + column
            source = pygame.Rect((source_index % 8) * 96, (source_index // 8) * 96, 96, 96)
            player_sheet.blit(player, (220 + column * 96, row * 96), source)
        cursor += count
    path = output / "sprig-states.png"
    pygame.image.save(player_sheet, path)
    paths.append(path)

    enemy_sheet = _surface((6 * 180, 3 * 150 + 6 * 150), (18, 28, 37))
    for index, enemy_id in enumerate(ENEMY_SHAPES):
        x = (index % 6) * 180
        y = (index // 6) * 150
        enemy_sheet.blit(by_id[f"enemy.{enemy_id}"], (x + 42, y + 4), pygame.Rect(0, 0, 96, 96))
        _qa_label(enemy_sheet, enemy_id, (x + 8, y + 108))
    boss_y = 3 * 150
    for index, boss_id in enumerate(BOSS_SHAPES):
        y = boss_y + index * 150
        _qa_label(enemy_sheet, boss_id, (8, y + 54))
        boss = by_id[f"boss.{boss_id}"]
        for phase in range(3):
            enemy_sheet.blit(boss, (220 + phase * 200, y + 8), pygame.Rect(0, phase * 128, 128, 128))
            _qa_label(enemy_sheet, f"phase {phase + 1}", (350 + phase * 200, y + 54))
    path = output / "enemy-boss-silhouettes.png"
    pygame.image.save(enemy_sheet, path)
    paths.append(path)

    world_sheet = _surface((1200, 6 * 260), (18, 28, 37))
    for index, world_id in enumerate(WORLD_ART):
        y = index * 260
        background = by_id[f"world.{world_id}.background"].subsurface(pygame.Rect(0, 0, 1280, 720))
        transition = by_id[f"world.{world_id}.transition"]
        world_sheet.blit(pygame.transform.smoothscale(background, (480, 240)), (0, y))
        world_sheet.blit(pygame.transform.smoothscale(transition, (480, 240)), (480, y))
        world_sheet.blit(by_id[f"world.{world_id}.tiles"], (688, y + 15))
        world_sheet.blit(by_id[f"world.{world_id}.props"], (624, y + 110))
        _qa_label(world_sheet, world_id, (980, y + 110))
    path = output / "world-sets.png"
    pygame.image.save(world_sheet, path)
    paths.append(path)

    launch_sheet = _surface((1200, 1000), (18, 28, 37))
    launch_sheet.blit(by_id["ui.social_card"], (0, 0))
    launch_sheet.blit(by_id["ui.favicon"], (24, 680))
    icons = by_id["ui.icons"]
    for index in range(len(ICON_IDS)):
        x = 230 + (index % 15) * 64
        y = 680 + (index // 15) * 96
        launch_sheet.blit(icons, (x, y), pygame.Rect(index * 64, 0, 64, 64))
        _qa_label(launch_sheet, str(index + 1), (x + 23, y + 68))
    path = output / "ui-launch-art.png"
    pygame.image.save(launch_sheet, path)
    paths.append(path)
    return tuple(paths)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--montages", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate release art, or perform an isolated no-write drift check."""

    args = _parser().parse_args(argv)
    if args.check and args.montages:
        raise SystemExit("--montages cannot be combined with the no-write --check mode")
    if args.check:
        findings = check(args.root)
        for finding in findings:
            print(finding)
        if findings:
            return 1
        entries = build_entries()
    else:
        entries = generate(args.root)
        if args.montages:
            write_montages(_safe_root(args.root), entries)
    print("art: 52 PNGs, 56 player frames, 18 enemies, 6 bosses, 6 world sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
