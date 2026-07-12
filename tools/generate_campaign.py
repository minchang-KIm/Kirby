from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

Route = Literal["main", "optional", "mastery"]


@dataclass(frozen=True)
class Recipe:
    world: str
    slug: str
    title: str
    target_ms: int
    width: int
    gaps: tuple[tuple[int, int], ...]
    platforms: tuple[tuple[int, int, int], ...]
    hazards: tuple[tuple[int, int, int], ...]
    mechanics: tuple[tuple[str, int, int, int, int], ...]
    encounters: tuple[tuple[str, str | None, int, int, bool], ...]
    motes: tuple[tuple[int, int, Route], tuple[int, int, Route], tuple[int, int, Route]]
    checkpoints: tuple[int, ...]
    boss_id: str | None = None


WORLDS = (
    (
        "world_1",
        "Sunleaf Vale",
        ("gust_lift", "breakable"),
        "palette.sunleaf",
        ((150, 500), (350, 410), (555, 480), (765, 345), (1040, 300)),
    ),
    (
        "world_2",
        "Emberglass Works",
        ("conveyor", "heat_vent", "timed_shutter"),
        "palette.emberglass",
        ((145, 430), (350, 505), (560, 390), (780, 475), (1045, 330)),
    ),
    (
        "world_3",
        "Tidemoon Grotto",
        ("current", "buoyant_pod", "falling_water"),
        "palette.tidemoon",
        ((140, 510), (360, 455), (555, 340), (790, 410), (1040, 285)),
    ),
    (
        "world_4",
        "Thunderrail Heights",
        ("rail", "conductor", "rotating_tower"),
        "palette.thunderrail",
        ((145, 490), (345, 350), (565, 445), (780, 315), (1040, 390)),
    ),
    (
        "world_5",
        "Prismbloom Dream",
        ("mirror", "color_beam", "gravity_bloom"),
        "palette.prismbloom",
        ((140, 455), (350, 330), (565, 480), (785, 365), (1040, 265)),
    ),
    (
        "world_6",
        "Stillstar Crown",
        ("silence_field", "ability_lock"),
        "palette.stillstar",
        ((145, 500), (355, 385), (570, 500), (790, 335), (1040, 250)),
    ),
)

