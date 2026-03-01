from __future__ import annotations

from pathlib import Path
import pygame

from kirby_clone.content import load_campaign_catalog
from kirby_clone.core.time import FixedStepClock
from kirby_clone.gameplay.abilities import create_default_registry
from kirby_clone.gameplay.components import Collider, Collectible, EnemyAI, Health, PlayerSlot, StageGoal, Team, Transform
from kirby_clone.gameplay.runtime import StageRuntime
from kirby_clone.input import InputDeviceMux
from kirby_clone.meta import CompletionTracker, SaveManager, UnlockRules, WorldMapService
from kirby_clone.settings import GameConfig


class GameApp:
    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config or GameConfig()
        self.root_dir = Path(__file__).resolve().parent
        self.content_dir = self.root_dir / "content"
        self.catalog = load_campaign_catalog(self.content_dir)
        self.ability_registry = create_default_registry(self.content_dir)
        self.save_manager = SaveManager(Path("save/save_data.json"))
        self.save_schema = self.save_manager.load()
        profile = self.save_schema.profiles[0]
        self.tracker = CompletionTracker(
            cleared_nodes=set(profile.cleared_nodes),
            energy_spheres=dict(profile.energy_spheres),
            challenge_unlocks=set(profile.challenge_unlocks),
            best_times=dict(profile.best_times),
        )
        self.unlocked_worlds = set(profile.unlocked_worlds)
        self.unlock_rules = UnlockRules(self.catalog)
        self.world_map_service = WorldMapService(self.catalog, self.unlock_rules)

        self.runtime: StageRuntime | None = None
        self.selected_node_index = 0
        self.mode = "world_map"

    def run(self) -> int:
        pygame.init()
        screen = pygame.display.set_mode(self.config.resolution)
        pygame.display.set_caption("Kirby RTD Study Clone")
        clock = pygame.time.Clock()
        fixed_clock = FixedStepClock(self.config.fixed_dt_ms)
        input_mux = InputDeviceMux()
        font = pygame.font.SysFont("malgungothic", 20)
        small_font = pygame.font.SysFont("consolas", 16)

        running = True
        while running:
            elapsed_ms = clock.tick(self.config.target_fps)
            events = pygame.event.get()
            keys = pygame.key.get_pressed()

            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.mode == "stage":
                        self.mode = "world_map"
                    else:
                        running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    if self.mode == "world_map":
                        self._start_selected_stage()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    if self.mode == "stage" and self.runtime is not None:
                        self.runtime = StageRuntime(
                            config=self.config,
                            stage=self.runtime.stage,
                            ability_registry=self.ability_registry,
                            seed=self.config.replay_seed,
                        )

            if self.mode == "world_map":
                self._update_world_map_selection(events)
            else:
                frame_input = input_mux.collect_frame(events, keys)
                steps = fixed_clock.push(elapsed_ms)
                for _ in range(steps):
                    if self.runtime is None:
                        break
                    self.runtime.step(frame_input)
                    frame_input = frame_input.continuous_only()
                    self._on_stage_progress()

            if self.mode == "world_map":
                self._render_world_map(screen, font, small_font)
            else:
                self._render_stage(screen, font, small_font)

            pygame.display.flip()

        self._flush_save()
        pygame.quit()
        return 0

    def _visible_nodes(self):
        visible = self.world_map_service.unlocked_nodes(self.tracker, self.unlocked_worlds)
        nodes = []
        for world_id in sorted(visible.keys()):
            for node in visible[world_id]:
                nodes.append(node)
        return nodes

    def _update_world_map_selection(self, events: list[pygame.event.Event]) -> None:
        nodes = self._visible_nodes()
        if not nodes:
            return
        self.selected_node_index %= len(nodes)
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in {pygame.K_RIGHT, pygame.K_d}:
                self.selected_node_index = (self.selected_node_index + 1) % len(nodes)
            elif event.key in {pygame.K_LEFT, pygame.K_a}:
                self.selected_node_index = (self.selected_node_index - 1) % len(nodes)

    def _start_selected_stage(self) -> None:
        nodes = self._visible_nodes()
        if not nodes:
            return
        node = nodes[self.selected_node_index % len(nodes)]
        stage = self.catalog.stages[node.stage_id]
        self.runtime = StageRuntime(
            config=self.config,
            stage=stage,
            ability_registry=self.ability_registry,
            seed=self.config.replay_seed + hash(node.stage_id) % 10000,
        )
        self.mode = "stage"

    def _on_stage_progress(self) -> None:
        if self.runtime is None:
            return
        if not self.runtime.world.resources.get("stage_cleared", False):
            return
        stage = self.runtime.stage
        elapsed = self.runtime.world.frame_index * self.config.fixed_dt_ms
        self.tracker.mark_stage_clear(stage.node_id, elapsed)
        self.tracker.add_energy_spheres(stage.stage_id, self.runtime.world.resources.get("run_energy_spheres", 0))
        self.unlocked_worlds = self.unlock_rules.apply_stage_rewards(stage.node_id, self.unlocked_worlds)
        self._flush_save()
        self.mode = "world_map"

    def _flush_save(self) -> None:
        profile = self.save_schema.profiles[0]
        profile.unlocked_worlds = set(self.unlocked_worlds)
        profile.cleared_nodes = set(self.tracker.cleared_nodes)
        profile.energy_spheres = dict(self.tracker.energy_spheres)
        profile.challenge_unlocks = set(self.tracker.challenge_unlocks)
        profile.best_times = dict(self.tracker.best_times)
        self.save_manager.save(self.save_schema)

    def _render_world_map(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        screen.fill((25, 33, 64))
        title = font.render("월드맵 - Enter: 스테이지 시작 / Esc: 종료", True, (240, 242, 255))
        screen.blit(title, (20, 18))
        nodes = self._visible_nodes()
        if not nodes:
            msg = font.render("해금된 노드가 없습니다.", True, (255, 220, 220))
            screen.blit(msg, (20, 70))
            return

        for idx, node in enumerate(nodes):
            selected = idx == (self.selected_node_index % len(nodes))
            cleared = node.node_id in self.tracker.cleared_nodes
            color = (95, 225, 150) if cleared else (255, 210, 94)
            if selected:
                color = (255, 255, 255)
            x, y = node.position
            pygame.draw.circle(screen, color, (x, y), 18 if selected else 14)
            label = small_font.render(node.stage_id, True, (10, 10, 10))
            screen.blit(label, (x - label.get_width() // 2, y - 34))

        info = small_font.render(
            f"해금 월드: {', '.join(sorted(self.unlocked_worlds))} | 클리어 노드: {len(self.tracker.cleared_nodes)}",
            True,
            (230, 230, 245),
        )
        screen.blit(info, (20, screen.get_height() - 30))

    def _render_stage(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        runtime = self.runtime
        if runtime is None:
            self.mode = "world_map"
            return

        stage = runtime.stage
        world = runtime.world
        screen.fill((92, 160, 244))
        camera_x, camera_y = self._camera_offset(runtime)

        # Tile layers
        for tx, ty in stage.solids:
            pygame.draw.rect(
                screen,
                (76, 98, 128),
                pygame.Rect(tx * stage.tile_size - camera_x, ty * stage.tile_size - camera_y, stage.tile_size, stage.tile_size),
            )
        for tx, ty in stage.one_way_tiles:
            pygame.draw.rect(
                screen,
                (116, 140, 171),
                pygame.Rect(tx * stage.tile_size - camera_x, ty * stage.tile_size - camera_y, stage.tile_size, 8),
            )
        for tx, ty in stage.hazards:
            pygame.draw.rect(
                screen,
                (230, 85, 85),
                pygame.Rect(tx * stage.tile_size - camera_x, ty * stage.tile_size - camera_y, stage.tile_size, stage.tile_size),
            )

        for entity_id, collectible, transform, collider in world.query(Collectible, Transform, Collider):
            _ = entity_id
            if collectible.collected:
                continue
            pygame.draw.ellipse(
                screen,
                (255, 239, 120),
                pygame.Rect(transform.x - camera_x, transform.y - camera_y, collider.width, collider.height),
            )

        for _, goal, transform, collider in world.query(StageGoal, Transform, Collider):
            _ = goal
            pygame.draw.rect(
                screen,
                (116, 230, 162),
                pygame.Rect(transform.x - camera_x, transform.y - camera_y, collider.width, collider.height),
            )

        for entity_id, team, transform, collider, health in world.query(Team, Transform, Collider, Health):
            color = (255, 167, 191) if team.name == "player" else (118, 192, 255)
            if health.dead:
                color = (100, 100, 100)
            pygame.draw.rect(
                screen,
                color,
                pygame.Rect(transform.x - camera_x, transform.y - camera_y, collider.width, collider.height),
            )
            if world.has_component(entity_id, EnemyAI):
                pygame.draw.rect(
                    screen,
                    (20, 20, 40),
                    pygame.Rect(transform.x - camera_x, transform.y - 8 - camera_y, collider.width, 5),
                )
                hp_ratio = health.current / max(1, health.maximum)
                pygame.draw.rect(
                    screen,
                    (220, 84, 84),
                    pygame.Rect(transform.x - camera_x, transform.y - 8 - camera_y, int(collider.width * hp_ratio), 5),
                )

        hud = world.resources.get("hud", {})
        stage_label = font.render(f"{stage.stage_id} | Esc: 월드맵 | R: 재시작", True, (250, 250, 255))
        screen.blit(stage_label, (16, 12))
        for idx, player in enumerate(hud.get("players", [])):
            text = small_font.render(
                f"P{player['slot']} HP {player['hp']}/{player['max_hp']} LIFE {player['lives']} ABIL {player['ability']}",
                True,
                (245, 245, 255),
            )
            screen.blit(text, (16, 44 + idx * 22))
        sphere_text = small_font.render(
            f"Energy Spheres (Run): {hud.get('energy_spheres', 0)}", True, (255, 245, 170)
        )
        screen.blit(sphere_text, (16, 44 + len(hud.get("players", [])) * 22 + 6))

    def _camera_offset(self, runtime: StageRuntime) -> tuple[int, int]:
        stage = runtime.stage
        tx, ty = runtime.world.resources.get("camera_target", (0.0, 0.0))
        view_w, view_h = self.config.resolution
        cam_x = int(max(0, min(tx - view_w / 2, stage.pixel_width - view_w)))
        cam_y = int(max(0, min(ty - view_h / 2, stage.pixel_height - view_h)))
        return cam_x, cam_y


def run_app(config: GameConfig | None = None) -> int:
    return GameApp(config=config).run()
