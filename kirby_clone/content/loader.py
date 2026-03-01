from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from kirby_clone.physics import TileCollisionWorld


@dataclass(frozen=True)
class EnemySpawn:
    x: float
    y: float
    kind: str
    copy_ability: str
    patrol_left: float
    patrol_right: float


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    world_id: str
    node_id: str
    width_tiles: int
    height_tiles: int
    tile_size: int
    ground_y_tile: int
    player_spawns: list[tuple[float, float]]
    enemy_spawns: list[EnemySpawn]
    energy_spheres: list[tuple[int, int]]
    goal_tile: tuple[int, int]
    hazards: list[tuple[int, int]]
    one_way_tiles: list[tuple[int, int]]
    solids: list[tuple[int, int]]

    @property
    def pixel_width(self) -> int:
        return self.width_tiles * self.tile_size

    @property
    def pixel_height(self) -> int:
        return self.height_tiles * self.tile_size

    def build_collision_world(self) -> TileCollisionWorld:
        return TileCollisionWorld(
            tile_size=self.tile_size,
            width_tiles=self.width_tiles,
            height_tiles=self.height_tiles,
            solid_tiles=set(self.solids),
            one_way_tiles=set(self.one_way_tiles),
            hazard_tiles=set(self.hazards),
        )


@dataclass(frozen=True)
class WorldNode:
    node_id: str
    world_id: str
    stage_id: str
    requires: list[str]
    rewards: list[str]
    position: tuple[int, int]
    is_boss: bool


@dataclass(frozen=True)
class CampaignCatalog:
    worlds: dict[str, list[WorldNode]]
    stages: dict[str, StageSpec]

    def world_nodes(self, world_id: str) -> list[WorldNode]:
        return self.worlds.get(world_id, [])


def load_campaign_catalog(content_dir: Path) -> CampaignCatalog:
    payload = json.loads((content_dir / "campaign.json").read_text(encoding="utf-8"))
    worlds: dict[str, list[WorldNode]] = {}
    for world in payload["worlds"]:
        worlds[world["world_id"]] = [
            WorldNode(
                node_id=node["node_id"],
                world_id=world["world_id"],
                stage_id=node["stage_id"],
                requires=list(node.get("requires", [])),
                rewards=list(node.get("rewards", [])),
                position=(int(node["position"][0]), int(node["position"][1])),
                is_boss=bool(node.get("is_boss", False)),
            )
            for node in world["nodes"]
        ]

    stages: dict[str, StageSpec] = {}
    for stage in payload["stages"]:
        stages[stage["stage_id"]] = StageSpec(
            stage_id=stage["stage_id"],
            world_id=stage["world_id"],
            node_id=stage["node_id"],
            width_tiles=int(stage["width_tiles"]),
            height_tiles=int(stage["height_tiles"]),
            tile_size=int(stage["tile_size"]),
            ground_y_tile=int(stage["ground_y_tile"]),
            player_spawns=[(float(x), float(y)) for x, y in stage["player_spawns"]],
            enemy_spawns=[
                EnemySpawn(
                    x=float(enemy["x"]),
                    y=float(enemy["y"]),
                    kind=enemy["kind"],
                    copy_ability=enemy["copy_ability"],
                    patrol_left=float(enemy["patrol_left"]),
                    patrol_right=float(enemy["patrol_right"]),
                )
                for enemy in stage["enemy_spawns"]
            ],
            energy_spheres=[(int(x), int(y)) for x, y in stage["energy_spheres"]],
            goal_tile=(int(stage["goal_tile"][0]), int(stage["goal_tile"][1])),
            hazards=[(int(x), int(y)) for x, y in stage["hazards"]],
            one_way_tiles=[(int(x), int(y)) for x, y in stage["one_way_tiles"]],
            solids=[(int(x), int(y)) for x, y in stage["solids"]],
        )
    return CampaignCatalog(worlds=worlds, stages=stages)