R = Recipe
STAGES = (
    R(
        "world_1",
        "first-flight",
        "First Flight",
        150000,
        92,
        ((31, 35), (68, 72)),
        ((12, 16, 7), (39, 14, 6), (57, 12, 5), (77, 15, 6)),
        ((31, 20, 4), (68, 20, 4)),
        (("gust_lift", 18, 16, 3, 4), ("gust_lift", 60, 12, 3, 8)),
        (
            ("breezeling", "galehook", 22, 19, False),
            ("bramblekin", "bloomblade", 49, 19, False),
            ("millmite", "voltsong", 80, 19, False),
        ),
        ((17, 14, "main"), (46, 12, "optional"), (79, 13, "mastery")),
        (38, 67),
    ),
    R(
        "world_1",
        "millstream-run",
        "Millstream Run",
        165000,
        98,
        ((24, 28), (51, 56), (82, 86)),
        ((9, 15, 6), (31, 13, 8), (60, 16, 5), (72, 11, 7), (88, 14, 5)),
        ((24, 20, 4), (52, 20, 4), (82, 20, 4)),
        (("gust_lift", 26, 13, 2, 7), ("breakable", 43, 17, 3, 3), ("gust_lift", 83, 11, 3, 9)),
        (
            ("millmite", "voltsong", 18, 19, False),
            ("breezeling", "galehook", 36, 12, False),
            ("bramblekin", "bloomblade", 64, 19, True),
            ("breezeling", "galehook", 90, 13, False),
        ),
        ((13, 13, "main"), (44, 15, "optional"), (75, 9, "mastery")),
        (48, 80),
    ),
    R(
        "world_1",
        "bramble-updraft",
        "Bramble Updraft",
        180000,
        104,
        ((19, 23), (45, 49), (73, 79)),
        ((7, 14, 6), (27, 16, 6), (36, 11, 5), (52, 13, 8), (64, 9, 5), (82, 15, 9), (94, 11, 5)),
        ((19, 20, 4), (45, 20, 4), (74, 20, 5)),
        (("breakable", 30, 14, 2, 2), ("gust_lift", 47, 12, 3, 8), ("breakable", 86, 13, 3, 2)),
        (
            ("bramblekin", "bloomblade", 15, 19, False),
            ("millmite", "voltsong", 32, 15, False),
            ("breezeling", "galehook", 58, 12, False),
            ("bramblekin", "bloomblade", 69, 19, True),
            ("millmite", "voltsong", 91, 14, False),
        ),
        ((10, 12, "main"), (38, 9, "optional"), (96, 9, "mastery")),
        (43, 72),
    ),
    R(
        "world_1",
        "valewind-gauntlet",
        "Valewind Gauntlet",
        210000,
        112,
        ((16, 20), (37, 42), (61, 65), (88, 94)),
        ((6, 15, 5), (22, 12, 7), (45, 15, 6), (53, 9, 5), (68, 13, 8), (79, 8, 6), (97, 14, 9)),
        ((16, 20, 4), (38, 20, 4), (61, 20, 4), (89, 20, 5)),
        (
            ("gust_lift", 17, 11, 3, 9),
            ("breakable", 48, 13, 2, 2),
            ("gust_lift", 62, 9, 3, 11),
            ("breakable", 101, 12, 3, 2),
        ),
        (
            ("breezeling", "galehook", 12, 19, False),
            ("bramblekin", "bloomblade", 27, 11, True),
            ("millmite", "voltsong", 50, 14, False),
            ("breezeling", "galehook", 73, 12, True),
            ("bramblekin", "bloomblade", 84, 19, False),
            ("millmite", "tempest", 103, 13, True),
        ),
        ((8, 13, "main"), (55, 7, "mastery"), (102, 12, "optional")),
        (36, 87),
    ),
    R(
        "world_1",
        "rootjaw-burrow",
        "Rootjaw Burrow",
        240000,
        100,
        ((27, 31), (52, 56)),
        ((10, 15, 7), (34, 12, 6), (59, 14, 8), (78, 11, 6)),
        ((27, 20, 4), (52, 20, 4)),
        (("gust_lift", 28, 12, 3, 8), ("breakable", 64, 12, 3, 2), ("switch", 82, 10, 2, 2)),
        (
            ("bramblekin", "bloomblade", 19, 19, True),
            ("breezeling", "galehook", 42, 11, False),
            ("millmite", "voltsong", 70, 19, True),
        ),
        ((13, 13, "main"), (37, 10, "optional"), (80, 9, "mastery")),
        (50, 78),
        "rootjaw",
    ),
    R(
        "world_2",
        "kilnwalk",
        "Kilnwalk",
        150000,
        94,
        ((29, 34), (69, 73)),
        ((11, 15, 6), (38, 13, 7), (55, 16, 6), (77, 12, 7)),
        ((29, 20, 5), (69, 20, 4)),
        (("conveyor", 15, 19, 8, 1), ("heat_vent", 31, 17, 2, 3), ("timed_shutter", 62, 14, 2, 6)),
        (
            ("cinderling", "cinder", 21, 19, False),
            ("slagroller", "stoneheart", 48, 19, False),
            ("shutterimp", "galehook", 80, 11, False),
        ),
        ((14, 13, "main"), (43, 11, "optional"), (81, 10, "mastery")),
        (36, 67),
    ),
    R(
        "world_2",
        "conveyor-crossing",
        "Conveyor Crossing",
        170000,
        101,
        ((20, 24), (46, 51), (78, 84)),
        ((7, 14, 6), (27, 16, 7), (36, 10, 6), (54, 13, 8), (66, 8, 6), (87, 15, 8)),
        ((20, 20, 4), (46, 20, 5), (79, 20, 5)),
        (
            ("conveyor", 9, 19, 10, 1),
            ("conveyor", 28, 15, 8, 1),
            ("heat_vent", 48, 16, 2, 4),
            ("timed_shutter", 73, 9, 2, 11),
        ),
        (
            ("slagroller", "stoneheart", 16, 19, False),
            ("cinderling", "cinder", 32, 15, False),
            ("shutterimp", "galehook", 58, 12, False),
            ("slagroller", "stoneheart", 91, 14, True),
        ),
        ((10, 12, "main"), (38, 8, "optional"), (68, 6, "mastery")),
        (45, 77),
    ),
    R(
        "world_2",
        "shutter-furnace",
        "Shutter Furnace",
        185000,
        106,
        ((25, 30), (57, 61), (90, 95)),
        ((8, 16, 6), (33, 12, 9), (48, 8, 5), (64, 15, 7), (76, 10, 8), (98, 14, 5)),
        ((25, 20, 5), (57, 20, 4), (90, 20, 5)),
        (
            ("timed_shutter", 19, 12, 2, 8),
            ("heat_vent", 27, 15, 2, 5),
            ("conveyor", 65, 14, 9, 1),
            ("timed_shutter", 87, 9, 2, 11),
        ),
        (
            ("shutterimp", "galehook", 14, 15, False),
            ("cinderling", "cinder", 38, 11, False),
            ("slagroller", "stoneheart", 68, 14, True),
            ("cinderling", "cinder", 80, 9, False),
            ("shutterimp", "voltsong", 100, 13, True),
        ),
        ((11, 14, "main"), (50, 6, "mastery"), (79, 8, "optional")),
        (52, 88),
    ),
    R(
        "world_2",
        "molten-clockwork",
        "Molten Clockwork",
        220000,
        116,
        ((18, 23), (42, 47), (65, 70), (94, 101)),
        ((6, 13, 6), (26, 16, 7), (33, 9, 5), (50, 12, 8), (73, 15, 8), (84, 8, 6), (104, 13, 7)),
        ((18, 20, 5), (42, 20, 5), (65, 20, 5), (95, 20, 6)),
        (
            ("conveyor", 7, 19, 10, 1),
            ("heat_vent", 20, 14, 2, 6),
            ("timed_shutter", 39, 10, 2, 10),
            ("conveyor", 74, 14, 10, 1),
            ("heat_vent", 98, 13, 2, 7),
        ),
        (
            ("cinderling", "cinder", 13, 19, False),
            ("slagroller", "stoneheart", 30, 15, True),
            ("shutterimp", "galehook", 54, 11, False),
            ("cinderling", "cinder", 78, 14, True),
            ("slagroller", "stoneheart", 89, 19, False),
            ("shutterimp", "tempest", 108, 12, True),
        ),
        ((9, 11, "main"), (35, 7, "mastery"), (106, 11, "optional")),
        (41, 92),
    ),
    R(
        "world_2",
        "crucible-crab",
        "Crucible Crab",
        250000,
        102,
        ((32, 37), (61, 66)),
        ((12, 15, 7), (40, 11, 7), (69, 14, 8), (84, 10, 6)),
        ((32, 20, 5), (61, 20, 5)),
        (("conveyor", 13, 19, 10, 1), ("heat_vent", 34, 15, 2, 5), ("timed_shutter", 79, 9, 2, 11)),
        (
            ("cinderling", "cinder", 20, 19, True),
            ("shutterimp", "voltsong", 45, 10, False),
            ("slagroller", "stoneheart", 72, 13, True),
        ),
        ((15, 13, "main"), (43, 9, "optional"), (86, 8, "mastery")),
        (55, 81),
        "crucible_crab",
    ),
    R(
        "world_3",
        "pod-pools",
        "Pod Pools",
        155000,
        96,
        ((26, 32), (70, 76)),
        ((9, 16, 7), (35, 13, 8), (52, 10, 6), (79, 15, 8)),
        ((26, 20, 6), (70, 20, 6)),
        (("current", 27, 15, 5, 5), ("buoyant_pod", 42, 16, 2, 2), ("falling_water", 62, 8, 3, 12)),
        (
            ("bubblefin", "cinder", 18, 19, False),
            ("shellskiff", "stoneheart", 47, 12, False),
            ("moonjelly", "voltsong", 82, 14, False),
        ),
        ((12, 14, "main"), (54, 8, "optional"), (64, 6, "mastery")),
        (39, 69),
    ),
    R(
        "world_3",
        "current-choir",
        "Current Choir",
        175000,
        103,
        ((18, 24), (49, 55), (83, 88)),
        ((6, 14, 6), (27, 16, 8), (38, 9, 6), (58, 13, 9), (72, 7, 6), (91, 15, 7)),
        ((18, 20, 6), (49, 20, 6), (83, 20, 5)),
        (
            ("current", 19, 12, 5, 8),
            ("buoyant_pod", 32, 15, 2, 2),
            ("falling_water", 50, 9, 4, 11),
            ("current", 84, 14, 4, 6),
        ),
        (
            ("bubblefin", "cinder", 13, 19, False),
            ("moonjelly", "voltsong", 31, 15, False),
            ("shellskiff", "stoneheart", 62, 12, True),
            ("bubblefin", "galehook", 94, 14, False),
        ),
        ((9, 12, "main"), (40, 7, "optional"), (74, 5, "mastery")),
        (47, 81),
    ),
    R(
        "world_3",
        "waterfall-vault",
        "Waterfall Vault",
        190000,
        108,
        ((22, 28), (54, 59), (88, 94)),
        ((8, 15, 7), (31, 11, 8), (43, 7, 5), (62, 14, 8), (75, 9, 7), (97, 13, 6)),
        ((22, 20, 6), (54, 20, 5), (88, 20, 6)),
        (
            ("falling_water", 23, 8, 5, 12),
            ("buoyant_pod", 35, 14, 2, 2),
            ("current", 55, 15, 4, 5),
            ("falling_water", 86, 7, 3, 13),
        ),
        (
            ("moonjelly", "voltsong", 16, 14, False),
            ("shellskiff", "stoneheart", 36, 10, False),
            ("bubblefin", "galehook", 66, 13, False),
            ("moonjelly", "voltsong", 78, 8, True),
            ("shellskiff", "cinder", 100, 12, True),
        ),
        ((11, 13, "main"), (45, 5, "mastery"), (77, 7, "optional")),
        (51, 86),
    ),
    R(
        "world_3",
        "mooncurrent-maze",
        "Mooncurrent Maze",
        225000,
        118,
        ((17, 23), (39, 45), (67, 73), (98, 105)),
        ((6, 16, 5), (26, 12, 8), (33, 7, 5), (48, 15, 8), (58, 9, 6), (76, 13, 8), (87, 6, 6), (108, 14, 6)),
        ((17, 20, 6), (39, 20, 6), (67, 20, 6), (98, 20, 7)),
        (
            ("current", 18, 11, 5, 9),
            ("falling_water", 40, 8, 5, 12),
            ("buoyant_pod", 52, 14, 2, 2),
            ("current", 68, 12, 5, 8),
            ("falling_water", 99, 7, 5, 13),
        ),
        (
            ("bubblefin", "galehook", 13, 19, False),
            ("shellskiff", "stoneheart", 30, 11, True),
            ("moonjelly", "voltsong", 51, 14, False),
            ("bubblefin", "cinder", 80, 12, True),
            ("shellskiff", "stoneheart", 91, 19, False),
            ("moonjelly", "tempest", 110, 13, True),
        ),
        ((8, 14, "main"), (35, 5, "mastery"), (89, 4, "optional")),
        (38, 96),
    ),
    R(
        "world_3",
        "luma-eel",
        "Luma Eel",
        255000,
        104,
        ((30, 36), (63, 69)),
        ((11, 14, 8), (39, 10, 7), (72, 13, 8), (88, 8, 6)),
        ((30, 20, 6), (63, 20, 6)),
        (("current", 31, 12, 5, 8), ("buoyant_pod", 44, 13, 2, 2), ("falling_water", 83, 7, 3, 13)),
        (
            ("bubblefin", "galehook", 19, 19, True),
            ("moonjelly", "voltsong", 45, 9, False),
            ("shellskiff", "stoneheart", 76, 12, True),
        ),
        ((14, 12, "main"), (42, 8, "optional"), (90, 6, "mastery")),
        (57, 84),
        "luma_eel",
    ),
    R(
        "world_4",
        "live-line",
        "Live Line",
        155000,
        97,
        ((28, 33), (72, 77)),
        ((10, 15, 7), (36, 12, 8), (55, 16, 6), (80, 11, 8)),
        ((28, 20, 5), (72, 20, 5)),
        (("rail", 13, 17, 12, 1), ("conductor", 42, 10, 2, 2), ("rotating_tower", 66, 8, 4, 12)),
        (
            ("coilbird", "voltsong", 20, 14, False),
            ("railrunner", "galehook", 48, 19, False),
            ("stormlens", "cinder", 83, 10, False),
        ),
        ((13, 13, "main"), (43, 10, "optional"), (68, 6, "mastery")),
        (40, 70),
    ),
    R(
        "world_4",
        "conductor-crossing",
        "Conductor Crossing",
        175000,
        102,
        ((21, 26), (50, 56), (84, 90)),
        ((7, 14, 6), (29, 16, 8), (39, 8, 6), (59, 13, 8), (73, 7, 6), (93, 15, 5)),
        ((21, 20, 5), (50, 20, 6), (84, 20, 6)),
        (
            ("rail", 8, 17, 12, 1),
            ("conductor", 32, 14, 2, 2),
            ("conductor", 63, 11, 2, 2),
            ("rotating_tower", 85, 8, 5, 12),
        ),
        (
            ("railrunner", "galehook", 15, 19, False),
            ("coilbird", "voltsong", 34, 15, False),
            ("stormlens", "cinder", 62, 12, True),
            ("coilbird", "voltsong", 95, 13, False),
        ),
        ((10, 12, "main"), (41, 6, "optional"), (75, 5, "mastery")),
        (48, 82),
    ),
    R(
        "world_4",
        "turntable-tempest",
        "Turntable Tempest",
        195000,
        110,
        ((24, 29), (56, 62), (92, 98)),
        ((8, 16, 7), (32, 11, 8), (45, 7, 6), (65, 14, 8), (78, 9, 7), (101, 13, 5)),
        ((24, 20, 5), (56, 20, 6), (92, 20, 6)),
        (
            ("rotating_tower", 25, 9, 4, 11),
            ("rail", 34, 12, 15, 1),
            ("conductor", 69, 12, 2, 2),
            ("rotating_tower", 94, 7, 4, 13),
        ),
        (
            ("stormlens", "cinder", 16, 15, False),
            ("coilbird", "voltsong", 37, 10, False),
            ("railrunner", "galehook", 69, 19, True),
            ("stormlens", "voltsong", 81, 8, False),
            ("coilbird", "cinder", 103, 12, True),
        ),
        ((11, 14, "main"), (47, 5, "mastery"), (80, 7, "optional")),
        (53, 90),
    ),
    R(
        "world_4",
        "observatory-ascent",
        "Observatory Ascent",
        230000,
        120,
        ((18, 24), (43, 49), (70, 76), (101, 108)),
        ((6, 13, 6), (27, 16, 8), (35, 8, 6), (52, 12, 8), (60, 6, 5), (79, 15, 8), (90, 9, 7), (111, 13, 6)),
        ((18, 20, 6), (43, 20, 6), (70, 20, 6), (101, 20, 7)),
        (
            ("rail", 7, 14, 10, 1),
            ("rotating_tower", 19, 8, 5, 12),
            ("conductor", 55, 10, 2, 2),
            ("rail", 80, 16, 12, 1),
            ("rotating_tower", 103, 6, 5, 14),
        ),
        (
            ("railrunner", "galehook", 13, 19, False),
            ("coilbird", "voltsong", 31, 15, True),
            ("stormlens", "cinder", 56, 11, False),
            ("railrunner", "galehook", 83, 14, True),
            ("coilbird", "voltsong", 94, 8, False),
            ("stormlens", "tempest", 113, 12, True),
        ),
        ((9, 11, "main"), (62, 4, "mastery"), (92, 7, "optional")),
        (42, 98),
    ),
    R(
        "world_4",
        "volt-roc",
        "Volt Roc",
        260000,
        106,
        ((31, 37), (65, 71)),
        ((12, 15, 7), (40, 10, 8), (74, 14, 8), (91, 8, 6)),
        ((31, 20, 6), (65, 20, 6)),
        (("rail", 13, 17, 12, 1), ("conductor", 44, 8, 2, 2), ("rotating_tower", 86, 7, 5, 13)),
        (
            ("coilbird", "voltsong", 20, 14, True),
            ("stormlens", "cinder", 46, 9, False),
            ("railrunner", "galehook", 78, 19, True),
        ),
        ((15, 13, "main"), (43, 8, "optional"), (93, 6, "mastery")),
        (59, 87),
        "volt_roc",
    ),
    R(
        "world_5",
        "mirror-seed",
        "Mirror Seed",
        160000,
        98,
        ((27, 32), (71, 76)),
        ((10, 15, 7), (35, 12, 8), (54, 16, 6), (79, 11, 8)),
        ((27, 20, 5), (71, 20, 5)),
        (("mirror", 18, 13, 2, 4), ("color_beam", 39, 10, 9, 2), ("gravity_bloom", 64, 12, 4, 8)),
        (
            ("petalisk", "bloomblade", 21, 19, False),
            ("mirrormite", "galehook", 47, 11, False),
            ("gravitybud", "stoneheart", 82, 10, False),
        ),
        ((13, 13, "main"), (40, 10, "optional"), (66, 8, "mastery")),
        (42, 69),
    ),
    R(
        "world_5",
        "chromatic-canopy",
        "Chromatic Canopy",
        180000,
        104,
        ((20, 25), (48, 54), (85, 91)),
        ((7, 14, 6), (28, 16, 8), (39, 8, 6), (57, 13, 8), (72, 7, 6), (94, 15, 6)),
        ((20, 20, 5), (48, 20, 6), (85, 20, 6)),
        (
            ("color_beam", 9, 12, 11, 2),
            ("mirror", 34, 14, 2, 4),
            ("gravity_bloom", 50, 10, 4, 10),
            ("mirror", 79, 5, 2, 6),
        ),
        (
            ("petalisk", "bloomblade", 15, 19, False),
            ("gravitybud", "stoneheart", 33, 15, False),
            ("mirrormite", "galehook", 61, 12, True),
            ("petalisk", "cinder", 96, 14, False),
        ),
        ((10, 12, "main"), (41, 6, "optional"), (74, 5, "mastery")),
        (46, 83),
    ),
    R(
        "world_5",
        "gravity-petal",
        "Gravity Petal",
        200000,
        111,
        ((23, 29), (58, 64), (93, 99)),
        ((8, 16, 7), (32, 11, 8), (46, 7, 6), (67, 14, 8), (80, 8, 7), (102, 13, 6)),
        ((23, 20, 6), (58, 20, 6), (93, 20, 6)),
        (
            ("gravity_bloom", 24, 9, 5, 11),
            ("mirror", 38, 9, 2, 4),
            ("color_beam", 61, 12, 12, 2),
            ("gravity_bloom", 94, 7, 5, 13),
        ),
        (
            ("gravitybud", "stoneheart", 16, 15, False),
            ("petalisk", "bloomblade", 37, 10, False),
            ("mirrormite", "galehook", 71, 13, True),
            ("gravitybud", "voltsong", 83, 7, False),
            ("petalisk", "cinder", 104, 12, True),
        ),
        ((11, 14, "main"), (48, 5, "mastery"), (82, 6, "optional")),
        (55, 91),
    ),
    R(
        "world_5",
        "refraction-labyrinth",
        "Refraction Labyrinth",
        235000,
        121,
        ((17, 23), (44, 50), (72, 78), (103, 110)),
        ((6, 13, 6), (26, 16, 8), (35, 8, 6), (53, 12, 8), (62, 6, 5), (81, 15, 8), (92, 9, 7), (113, 13, 6)),
        ((17, 20, 6), (44, 20, 6), (72, 20, 6), (103, 20, 7)),
        (
            ("mirror", 14, 11, 2, 5),
            ("color_beam", 18, 9, 14, 2),
            ("gravity_bloom", 45, 8, 5, 12),
            ("mirror", 68, 4, 2, 6),
            ("color_beam", 83, 13, 12, 2),
        ),
        (
            ("petalisk", "bloomblade", 13, 19, False),
            ("mirrormite", "galehook", 30, 15, True),
            ("gravitybud", "stoneheart", 57, 11, False),
            ("petalisk", "cinder", 85, 14, True),
            ("mirrormite", "voltsong", 96, 8, False),
            ("gravitybud", "tempest", 115, 12, True),
        ),
        ((9, 11, "main"), (64, 4, "mastery"), (94, 7, "optional")),
        (43, 100),
    ),
    R(
        "world_5",
        "prism-warden",
        "Prism Warden",
        265000,
        108,
        ((32, 38), (67, 73)),
        ((12, 15, 7), (41, 10, 8), (76, 14, 8), (93, 8, 6)),
        ((32, 20, 6), (67, 20, 6)),
        (("mirror", 19, 13, 2, 4), ("color_beam", 43, 8, 10, 2), ("gravity_bloom", 88, 6, 5, 14)),
        (
            ("petalisk", "bloomblade", 20, 19, True),
            ("mirrormite", "voltsong", 47, 9, False),
            ("gravitybud", "stoneheart", 80, 13, True),
        ),
        ((15, 13, "main"), (44, 8, "optional"), (95, 6, "mastery")),
        (61, 89),
        "prism_warden",
    ),
    R(
        "world_6",
        "hushed-court",
        "Hushed Court",
        165000,
        100,
        ((29, 34), (74, 80)),
        ((10, 15, 7), (37, 12, 8), (56, 16, 6), (83, 11, 8)),
        ((29, 20, 5), (74, 20, 6)),
        (("silence_field", 18, 11, 7, 9), ("ability_lock", 44, 13, 4, 7), ("gust_lift", 66, 12, 3, 8)),
        (
            ("hushshade", "bloomblade", 21, 19, False),
            ("lockwarden", "stoneheart", 49, 11, False),
            ("riftling", "voltsong", 86, 10, False),
        ),
        ((13, 13, "main"), (42, 10, "optional"), (68, 8, "mastery")),
        (45, 72),
    ),
    R(
        "world_6",
        "shattered-orbit",
        "Shattered Orbit",
        185000,
        106,
        ((21, 27), (51, 57), (87, 93)),
        ((7, 14, 6), (30, 16, 8), (41, 8, 6), (60, 13, 8), (75, 7, 6), (96, 15, 6)),
        ((21, 20, 6), (51, 20, 6), (87, 20, 6)),
        (
            ("gravity_bloom", 22, 10, 5, 10),
            ("silence_field", 35, 9, 7, 11),
            ("rail", 62, 14, 12, 1),
            ("ability_lock", 82, 8, 4, 12),
        ),
        (
            ("riftling", "voltsong", 15, 19, False),
            ("hushshade", "bloomblade", 35, 15, False),
            ("lockwarden", "stoneheart", 64, 12, True),
            ("riftling", "galehook", 98, 14, False),
        ),
        ((10, 12, "main"), (43, 6, "optional"), (77, 5, "mastery")),
        (49, 85),
    ),
    R(
        "world_6",
        "locked-echoes",
        "Locked Echoes",
        205000,
        113,
        ((24, 30), (60, 66), (95, 102)),
        ((8, 16, 7), (33, 11, 8), (47, 7, 6), (69, 14, 8), (82, 8, 7), (105, 13, 5)),
        ((24, 20, 6), (60, 20, 6), (95, 20, 7)),
        (
            ("ability_lock", 25, 9, 5, 11),
            ("timed_shutter", 39, 8, 2, 12),
            ("silence_field", 61, 10, 6, 10),
            ("conductor", 87, 6, 2, 2),
        ),
        (
            ("lockwarden", "stoneheart", 16, 15, False),
            ("hushshade", "bloomblade", 38, 10, False),
            ("riftling", "galehook", 73, 13, True),
            ("lockwarden", "cinder", 85, 7, False),
            ("hushshade", "voltsong", 107, 12, True),
        ),
        ((11, 14, "main"), (49, 5, "mastery"), (84, 6, "optional")),
        (57, 93),
    ),
    R(
        "world_6",
        "crown-of-motion",
        "Crown of Motion",
        240000,
        124,
        ((18, 24), (45, 51), (74, 80), (106, 113)),
        ((6, 13, 6), (27, 16, 8), (36, 8, 6), (54, 12, 8), (64, 6, 5), (83, 15, 8), (94, 9, 7), (116, 13, 6)),
        ((18, 20, 6), (45, 20, 6), (74, 20, 6), (106, 20, 7)),
        (
            ("silence_field", 19, 9, 6, 11),
            ("heat_vent", 46, 14, 2, 6),
            ("current", 75, 11, 5, 9),
            ("mirror", 90, 6, 2, 6),
            ("ability_lock", 107, 7, 5, 13),
        ),
        (
            ("hushshade", "bloomblade", 13, 19, False),
            ("lockwarden", "stoneheart", 31, 15, True),
            ("riftling", "galehook", 58, 11, False),
            ("hushshade", "cinder", 87, 14, True),
            ("lockwarden", "voltsong", 98, 8, False),
            ("riftling", "tempest", 118, 12, True),
        ),
        ((9, 11, "main"), (66, 4, "mastery"), (96, 7, "optional")),
        (44, 103),
    ),
    R(
        "world_6",
        "the-stillness",
        "The Stillness",
        280000,
        112,
        ((34, 40), (70, 76)),
        ((12, 15, 7), (43, 10, 8), (79, 14, 8), (97, 8, 6)),
        ((34, 20, 6), (70, 20, 6)),
        (("silence_field", 18, 11, 8, 9), ("ability_lock", 46, 8, 5, 12), ("gravity_bloom", 92, 6, 5, 14)),
        (
            ("hushshade", "bloomblade", 20, 19, True),
            ("riftling", "voltsong", 49, 9, False),
            ("lockwarden", "stoneheart", 83, 13, True),
        ),
        ((15, 13, "main"), (46, 8, "optional"), (99, 6, "mastery")),
        (64, 93),
        "the_stillness",
    ),
)

