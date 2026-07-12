"""Map immutable semantic gameplay events to allowlisted one-shot audio cues."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from windsprig.audio.catalog import ABILITY_IDS, BOSS_PHASES, SFX_CUE_IDS
from windsprig.core.events import GameEvent

STATIC_EVENT_CUES: Final = MappingProxyType(
    {
        "PlayerDodged": "sfx.dodge",
        "EnemyCaptured": "sfx.draw.start",
        "CaptureReleased": "sfx.draw.release",
        "EnemyLaunched": "sfx.enemy.launch",
        "HarmonizeUnavailable": "sfx.ui.cancel",
        "AbilityEquipped": "sfx.harmonize",
        "AbilityDropped": "sfx.draw.release",
        "AttackHit": "sfx.damage",
        "ProjectileCut": "sfx.guard",
        "EnemyDefeated": "sfx.damage",
        "MoteCollected": "sfx.mote",
        "CheckpointReached": "sfx.checkpoint",
        "GatherCompleted": "sfx.goal",
        "PlayerDefeated": "sfx.defeat",
        "PlayerRespawned": "sfx.checkpoint",
        "StageCompleted": "sfx.victory",
        "StageFailed": "sfx.defeat",
    }
)


def _exact_text(value: object) -> str | None:
    return value if type(value) is str else None


def _ability_cue(event: GameEvent) -> str | None:
    ability_id = _exact_text(event.payload.get("ability_id"))
    if ability_id not in ABILITY_IDS:
        return None
    return f"sfx.ability.{ability_id}"


def _boss_telegraph_cue(event: GameEvent) -> str | None:
    boss_id = _exact_text(event.payload.get("boss_id"))
    cue_id = _exact_text(event.payload.get("cue_id"))
    if boss_id not in BOSS_PHASES or cue_id != f"sfx.boss.{boss_id}":
        return None
    return cue_id if cue_id in SFX_CUE_IDS else None


def cue_for_event(event: GameEvent) -> str | None:
    """Return an exact known cue, safely ignoring malformed event payloads.

    Exact DTO typing prevents a derived mapping or event class from changing
    lookup behavior at this presentation boundary. Unknown semantic topics are
    intentionally silent rather than being interpreted as asset paths.
    """

    if type(event) is not GameEvent:
        raise TypeError("event must be an exact GameEvent")
    if event.topic == "PlayerDamaged":
        guarded = event.payload.get("guarded")
        if guarded is True:
            return "sfx.guard"
        if guarded is False or guarded is None:
            return "sfx.damage"
        return None
    if event.topic in {"AbilityUsed", "AttackSpawned"}:
        return _ability_cue(event)
    if event.topic == "BossAttackTelegraphed":
        return _boss_telegraph_cue(event)
    return STATIC_EVENT_CUES.get(event.topic)


__all__ = ["STATIC_EVENT_CUES", "cue_for_event"]
