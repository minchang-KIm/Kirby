from __future__ import annotations

from kirby_clone.content.loader import StageSpec
from kirby_clone.core.ecs import FrameSnapshot, World
from kirby_clone.gameplay.abilities import AbilityRegistry
from kirby_clone.gameplay.factory import EntityFactory
from kirby_clone.gameplay.systems import (
    AbilitySystem,
    CameraSystem,
    CollisionSystem,
    CombatSystem,
    CoopRespawnSystem,
    DamageSystem,
    EnemyAISystem,
    HudSystem,
    InhaleSystem,
    InputCommandSystem,
    MovementSystem,
    PickupSystem,
    StageGoalSystem,
)
from kirby_clone.settings import GameConfig


class StageRuntime:
    def __init__(self, config: GameConfig, stage: StageSpec, ability_registry: AbilityRegistry, seed: int) -> None:
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
        for slot in range(1, 5):
            x, y = stage.player_spawns[min(slot - 1, len(stage.player_spawns) - 1)]
            self.player_entities.append(self.factory.spawn_player(slot, x, y))

        for enemy in stage.enemy_spawns:
            self.factory.spawn_enemy(
                x=enemy.x,
                y=enemy.y,
                kind=enemy.kind,
                ability=enemy.copy_ability,
                patrol_left=enemy.patrol_left,
                patrol_right=enemy.patrol_right,
            )

        for tx, ty in stage.energy_spheres:
            self.factory.spawn_energy_sphere(tx, ty, stage.tile_size)

        self.factory.spawn_stage_goal(stage)

        self.world.scheduler.systems = [
            InputCommandSystem(),
            EnemyAISystem(),
            MovementSystem(),
            CollisionSystem(),
            InhaleSystem(),
            AbilitySystem(),
            CombatSystem(),
            DamageSystem(),
            PickupSystem(),
            CoopRespawnSystem(),
            StageGoalSystem(),
            CameraSystem(),
            HudSystem(),
        ]

    def step(self, input_frame) -> FrameSnapshot:
        return self.world.step(self.config.fixed_dt_ms, input_frame)
