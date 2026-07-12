"""Canonical stable IDs shared by audio generation, validation, and direction."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

ABILITY_IDS: Final = frozenset(
    {
        "bloomblade",
        "cinder",
        "galehook",
        "stoneheart",
        "tempest",
        "voltsong",
    }
)

BOSS_PHASES: Final = MappingProxyType(
    {
        "rootjaw": (
            "rootjaw.buried_hunger",
            "rootjaw.tangled_fury",
            "rootjaw.heartwood_quake",
        ),
        "crucible_crab": (
            "crucible_crab.forged_shell",
            "crucible_crab.molten_lanes",
            "crucible_crab.overheat",
        ),
        "luma_eel": (
            "luma_eel.moonlit_current",
            "luma_eel.decoy_tide",
            "luma_eel.eclipse_spiral",
        ),
        "volt_roc": (
            "volt_roc.storm_perch",
            "volt_roc.chain_sky",
            "volt_roc.tempest_dive",
        ),
        "prism_warden": (
            "prism_warden.reflection",
            "prism_warden.clone_garden",
            "prism_warden.gravity_refraction",
        ),
        "the_stillness": (
            "the_stillness.silenced_motion",
            "the_stillness.stolen_systems",
            "the_stillness.motion_returns",
        ),
    }
)

SYSTEM_MUSIC_CUE_IDS: Final = frozenset({"music.title", "music.map", "music.results", "music.credits"})
WORLD_MUSIC_CUE_IDS: Final = frozenset(f"music.world.world_{index}" for index in range(1, 7))
BOSS_MUSIC_CUE_IDS: Final = frozenset(
    f"music.boss.{boss_id}.p{phase_index}" for boss_id in BOSS_PHASES for phase_index in range(1, 4)
)
MUSIC_CUE_IDS: Final = SYSTEM_MUSIC_CUE_IDS | WORLD_MUSIC_CUE_IDS | BOSS_MUSIC_CUE_IDS

ACTION_SFX_CUE_IDS: Final = frozenset(
    {
        "sfx.ui.confirm",
        "sfx.ui.cancel",
        "sfx.save.ok",
        "sfx.player.jump",
        "sfx.player.hover",
        "sfx.draw.start",
        "sfx.draw.release",
        "sfx.enemy.launch",
        "sfx.harmonize",
        "sfx.damage",
        "sfx.guard",
        "sfx.dodge",
        "sfx.mote",
        "sfx.checkpoint",
        "sfx.goal",
        "sfx.defeat",
        "sfx.victory",
    }
)
ABILITY_SFX_CUE_IDS: Final = frozenset(f"sfx.ability.{ability_id}" for ability_id in ABILITY_IDS)
BOSS_SFX_CUE_IDS: Final = frozenset(f"sfx.boss.{boss_id}" for boss_id in BOSS_PHASES)
SFX_CUE_IDS: Final = ACTION_SFX_CUE_IDS | ABILITY_SFX_CUE_IDS | BOSS_SFX_CUE_IDS

if len(MUSIC_CUE_IDS) != 28 or len(SFX_CUE_IDS) != 29:
    raise AssertionError("canonical audio inventory must remain exactly 28 music cues and 29 SFX")


__all__ = [
    "ABILITY_IDS",
    "BOSS_PHASES",
    "MUSIC_CUE_IDS",
    "SFX_CUE_IDS",
]