REWARDS = tuple(
    (threshold, reward_id, kind)
    for threshold, reward_id, kind in (
        (6, "gallery.sunleaf", "gallery"),
        (12, "palette.mint", "palette"),
        (18, "challenge.sunleaf", "challenge"),
        (24, "gallery.emberglass", "gallery"),
        (30, "palette.ember", "palette"),
        (36, "challenge.emberglass", "challenge"),
        (42, "gallery.tidemoon", "gallery"),
        (48, "palette.moon", "palette"),
        (54, "challenge.tidemoon", "challenge"),
        (60, "gallery.thunderrail", "gallery"),
        (66, "palette.storm", "palette"),
        (72, "challenge.thunderrail", "challenge"),
        (78, "gallery.prismbloom", "gallery"),
        (82, "palette.prism", "palette"),
        (84, "challenge.prismbloom", "challenge"),
        (86, "gallery.stillstar", "gallery"),
        (88, "palette.stillstar", "palette"),
        (90, "challenge.stillstar", "challenge"),
    )
)

OUTPUT_PATHS = (
    Path("windsprig/content/campaign.json"),
    Path("windsprig/content/rewards.json"),
)


def run_cells(run: tuple[int, int, int]) -> list[list[int]]:
    """Expand one horizontal tile run into canonical coordinate pairs."""

    x, y, width = run
    return [[tile_x, y] for tile_x in range(x, x + width)]


