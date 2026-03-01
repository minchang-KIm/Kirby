from __future__ import annotations

from dataclasses import replace

import pygame

from .assets import AssetManager
from .audio import AudioManager
from .camera import Camera
from .hud import HudRenderer
from .input import InputState
from .level import LevelLoader
from .settings import GameConfig
from .simulation import Simulation


def run_game(config: GameConfig | None = None) -> int:
    pygame.init()
    cfg = config or GameConfig()
    flags = pygame.FULLSCREEN if cfg.fullscreen else 0
    screen = pygame.display.set_mode(cfg.resolution, flags)
    pygame.display.set_caption("Kirby Practice Clone")
    clock = pygame.time.Clock()

    level = LevelLoader().load_level(str(cfg.level_path))
    sim = Simulation(config=cfg, level=level)
    camera = Camera(
        viewport_width=cfg.resolution[0],
        viewport_height=cfg.resolution[1],
        world_width=level.pixel_width,
        world_height=level.pixel_height,
    )
    assets = AssetManager(tile_size=cfg.tile_size)
    assets.load_all()
    hud = HudRenderer()
    audio = AudioManager()
    audio.play_bgm("level_01")

    running = True
    accumulator_ms = 0.0
    while running:
        frame_input, should_quit = _poll_input()
        if should_quit:
            running = False
            continue

        accumulator_ms += clock.tick(cfg.target_fps)
        step_input = frame_input
        while accumulator_ms >= cfg.fixed_dt_ms:
            sim.step(step_input)
            step_input = replace(
                step_input,
                jump_pressed=False,
                attack_pressed=False,
                pause_pressed=False,
                restart_pressed=False,
            )
            accumulator_ms -= cfg.fixed_dt_ms

        player = sim.player.get_aabb()
        camera.update(player.center_x, player.center_y)
        _draw_scene(screen, assets, camera, sim)
        hud.draw(screen, sim)
        pygame.display.flip()

    pygame.quit()
    return 0


def _poll_input() -> tuple[InputState, bool]:
    jump_pressed = False
    attack_pressed = False
    pause_pressed = False
    restart_pressed = False
    should_quit = False
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            should_quit = True
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                jump_pressed = True
            elif event.key == pygame.K_j:
                attack_pressed = True
            elif event.key == pygame.K_ESCAPE:
                pause_pressed = True
            elif event.key == pygame.K_r:
                restart_pressed = True

    keys = pygame.key.get_pressed()
    move_left = keys[pygame.K_LEFT] or keys[pygame.K_a]
    move_right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
    move_x = int(bool(move_right)) - int(bool(move_left))
    return (
        InputState(
            move_x=move_x,
            jump_pressed=jump_pressed,
            jump_held=bool(keys[pygame.K_SPACE]),
            attack_pressed=attack_pressed,
            pause_pressed=pause_pressed,
            restart_pressed=restart_pressed,
        ),
        should_quit,
    )


def _draw_scene(screen: pygame.Surface, assets: AssetManager, camera: Camera, sim: Simulation) -> None:
    _draw_background(screen)
    level = sim.level
    tile_size = level.tile_size

    def draw_tile(tile_name: str, tx: int, ty: int) -> None:
        px = tx * tile_size - camera.x
        py = ty * tile_size - camera.y
        screen.blit(assets.tiles[tile_name], (int(px), int(py)))

    for tx, ty in level.solid_tiles:
        draw_tile("solid", tx, ty)
    for tx, ty in level.one_way_tiles:
        draw_tile("one_way", tx, ty)
    for tx, ty in level.hazard_tiles:
        draw_tile("hazard", tx, ty)
    for tx, ty in level.checkpoint_tiles:
        draw_tile("checkpoint", tx, ty)
    for tx, ty in level.goal_tiles:
        draw_tile("goal", tx, ty)
    for tx, ty in sim.collectibles:
        draw_tile("collectible", tx, ty)

    player = sim.player.get_aabb()
    sprite_key = "player_attack" if sim.player.state == "attack" else "player_idle"
    screen.blit(assets.sprites[sprite_key], (int(player.x - camera.x), int(player.y - camera.y)))

    for enemy in sim.enemies:
        rect = enemy.get_aabb()
        key = "enemy_brute" if enemy.kind == "brute" else "enemy_grunt"
        sprite = assets.sprites[key].copy()
        if enemy.dead:
            sprite.fill((60, 60, 60, 180), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(sprite, (int(rect.x - camera.x), int(rect.y - camera.y)))


def _draw_background(screen: pygame.Surface) -> None:
    width, height = screen.get_size()
    top = (84, 153, 242)
    bottom = (227, 245, 255)
    for y in range(height):
        t = y / max(1, height - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        pygame.draw.line(screen, color, (0, y), (width, y))
