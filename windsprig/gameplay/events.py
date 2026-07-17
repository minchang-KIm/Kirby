"""Publish stable semantic gameplay events for presentation subscribers."""

from __future__ import annotations

from enum import StrEnum

from windsprig.core.ecs import World
from windsprig.core.events import GameEvent


class GameplayTopic(StrEnum):
    """Canonical event topics shared by simulation and presentation."""

    PLAYER_JOINED = "PlayerJoined"
    PLAYER_LEFT = "PlayerLeft"
    PLAYER_DAMAGED = "PlayerDamaged"
    PLAYER_DODGED = "PlayerDodged"
    ENEMY_CAPTURED = "EnemyCaptured"
    CAPTURE_RELEASED = "CaptureReleased"
    ENEMY_LAUNCHED = "EnemyLaunched"
    HARMONIZE_UNAVAILABLE = "HarmonizeUnavailable"
    ABILITY_EQUIPPED = "AbilityEquipped"
    ABILITY_DROPPED = "AbilityDropped"
    ABILITY_USED = "AbilityUsed"
    ATTACK_SPAWNED = "AttackSpawned"
    ATTACK_HIT = "AttackHit"
    PROJECTILE_CUT = "ProjectileCut"
    ENEMY_DEFEATED = "EnemyDefeated"
    MOTE_COLLECTED = "MoteCollected"
    CHECKPOINT_REACHED = "CheckpointReached"
    PLAYER_DEFEATED = "PlayerDefeated"
    PLAYER_RESPAWNED = "PlayerRespawned"
    GATHER_STARTED = "GatherStarted"
    GATHER_CANCELLED = "GatherCancelled"
    GATHER_COMPLETED = "GatherCompleted"
    STAGE_COMPLETED = "StageCompleted"
    STAGE_FAILED = "StageFailed"


def make_event(topic: GameplayTopic, frame_index: int, **payload: object) -> GameEvent:
    """Create a gameplay event stamped with its deterministic simulation frame."""
    if not isinstance(topic, GameplayTopic):
        raise TypeError("topic must be a GameplayTopic")
    if type(frame_index) is not int:
        raise TypeError("frame_index must be an integer")
    if "frame_index" in payload:
        raise ValueError("frame_index is reserved by the gameplay event factory")
    return GameEvent(topic=topic.value, payload={"frame_index": frame_index, **payload})


def publish(world: World, topic: GameplayTopic, **payload: object) -> None:
    """Publish an event using the world's current simulation frame."""
    event = make_event(topic, world.frame_index, **payload)
    world.events.publish(event.topic, event.payload)