def stage_payload(recipe: Recipe, world_index: int, stage_index: int) -> dict[str, object]:
    """Expand one immutable tile recipe into the reconciled runtime schema."""

    stage_id = f"{recipe.world}_stage_{stage_index}"
    node_id = f"{recipe.world}_node_{stage_index}"
    gap_x = {x for start, stop in recipe.gaps for x in range(start, stop)}
    solids = [[x, y] for y in range(20, 24) for x in range(recipe.width) if x not in gap_x]
    one_way = [cell for platform in recipe.platforms for cell in run_cells(platform)]
    hazards = [cell for hazard in recipe.hazards for cell in run_cells(hazard)]
    checkpoint_ids = [f"{stage_id}:checkpoint:{number + 1}" for number in range(len(recipe.checkpoints))]
    main_nodes: list[dict[str, object]] = (
        [{"nav_id": "start", "tile_x": 2, "tile_y": 19, "route": "main"}]
        + [
            {"nav_id": checkpoint_ids[number], "tile_x": x, "tile_y": 19, "route": "main"}
            for number, x in enumerate(recipe.checkpoints)
        ]
        + [{"nav_id": "goal", "tile_x": recipe.width - 4, "tile_y": 19, "route": "main"}]
    )
    mote_ids = [f"{stage_id}:mote:{number}" for number in range(1, 4)]
    mote_nodes: list[dict[str, object]] = [
        {
            "nav_id": f"nav.{mote_id}",
            "tile_x": x,
            "tile_y": y,
            "route": route,
        }
        for mote_id, (x, y, route) in zip(mote_ids, recipe.motes, strict=True)
    ]
    main_ids = [str(node["nav_id"]) for node in main_nodes]
    edges = [[main_ids[number], main_ids[number + 1]] for number in range(len(main_ids) - 1)]
    for mote in mote_nodes:
        mote_x = cast(int, mote["tile_x"])
        nearest = min(main_nodes, key=lambda node: abs(cast(int, node["tile_x"]) - mote_x))
        nearest_id = str(nearest["nav_id"])
        mote_id = str(mote["nav_id"])
        edges.extend([[nearest_id, mote_id], [mote_id, nearest_id]])
    return {
        "stage_id": stage_id,
        "world_id": recipe.world,
        "node_id": node_id,
        "order": (world_index - 1) * 5 + stage_index,
        "name_key": f"stage.{recipe.world}.{stage_index:02d}.name",
        "intro_key": f"stage.{recipe.world}.{stage_index:02d}.intro",
        "target_time_ms": recipe.target_ms,
        "width_tiles": recipe.width,
        "height_tiles": 24,
        "tile_size": 32,
        "ground_y_tile": 20,
        "player_spawns": [[64.0 + offset * 30.0, 580.0] for offset in range(4)],
        "enemy_spawns": [
            {
                "spawn_id": f"enemy.{recipe.world}.{stage_index:02d}.{number + 1}",
                "kind": kind,
                "ability_id": ability,
                "x": float(x * 32),
                "y": float(y * 32),
                "patrol_left": float(max(1, x - 4) * 32),
                "patrol_right": float(min(recipe.width - 2, x + 4) * 32),
                "elite": elite,
            }
            for number, (kind, ability, x, y, elite) in enumerate(recipe.encounters)
        ],
        "motes": [
            {
                "mote_id": f"{stage_id}:mote:{number}",
                "tile_x": mote[0],
                "tile_y": mote[1],
                "route": mote[2],
            }
            for number, mote in zip(range(1, 4), recipe.motes, strict=True)
        ],
        "checkpoints": [
            {"checkpoint_id": checkpoint_ids[number], "tile_x": x, "tile_y": 19}
            for number, x in enumerate(recipe.checkpoints)
        ],
        "interactions": [
            {
                "interaction_id": f"interaction.{recipe.world}.{stage_index:02d}.{number + 1}",
                "kind": kind,
                "tile_x": x,
                "tile_y": y,
                "width_tiles": width,
                "height_tiles": height,
                "params": {},
            }
            for number, (kind, x, y, width, height) in enumerate(recipe.mechanics)
        ],
        "solids": solids,
        "one_way_tiles": one_way,
        "hazards": hazards,
        "navigation": {
            "start": "start",
            "goal": "goal",
            "nodes": main_nodes + mote_nodes,
            "edges": edges,
        },
        "goal_tile": [recipe.width - 4, 19],
        "boss_id": recipe.boss_id,
    }


