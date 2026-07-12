"""Construct a stage world from validated content and the active roster."""

from __future__ import annotations

from typing import cast

from windsprig.config import GameConfig
from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    CameraFocus,
    CaptureState,
    Collectible,
    Collider,
    ControlIntent,
    DefenseState,
    EchoPickup,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    Health,
    MovementState,
    PlayerSlot,
    Respawn,
    StageGoal,
    Team,
    Transform,
    Velocity,
)
from windsprig.input.roster import ActivePlayer


class EntityFactory:
    """Materialize validated stage and roster records as ECS entities."""

    def __init__(self, world: World) -> None:
        self.world = world

    def spawn_player(self, player: ActivePlayer, x: float, y: float) -> int:
        """Create the entity owned by one joined roster identity."""
        config = cast(GameConfig, self.world.resources["config"])
        entity_id = self.world.create_entity()
        self.world.add_component(entity_id, Transform(x, y))
        self.world.add_component(entity_id, Velocity())
        self.world.add_component(entity_id, Collider(width=28, height=28))
        self.world.add_component(entity_id, Team("player"))
        self.world.add_component(
            entity_id,
            PlayerSlot(slot=player.slot, is_leader=player.is_leader),
        )
        self.world.add_component(
            entity_id,
            Health(current=config.player_max_hp, maximum=config.player_max_hp),
        )
        self.world.add_component(entity_id, ActorState())
        self.world.add_component(entity_id, ControlIntent())
        self.world.add_component(
            entity_id,
            MovementState(hover_remaining_ms=config.hover_duration_ms),
        )
        self.world.add_component(entity_id, DefenseState())
        self.world.add_component(entity_id, Facing(direction=1))
        self.world.add_component(entity_id, CaptureState())
        self.world.add_component(entity_id, AbilityState())
        self.world.add_component(entity_id, Respawn(x=x, y=y))
        self.world.add_component(entity_id, CameraFocus(weight=1.0))
        return entity_id

    def spawn_echo_pickup(self, ability_id: str, x: float, y: float) -> int:
        """Create one non-solid recoverable ability echo."""
        entity_id = self.world.create_entity()
        self.world.add_component(entity_id, Transform(x, y))
        self.world.add_component(entity_id, Collider(width=20, height=20, solid=False))
        self.world.add_component(entity_id, EchoPickup(ability_id))
        return entity_id

    def spawn_enemy(
        self,
        x: float,
        y: float,
        kind: str,
        ability: str,
        patrol_left: float,
        patrol_right: float,
    ) -> int:
        entity_id = self.world.create_entity()
        width, height = (30, 30) if kind in {"brute", "boss"} else (26, 26)
        hp = 12 if kind == "boss" else 4 if kind == "brute" else 2
        self.world.add_component(entity_id, Transform(x, y))
        self.world.add_component(entity_id, Velocity())
        self.world.add_component(entity_id, Collider(width=width, height=height))
        self.world.add_component(entity_id, Team("enemy"))
        self.world.add_component(entity_id, Health(current=hp, maximum=hp))
        self.world.add_component(entity_id, ActorState(name="Run"))
        self.world.add_component(
            entity_id,
            EnemyAI(
                kind=kind,
                patrol_left=patrol_left,
                patrol_right=patrol_right,
                aggro_range=230.0 if kind == "boss" else 180.0,
                facing=-1,
            ),
        )
        self.world.add_component(entity_id, EnemyDropAbility(ability=ability))
        self.world.add_component(entity_id, Facing(direction=-1))
        return entity_id

    def spawn_energy_sphere(self, tx: int, ty: int, tile_size: int) -> int:
        entity_id = self.world.create_entity()
        self.world.add_component(entity_id, Transform(tx * tile_size + 6, ty * tile_size + 6))
        self.world.add_component(entity_id, Collider(width=20, height=20, solid=False))
        self.world.add_component(entity_id, Collectible(kind="energy_sphere", value=1))
        return entity_id

    def spawn_stage_goal(self, stage: StageSpec) -> int:
        entity_id = self.world.create_entity()
        gx, gy = stage.goal_tile
        self.world.add_component(entity_id, Transform(gx * stage.tile_size + 6, gy * stage.tile_size + 2))
        self.world.add_component(entity_id, Collider(width=22, height=30, solid=False))
        self.world.add_component(
            entity_id,
            StageGoal(node_id=stage.node_id, world_id=stage.world_id, stage_id=stage.stage_id),
        )
        return entity_id
