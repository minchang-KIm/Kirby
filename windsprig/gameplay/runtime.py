from __future__ import annotations

from collections.abc import Sequence

from windsprig.config import GameConfig
from windsprig.content.loader import StageSpec
from windsprig.core.ecs import FrameSnapshot, World
from windsprig.gameplay.abilities import AbilityRegistry
from windsprig.gameplay.factory import EntityFactory
from windsprig.gameplay.systems import (
    AbilitySystem,
    CameraSystem,
    CollisionSystem,
    CombatSystem,
    CoopRespawnSystem,
    DamageSystem,
    DrawSystem,
    EnemyAISystem,
    HudSystem,
    InputCommandSystem,
    MovementSystem,
    PickupSystem,
    StageGoalSystem,
)
from windsprig.input.roster import ActivePlayer


class StageRuntime:
    def __init__(
        self,
        config: GameConfig,
        stage: StageSpec,
        ability_registry: AbilityRegistry,
        active_players: Sequence[ActivePlayer],
        seed: int,
    ) -> None:
        self.config = config
        self.stage = stage
        self.world = World(seed=seed)
        self.world.resources["config"] = config
        self.world.resources["stage_spec"] = stage
        self.world.resources["collision_world"] = stage.build_collision_world()
        self.world.resources["ability_registry"] = ability_registry
        self.world.resources["run_energy_spheres"] = 0
        self.world.resources["stage_cleared"] = False
        self.world.resources["camera_target"] = (0.0, 0.0)

        self.factory = EntityFactory(self.world)
        self.player_entities: list[int] = []
        for player in active_players:
            spawn_index = min(player.slot - 1, len(stage.player_spawns) - 1)
            x, y = stage.player_spawns[spawn_index]
            self.player_entities.append(self.factory.spawn_player(player.slot, x, y))

        for enemy in stage.enemy_spawns:
            self.factory.spawn_enemy(
                x=enemy.x,
                y=enemy.y,
                kind=enemy.kind,
                ability=enemy.ability_id or "none",
                patrol_left=enemy.patrol_left,
                patrol_right=enemy.patrol_right,
            )

        for mote in stage.motes:
            self.factory.spawn_energy_sphere(mote.tile_x, mote.tile_y, stage.tile_size)

        self.factory.spawn_stage_goal(stage)

        self.world.scheduler.systems = [
            InputCommandSystem(),
            EnemyAISystem(),
            MovementSystem(),
            CollisionSystem(),
            DrawSystem(),
            AbilitySystem(),
            CombatSystem(),
            DamageSystem(),
            PickupSystem(),
            CoopRespawnSystem(),
            StageGoalSystem(),
            CameraSystem(),
            HudSystem(),
        ]

    def step(self, input_frame: object) -> FrameSnapshot:
        return self.world.step(self.config.fixed_dt_ms, input_frame)