def build_campaign() -> dict[str, object]:
    """Build the complete ordered six-world campaign payload."""

    stages: list[dict[str, object]] = []
    worlds: list[dict[str, object]] = []
    previous_node: str | None = None
    for world_index, (world_id, _title, mechanics, palette_id, positions) in enumerate(WORLDS, 1):
        recipes = [recipe for recipe in STAGES if recipe.world == world_id]
        nodes: list[dict[str, object]] = []
        for stage_index, recipe in enumerate(recipes, 1):
            stage = stage_payload(recipe, world_index, stage_index)
            node_id = str(stage["node_id"])
            rewards = [f"unlock:world_{world_index + 1}"] if recipe.boss_id is not None and world_index < 6 else []
            nodes.append(
                {
                    "node_id": node_id,
                    "stage_id": stage["stage_id"],
                    "position": list(positions[stage_index - 1]),
                    "requires": [] if previous_node is None else [previous_node],
                    "rewards": rewards,
                    "is_boss": recipe.boss_id is not None,
                }
            )
            previous_node = node_id
            stages.append(stage)
        worlds.append(
            {
                "world_id": world_id,
                "order": world_index,
                "name_key": f"world.{world_id}.name",
                "identity_key": f"world.{world_id}.identity",
                "mechanic_keys": [f"mechanic.{kind}.name" for kind in mechanics],
                "palette_id": palette_id,
                "nodes": nodes,
            }
        )
    return {"version": "1.0", "worlds": worlds, "stages": stages}


