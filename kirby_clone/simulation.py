from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random

from .combat import CombatResolver
from .enemies import Enemy
from .entities import WorldState
from .input import InputState
from .level import LevelData
from .math2d import Rect
from .player import Player
from .settings import GameConfig


@dataclass(frozen=True)
class ReplayFrame:
    frame_index: int
    input_state: InputState
    rng_state_hash: str
    world_state_hash: str


class Simulation:
    def __init__(self, config: GameConfig, level: LevelData, seed: int | None = None) -> None:
        self.config = config
        self.level = level
        self.rng_seed = config.replay_seed if seed is None else seed
        self.rng = random.Random(self.rng_seed)
        self.frame_index = 0
        self.collision_map = level.make_collision_world()
        self.player = Player(config=config, spawn=level.player_spawn)
        self.enemies = [
            Enemy(
                kind=spawn.kind,
                spawn=(spawn.x, spawn.y),
                patrol_left=spawn.patrol_left,
                patrol_right=spawn.patrol_right,
                entity_id=100 + idx,
            )
            for idx, spawn in enumerate(level.enemy_spawns)
        ]
        self.combat = CombatResolver(i_frame_frames=int(round(config.invulnerable_ms / config.fixed_dt_ms)))
        self.collectibles = set(level.collectibles)
        self.collected_count = 0
        self.checkpoint = level.player_spawn
        self.won = False
        self.lost = False
        self.paused = False
        self._dropped_enemy_loot: set[int] = set()

    def entity_index(self) -> dict[int, object]:
        entities: dict[int, object] = {self.player.entity_id: self.player}
        for enemy in self.enemies:
            entities[enemy.entity_id] = enemy
        return entities

    def step(self, input_state: InputState) -> ReplayFrame:
        if input_state.pause_pressed:
            self.paused = not self.paused

        if input_state.restart_pressed and self.lost:
            self.reset_to_checkpoint()
            return self.snapshot_frame(input_state)

        if self.paused:
            return self.snapshot_frame(input_state)

        if not self.won and not self.lost:
            self._tick_world(input_state)
            self.frame_index += 1
        return self.snapshot_frame(input_state)

    def _tick_world(self, input_state: InputState) -> None:
        world = WorldState(
            collision_map=self.collision_map,
            entity_index=self.entity_index(),
            rng_seed=self.rng_seed,
            event_bus=[],
            frame_index=self.frame_index,
            player_id=self.player.entity_id,
        )

        self.player.set_input(input_state)
        self.player.update(self.config.fixed_dt_ms, world)
        for enemy in self.enemies:
            enemy.update(self.config.fixed_dt_ms, world)

        events = self.combat.step(
            self.frame_index,
            attackers=self._build_hitboxes(),
            hurtboxes=self._build_hurtboxes(),
        )
        for event in events:
            target = world.entity_index.get(event.target_id)
            if target is not None:
                target.on_hit(event)

        self._handle_collectibles()
        self._handle_checkpoints()
        self._handle_goal()
        self._handle_enemy_loot()
        self.lost = self.player.dead

    def _build_hitboxes(self):
        hitboxes = self.player.get_hitboxes(self.frame_index)
        for enemy in self.enemies:
            hitboxes.extend(enemy.get_hitboxes(self.frame_index))
        return hitboxes

    def _build_hurtboxes(self):
        hurtboxes = [self.player.get_hurtbox()]
        for enemy in self.enemies:
            if not enemy.dead:
                hurtboxes.append(enemy.get_hurtbox())
        return hurtboxes

    def _handle_collectibles(self) -> None:
        player_rect = self.player.get_aabb()
        consumed: set[tuple[int, int]] = set()
        for tile in self.collectibles:
            item_rect = self._tile_rect(tile[0], tile[1], inset=8)
            if player_rect.intersects(item_rect):
                consumed.add(tile)
        if consumed:
            self.collectibles.difference_update(consumed)
            self.collected_count += len(consumed)

    def _handle_checkpoints(self) -> None:
        player_rect = self.player.get_aabb()
        hits = self.collision_map.touching_tile_coords(player_rect, self.level.checkpoint_tiles)
        for tx, ty in hits:
            self.checkpoint = (tx * self.level.tile_size + 4.0, ty * self.level.tile_size - 8.0)

    def _handle_goal(self) -> None:
        if self.player.dead:
            return
        player_rect = self.player.get_aabb()
        hits = self.collision_map.touching_tile_coords(player_rect, self.level.goal_tiles)
        if hits:
            self.won = True

    def _handle_enemy_loot(self) -> None:
        for enemy in self.enemies:
            if not enemy.dead:
                continue
            if enemy.entity_id in self._dropped_enemy_loot:
                continue
            tile_x = int(enemy.get_aabb().center_x // self.level.tile_size)
            tile_y = int(enemy.get_aabb().center_y // self.level.tile_size)
            if 0 <= tile_x < self.level.width_tiles and 0 <= tile_y < self.level.height_tiles:
                self.collectibles.add((tile_x, tile_y))
            self._dropped_enemy_loot.add(enemy.entity_id)

    def reset_to_checkpoint(self) -> None:
        self.player.respawn(self.checkpoint)
        self.lost = False
        self.won = False
        self.paused = False
        self.combat.clear()

    def snapshot_frame(self, input_state: InputState) -> ReplayFrame:
        return ReplayFrame(
            frame_index=self.frame_index,
            input_state=input_state,
            rng_state_hash=self.rng_state_hash(),
            world_state_hash=self.world_state_hash(),
        )

    def rng_state_hash(self) -> str:
        state = repr(self.rng.getstate())
        return hashlib.sha256(state.encode("utf-8")).hexdigest()[:16]

    def world_state_hash(self) -> str:
        enemy_state = [
            {
                "id": enemy.entity_id,
                "kind": enemy.kind,
                "x": round(enemy.body.rect.x, 3),
                "y": round(enemy.body.rect.y, 3),
                "hp": enemy.hp,
                "dead": enemy.dead,
                "state": enemy.state,
            }
            for enemy in sorted(self.enemies, key=lambda e: e.entity_id)
        ]
        payload = {
            "frame": self.frame_index,
            "won": self.won,
            "lost": self.lost,
            "collected": self.collected_count,
            "checkpoint": (round(self.checkpoint[0], 3), round(self.checkpoint[1], 3)),
            "player": {
                "x": round(self.player.body.rect.x, 3),
                "y": round(self.player.body.rect.y, 3),
                "vx": round(self.player.body.velocity.x, 3),
                "vy": round(self.player.body.velocity.y, 3),
                "hp": self.player.hp,
                "state": self.player.state,
                "dead": self.player.dead,
            },
            "enemies": enemy_state,
            "collectibles": sorted(self.collectibles),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def _tile_rect(self, tx: int, ty: int, inset: int = 0) -> Rect:
        size = self.level.tile_size - inset * 2
        return Rect(
            tx * self.level.tile_size + inset,
            ty * self.level.tile_size + inset,
            size,
            size,
        )