def build_rewards() -> dict[str, object]:
    """Build the ordered strict Mote-threshold reward payload."""

    return {
        "mote_thresholds": [
            {
                "threshold": threshold,
                "reward_id": reward_id,
                "kind": kind,
                "name_key": f"reward.{reward_id}.name",
            }
            for threshold, reward_id, kind in REWARDS
        ]
    }


def generated_outputs() -> dict[Path, object]:
    """Return every generated payload in canonical write order."""

    return {
        OUTPUT_PATHS[0]: build_campaign(),
        OUTPUT_PATHS[1]: build_rewards(),
    }


def _serialize_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def canonical_outputs() -> dict[Path, str]:
    """Serialize every output fully before any file can be replaced."""

    return {path: _serialize_payload(payload) for path, payload in generated_outputs().items()}


def check_outputs(root: Path = Path(".")) -> tuple[Path, ...]:
    """Return stale relative output paths without mutating the filesystem."""

    stale: list[Path] = []
    for relative_path, canonical in canonical_outputs().items():
        path = root / relative_path
        if not path.exists() or path.read_bytes() != canonical.encode("utf-8"):
            stale.append(relative_path)
    return tuple(sorted(stale, key=lambda path: path.as_posix()))


def _atomic_write(path: Path, canonical: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def write_outputs(root: Path = Path(".")) -> None:
    """Atomically replace outputs after all payloads serialize successfully."""

    documents = canonical_outputs()
    for relative_path, canonical in documents.items():
        _atomic_write(root / relative_path, canonical)


def main(argv: Sequence[str] | None = None, *, root: Path = Path(".")) -> int:
    """Generate campaign content or verify tracked bytes in check mode."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        stale = check_outputs(root)
        if stale:
            print("STALE: " + ", ".join(path.as_posix() for path in stale))
            return 1
    else:
        write_outputs(root)
    print("campaign: 6 worlds, 30 stages, 90 motes, 18 rewards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
