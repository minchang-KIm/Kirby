"""Render the campaign exclusively from immutable content and snapshot values."""

from __future__ import annotations

import math
from dataclasses import replace
from types import MappingProxyType
from typing import Final, cast

import pygame

from windsprig.content.models import StageSpec
from windsprig.gameplay.snapshot import (
    AttackView,
    BossView,
    CameraTargetView,
    CheckpointView,
    EchoPickupView,
    EnemyView,
    InteractionView,
    PlayerView,
    StageSnapshot,
)
from windsprig.localization import Localizer
from windsprig.render.animation import AnimationBank, AnimationCursor
from windsprig.render.assets import AssetCatalog
from windsprig.render.camera import CameraView
from windsprig.render.effects import EffectFrame, Flash, Particle
from windsprig.render.hud import BOSS_PHASE_NUMBER, HudPlayerVM, HudViewModel
from windsprig.render.ui import Color, draw_panel, draw_text

type Number = int | float
type CursorKey = tuple[str, int]
type ScaledFrameKey = tuple[str, int, int, int, bool]

LOGICAL_SIZE: Final = (1280, 720)
RENDER_LAYER_ORDER: Final = (
    "parallax",
    "tiles",
    "interactions",
    "collectibles",
    "checkpoints_and_goal",
    "enemies",
    "bosses",
    "players",
    "attacks_and_echoes",
    "effects",
    "hud",
)

_INK: Final[Color] = (22, 32, 43)
_INK_LIGHT: Final[Color] = (245, 247, 226)
_MINT: Final[Color] = (119, 222, 153)
_GOLD: Final[Color] = (248, 194, 67)
_CYAN: Final[Color] = (112, 222, 232)
_PANEL: Final[Color] = (12, 24, 34, 246)
_SLOT_COLORS: Final = MappingProxyType(
    {
        "mint": (119, 222, 153),
        "gold": (248, 194, 67),
        "violet": (190, 155, 255),
        "cyan": (112, 222, 232),
    }
)
_PLAYER_ICON_BY_TOKEN: Final = MappingProxyType(
    {"leaf": "player_1", "sun": "player_2", "moon": "player_3", "gale": "player_4"}
)
_ICON_FRAME: Final = MappingProxyType(
    {
        "move": 0,
        "jump": 1,
        "hover": 2,
        "draw": 3,
        "release": 4,
        "harmonize": 5,
        "attack": 6,
        "guard": 7,
        "dodge": 8,
        "hurt": 9,
        "defeated": 10,
        "victory": 11,
        "mote": 12,
        "checkpoint": 13,
        "goal": 14,
        "boss": 15,
        "bloomblade": 16,
        "cinder": 17,
        "voltsong": 18,
        "galehook": 19,
        "stoneheart": 20,
        "tempest": 21,
        "player_1": 22,
        "player_2": 23,
        "player_3": 24,
        "player_4": 25,
        "keyboard": 26,
        "gamepad": 27,
        "locked": 28,
        "available": 29,
        "cleared": 30,
        "audio_muted": 31,
    }
)
_INTERACTION_FRAME: Final = MappingProxyType(
    {
        "gust_lift": 0,
        "breakable": 1,
        "conveyor": 0,
        "heat_vent": 1,
        "timed_shutter": 2,
        "current": 0,
        "buoyant_pod": 1,
        "falling_water": 2,
        "rail": 0,
        "conductor": 1,
        "rotating_tower": 2,
        "mirror": 0,
        "color_beam": 1,
        "gravity_bloom": 2,
        "silence_field": 0,
        "ability_lock": 1,
        "breakable_floor": 2,
        "switch": 3,
    }
)
_INTERACTION_STATES: Final = frozenset({"idle", "energized", "activated", "broken"})
_ABILITY_ATTACK: Final = MappingProxyType(
    {
        "bloomblade_arc_1": ("bloomblade", "arc"),
        "bloomblade_arc_2": ("bloomblade", "arc"),
        "bloomblade_arc_3": ("bloomblade", "arc"),
        "cinder_ember": ("cinder", "projectile"),
        "cinder_ember_charged": ("cinder", "projectile"),
        "cinder_burn_zone": ("cinder", "area"),
        "voltsong_chain_pulse": ("voltsong", "pulse"),
        "galehook_boomerang": ("galehook", "return"),
        "stoneheart_ground_slam": ("stoneheart", "ground"),
        "tempest_screen": ("tempest", "screen"),
        "wind_launch": ("release", "launch"),
    }
)
_BOSS_TELEGRAPH: Final = MappingProxyType(
    {
        "rootjaw.burrow_line": "ground",
        "rootjaw.seed_spit": "orbit",
        "rootjaw.root_cage": "arena",
        "rootjaw.bramble_sweep": "silhouette",
        "rootjaw.quake_bloom": "ground",
        "rootjaw.tunnel_feint": "lane",
        "crucible_crab.claw_press": "ground",
        "crucible_crab.slag_cast": "lane",
        "crucible_crab.lane_pour": "lane",
        "crucible_crab.shell_spin": "silhouette",
        "crucible_crab.vent_burst": "ground",
        "crucible_crab.forge_drop": "ground",
        "luma_eel.current_dash": "silhouette",
        "luma_eel.lumen_orbs": "orbit",
        "luma_eel.decoy_flash": "arena",
        "luma_eel.reverse_current": "lane",
        "luma_eel.eclipse_ring": "orbit",
        "luma_eel.spiral_dive": "silhouette",
        "volt_roc.dive_lane": "lane",
        "volt_roc.feather_bolts": "orbit",
        "volt_roc.lightning_chain": "ground",
        "volt_roc.rail_talon": "silhouette",
        "volt_roc.tempest_wall": "arena",
        "volt_roc.thunder_dive": "ground",
        "prism_warden.prism_beam": "beam",
        "prism_warden.mirror_guard": "silhouette",
        "prism_warden.clone_cast": "arena",
        "prism_warden.color_cross": "beam",
        "prism_warden.gravity_shard": "ground",
        "prism_warden.refraction_bloom": "orbit",
        "the_stillness.hush_wave": "arena",
        "the_stillness.locked_echo": "silhouette",
        "the_stillness.system_chain": "arena",
        "the_stillness.prism_lock": "beam",
        "the_stillness.echo_crown": "orbit",
        "the_stillness.final_release": "arena",
    }
)
_PARTICLE_COLOR: Final = MappingProxyType(
    {
        "impact": (255, 236, 165),
        "afterimage": (147, 226, 255),
        "wind_ribbon": (119, 222, 153),
        "leaf": (119, 222, 153),
        "streak": (245, 247, 226),
        "spark": (248, 194, 67),
        "echo": (190, 155, 255),
        "shard": (147, 226, 255),
        "mote": (248, 194, 67),
        "paper": (220, 220, 206),
        "confetti": (255, 143, 196),
    }
)
_EFFECT_COLOR: Final = MappingProxyType(
    {
        "pattern.damage": (255, 132, 109),
        "pattern.dodge": (147, 226, 255),
        "pattern.capture": (119, 222, 153),
        "pattern.release": (119, 222, 153),
        "pattern.launch": (245, 247, 226),
        "pattern.harmonize": (190, 155, 255),
        "pattern.echo": (190, 155, 255),
        "pattern.hit": (255, 236, 165),
        "pattern.cut": (147, 226, 255),
        "pattern.mote": (248, 194, 67),
        "pattern.checkpoint": (119, 222, 153),
        "pattern.defeat": (220, 220, 206),
        "pattern.respawn": (112, 222, 232),
        "pattern.goal": (119, 222, 153),
        "pattern.victory": (255, 143, 196),
        "pattern.boss": (255, 132, 109),
        **{f"pattern.{kind}": color for kind, color in _PARTICLE_COLOR.items()},
    }
)


def _finite(name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise TypeError(f"{name} must be a number")
    result = float(cast(Number, value))
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _strict_int(name: str, value: object, *, minimum: int = 0) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _stable_id(name: str, value: object) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


def _facing(value: object) -> int:
    if type(value) is not int:
        raise TypeError("facing must be an integer")
    if value not in {-1, 1}:
        raise ValueError("facing must be -1 or 1")
    return value


def _world_rect(
    x: Number,
    y: Number,
    width: int,
    height: int,
    camera: CameraView,
) -> pygame.Rect:
    screen_x = _finite("world x", x) - camera.x + camera.shake_x
    screen_y = _finite("world y", y) - camera.y + camera.shake_y
    validated_width = _strict_int("world width", width, minimum=1)
    validated_height = _strict_int("world height", height, minimum=1)
    return pygame.Rect(round(screen_x), round(screen_y), validated_width, validated_height)


def _is_visible(rect: pygame.Rect, canvas: pygame.Surface) -> bool:
    return rect.colliderect(canvas.get_rect().inflate(160, 160))


def _pattern_for(token: str) -> str:
    stable = _stable_id("pattern token", token)
    if stable.startswith("pattern.slot-"):
        slot_text = stable.removeprefix("pattern.slot-")
        if slot_text in {"1", "4"}:
            return "hatch"
        if slot_text == "2":
            return "dots"
        if slot_text == "3":
            return "stripes"
    if stable.startswith("pattern.boss."):
        state = stable.removeprefix("pattern.boss.")
        return {"vulnerable": "dots", "armored": "hatch", "hidden": "stripes", "invulnerable": "hatch"}.get(
            state,
            "",
        )
    raise ValueError(f"unsupported HUD pattern token: {stable}")


class StageRenderer:
    """Own bounded render caches and draw only explicit immutable presentation inputs."""

    MAX_SCALED_CACHE: Final = 256

    def __init__(self, assets: AssetCatalog, animations: AnimationBank, tr: Localizer) -> None:
        if not isinstance(assets, AssetCatalog):
            raise TypeError("assets must be an AssetCatalog")
        if not isinstance(animations, AnimationBank):
            raise TypeError("animations must be an AnimationBank")
        if not isinstance(tr, Localizer):
            raise TypeError("tr must be a Localizer")
        self.assets = assets
        self.animations = animations
        self.tr = tr
        self.cursors: dict[CursorKey, AnimationCursor] = {}
        self._scaled_frames: dict[ScaledFrameKey, pygame.Surface] = {}
        self._parallax_layers: dict[tuple[str, int], pygame.Surface] = {}

    def _validate_render(
        self,
        canvas: pygame.Surface,
        stage: StageSpec,
        snapshot: StageSnapshot,
        camera: CameraView,
        hud: HudViewModel,
        effects: EffectFrame,
        render_dt_ms: int,
    ) -> None:
        if not isinstance(canvas, pygame.Surface):
            raise TypeError("canvas must be a pygame.Surface")
        if canvas.get_size() != LOGICAL_SIZE:
            raise ValueError("stage renderer requires a 1280x720 logical canvas")
        if not isinstance(stage, StageSpec):
            raise TypeError("stage must be a StageSpec")
        if not isinstance(snapshot, StageSnapshot):
            raise TypeError("snapshot must be a StageSnapshot")
        if not isinstance(camera, CameraView):
            raise TypeError("camera must be a CameraView")
        if not isinstance(hud, HudViewModel):
            raise TypeError("hud must be a HudViewModel")
        if not isinstance(effects, EffectFrame):
            raise TypeError("effects must be an EffectFrame")
        _strict_int("render delta", render_dt_ms)
        if (snapshot.stage_id, snapshot.world_id, snapshot.node_id) != (stage.stage_id, stage.world_id, stage.node_id):
            raise ValueError("snapshot identity does not match stage identity")
        if stage.world_id not in {f"world_{index}" for index in range(1, 7)}:
            raise ValueError(f"unsupported release world ID: {stage.world_id}")
        _strict_int("stage tile size", stage.tile_size, minimum=1)
        _strict_int("snapshot frame index", snapshot.frame_index)
        _strict_int("snapshot elapsed time", snapshot.elapsed_ms)
        if type(snapshot.players) is not tuple or any(not isinstance(item, PlayerView) for item in snapshot.players):
            raise TypeError("snapshot players must be a tuple of PlayerView values")
        if type(snapshot.enemies) is not tuple or any(not isinstance(item, EnemyView) for item in snapshot.enemies):
            raise TypeError("snapshot enemies must be a tuple of EnemyView values")
        if type(snapshot.attacks) is not tuple or any(not isinstance(item, AttackView) for item in snapshot.attacks):
            raise TypeError("snapshot attacks must be a tuple of AttackView values")
        if type(snapshot.echo_pickups) is not tuple or any(
            not isinstance(item, EchoPickupView) for item in snapshot.echo_pickups
        ):
            raise TypeError("snapshot echo pickups must be a tuple of EchoPickupView values")
        if type(snapshot.interactions) is not tuple or any(
            not isinstance(item, InteractionView) for item in snapshot.interactions
        ):
            raise TypeError("snapshot interactions must be a tuple of InteractionView values")
        if type(snapshot.checkpoints) is not tuple or any(
            not isinstance(item, CheckpointView) for item in snapshot.checkpoints
        ):
            raise TypeError("snapshot checkpoints must be a tuple of CheckpointView values")
        if type(snapshot.camera_targets) is not tuple or any(
            not isinstance(item, CameraTargetView) for item in snapshot.camera_targets
        ):
            raise TypeError("snapshot camera targets must be a tuple of CameraTargetView values")
        if type(snapshot.bosses) is not tuple or any(not isinstance(item, BossView) for item in snapshot.bosses):
            raise TypeError("snapshot bosses must be a tuple of BossView values")
        if len(snapshot.bosses) > 1:
            raise ValueError("stage renderer supports exactly one authored boss encounter")
        entity_ids = tuple(
            item.entity_id
            for collection in (
                snapshot.players,
                snapshot.enemies,
                snapshot.attacks,
                snapshot.echo_pickups,
                snapshot.interactions,
                snapshot.bosses,
            )
            for item in collection
        )
        if any(type(entity_id) is not int or entity_id <= 0 for entity_id in entity_ids):
            raise ValueError("render entity IDs must be positive integers")
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("render entity IDs must be globally unique")
        snapshot_slots = tuple(sorted(player.slot for player in snapshot.players))
        if snapshot_slots != tuple(player.slot for player in hud.players):
            raise ValueError("HUD player slots must match snapshot player slots")

    def _camera_with_effect_shake(
        self,
        camera: CameraView,
        effects: EffectFrame,
        frame_index: int,
    ) -> CameraView:
        if effects.shake is None:
            return camera
        pattern = ((-1.0, 0.0), (1.0, -0.75), (0.0, 1.0), (-0.5, 0.5))
        # Remaining lifetime is render-owned time, so shake still animates on
        # display frames where the deterministic simulation index is unchanged.
        unit_x, unit_y = pattern[(effects.shake.duration_ms // 16) % len(pattern)]
        return replace(
            camera,
            shake_x=camera.shake_x + unit_x * effects.shake.amplitude_px,
            shake_y=camera.shake_y + unit_y * effects.shake.amplitude_px,
        )

    def render(
        self,
        canvas: pygame.Surface,
        stage: StageSpec,
        snapshot: StageSnapshot,
        camera: CameraView,
        hud: HudViewModel,
        effects: EffectFrame,
        render_dt_ms: int,
    ) -> None:
        """Draw one frame in fixed layer order and advance each live cursor once."""

        self._validate_render(canvas, stage, snapshot, camera, hud, effects, render_dt_ms)
        draw_camera = self._camera_with_effect_shake(camera, effects, snapshot.frame_index)
        self._draw_parallax(canvas, stage, draw_camera)
        self._draw_tiles(canvas, stage, draw_camera)
        self._draw_interactions(canvas, snapshot.interactions, stage.world_id, draw_camera)
        self._draw_collectibles(canvas, stage, snapshot.collected_mote_ids, draw_camera)
        self._draw_checkpoints_and_goal(canvas, snapshot, draw_camera)
        self._draw_enemies(canvas, snapshot.enemies, draw_camera, render_dt_ms)
        self._draw_bosses(canvas, snapshot.bosses, draw_camera, render_dt_ms)
        self._draw_players(canvas, snapshot.players, draw_camera, render_dt_ms)
        self._draw_attacks_and_echoes(canvas, snapshot.attacks, snapshot.echo_pickups, draw_camera)
        self._draw_effects(canvas, effects, draw_camera)
        self._draw_hud(canvas, hud)

        live_keys = {
            *(("player", player.entity_id) for player in snapshot.players),
            *(("enemy", enemy.entity_id) for enemy in snapshot.enemies),
            *(("boss", boss.entity_id) for boss in snapshot.bosses),
        }
        for stale_key in sorted(set(self.cursors) - live_keys):
            del self.cursors[stale_key]

    def _scaled_frame(
        self,
        asset_id: str,
        frame_index: int,
        size: tuple[int, int],
        *,
        flip_x: bool = False,
    ) -> pygame.Surface:
        width, height = size
        _strict_int("scaled frame width", width, minimum=1)
        _strict_int("scaled frame height", height, minimum=1)
        if type(flip_x) is not bool:
            raise TypeError("frame flip must be a boolean")
        key = (asset_id, frame_index, width, height, flip_x)
        cached = self._scaled_frames.get(key)
        if cached is not None:
            return cached
        source = self.assets.frame(asset_id, frame_index)
        scaled = pygame.transform.smoothscale(source, size)
        if flip_x:
            scaled = pygame.transform.flip(scaled, True, False)
        if len(self._scaled_frames) >= self.MAX_SCALED_CACHE:
            # FIFO eviction bounds a long soak even if authored dimensions vary.
            del self._scaled_frames[next(iter(self._scaled_frames))]
        self._scaled_frames[key] = scaled
        return scaled

    def _icon(self, icon_id: str, size: int = 32) -> pygame.Surface:
        stable = _stable_id("icon ID", icon_id)
        frame_index = _ICON_FRAME.get(stable)
        if frame_index is None:
            raise ValueError(f"unsupported UI icon ID: {stable}")
        return self._scaled_frame("ui.icons", frame_index, (size, size))

    def _cursor(self, kind: str, entity_id: int, actor_state: str, dt_ms: int) -> AnimationCursor:
        key = (_stable_id("cursor kind", kind), _strict_int("cursor entity ID", entity_id, minimum=1))
        clip = self.animations.clip_for(actor_state)
        current = self.cursors.get(key)
        if current is None or current.clip is not clip:
            current = AnimationCursor.start(clip)
        advanced, _markers = current.advance(dt_ms)
        self.cursors[key] = advanced
        return advanced

    def _draw_parallax(self, canvas: pygame.Surface, stage: StageSpec, camera: CameraView) -> None:
        asset_id = f"world.{stage.world_id}.background"
        canvas.fill(_INK)
        for layer_index, factor in enumerate((0.08, 0.16, 0.28, 0.42)):
            cache_key = (stage.world_id, layer_index)
            layer = self._parallax_layers.get(cache_key)
            if layer is None:
                layer = self.assets.frame(asset_id, layer_index).copy()
                if layer_index:
                    layer.set_alpha(45 + layer_index * 22)
                self._parallax_layers[cache_key] = layer
            offset_x = -round((camera.x * factor) % LOGICAL_SIZE[0]) + round(camera.shake_x)
            offset_y = round(camera.shake_y - camera.y * factor * 0.08)
            canvas.blit(layer, (offset_x, offset_y))
            canvas.blit(layer, (offset_x + LOGICAL_SIZE[0], offset_y))

    def _draw_tile_group(
        self,
        canvas: pygame.Surface,
        tiles: tuple[tuple[int, int], ...],
        stage: StageSpec,
        camera: CameraView,
        frame_index: int,
    ) -> None:
        asset_id = f"world.{stage.world_id}.tiles"
        tile_size = stage.tile_size
        for tile_x, tile_y in tiles:
            if type(tile_x) is not int or type(tile_y) is not int:
                raise TypeError("stage tile coordinates must be integers")
            rect = _world_rect(tile_x * tile_size, tile_y * tile_size, tile_size, tile_size, camera)
            if _is_visible(rect, canvas):
                canvas.blit(self._scaled_frame(asset_id, frame_index, rect.size), rect)

    def _draw_tiles(self, canvas: pygame.Surface, stage: StageSpec, camera: CameraView) -> None:
        self._draw_tile_group(canvas, stage.solids, stage, camera, 0)
        self._draw_tile_group(canvas, stage.one_way_tiles, stage, camera, 1)
        self._draw_tile_group(canvas, stage.hazards, stage, camera, 2)

    def _draw_interactions(
        self,
        canvas: pygame.Surface,
        interactions: tuple[InteractionView, ...],
        world_id: str,
        camera: CameraView,
    ) -> None:
        for interaction in sorted(interactions, key=lambda item: item.entity_id):
            frame_index = _INTERACTION_FRAME.get(interaction.interaction_kind)
            if frame_index is None:
                raise ValueError(f"unsupported interaction kind: {interaction.interaction_kind}")
            if interaction.interaction_state not in _INTERACTION_STATES:
                raise ValueError(f"unsupported interaction state: {interaction.interaction_state}")
            _stable_id("interaction ID", interaction.interaction_id)
            rect = _world_rect(
                interaction.x,
                interaction.y,
                interaction.width,
                interaction.height,
                camera,
            )
            if not _is_visible(rect, canvas):
                continue
            canvas.blit(
                self._scaled_frame(f"world.{world_id}.props", frame_index, rect.size),
                rect,
            )
            if interaction.interaction_state == "energized":
                pygame.draw.circle(canvas, _GOLD, rect.center, max(6, min(rect.size) // 4), 3)
            elif interaction.interaction_state == "activated":
                pygame.draw.rect(canvas, _MINT, rect, 4, border_radius=8)
                pygame.draw.line(canvas, _INK_LIGHT, rect.midleft, rect.midright, 3)
            elif interaction.interaction_state == "broken":
                pygame.draw.line(canvas, _INK_LIGHT, rect.topleft, rect.bottomright, 4)
                pygame.draw.line(canvas, _INK_LIGHT, rect.topright, rect.bottomleft, 4)
            else:
                pygame.draw.rect(canvas, _INK, rect, 2, border_radius=8)

    def _draw_collectibles(
        self,
        canvas: pygame.Surface,
        stage: StageSpec,
        collected_mote_ids: tuple[str, ...],
        camera: CameraView,
    ) -> None:
        if type(collected_mote_ids) is not tuple:
            raise TypeError("collected mote IDs must be a tuple")
        collected = frozenset(collected_mote_ids)
        for mote in stage.motes:
            if mote.mote_id in collected:
                continue
            center_x = mote.tile_x * stage.tile_size + stage.tile_size // 2
            center_y = mote.tile_y * stage.tile_size + stage.tile_size // 2
            rect = _world_rect(center_x - 18, center_y - 18, 36, 36, camera)
            if _is_visible(rect, canvas):
                canvas.blit(self._icon("mote", 36), rect)
                pygame.draw.circle(canvas, _GOLD, rect.center, 20, 2)

    def _draw_checkpoints_and_goal(
        self,
        canvas: pygame.Surface,
        snapshot: StageSnapshot,
        camera: CameraView,
    ) -> None:
        for checkpoint in sorted(snapshot.checkpoints, key=lambda item: item.checkpoint_id):
            _stable_id("checkpoint ID", checkpoint.checkpoint_id)
            if type(checkpoint.is_active) is not bool:
                raise TypeError("checkpoint active state must be a boolean")
            rect = _world_rect(checkpoint.x - 20, checkpoint.y - 40, 40, 40, camera)
            if not _is_visible(rect, canvas):
                continue
            canvas.blit(self._icon("checkpoint", 40), rect)
            if checkpoint.is_active:
                pygame.draw.circle(canvas, _MINT, rect.center, 23, 4)
                pygame.draw.line(canvas, _INK_LIGHT, rect.midleft, rect.midright, 2)
            else:
                for angle in range(0, 360, 45):
                    point = (
                        rect.centerx + round(math.cos(math.radians(angle)) * 23),
                        rect.centery + round(math.sin(math.radians(angle)) * 23),
                    )
                    pygame.draw.circle(canvas, _INK_LIGHT, point, 2)
        gather = snapshot.goal_gather
        goal_rect = _world_rect(gather.goal_x - 24, gather.goal_y - 48, 48, 48, camera)
        if _is_visible(goal_rect, canvas):
            canvas.blit(self._icon("goal", 48), goal_rect)
            pygame.draw.rect(canvas, _GOLD, goal_rect.inflate(8, 8), 3, border_radius=18)
            for index, _slot in enumerate(gather.at_goal_slots):
                pygame.draw.circle(canvas, _MINT, (goal_rect.left + 8 + index * 10, goal_rect.bottom + 8), 4)

    def _draw_enemies(
        self,
        canvas: pygame.Surface,
        enemies: tuple[EnemyView, ...],
        camera: CameraView,
        render_dt_ms: int,
    ) -> None:
        for enemy in sorted(enemies, key=lambda item: item.entity_id):
            _stable_id("enemy kind", enemy.enemy_kind)
            facing = _facing(enemy.facing)
            cursor = self._cursor("enemy", enemy.entity_id, enemy.actor_state, render_dt_ms)
            frame_index = cursor.frame_index % self.assets.frame_count(f"enemy.{enemy.enemy_kind}")
            sprite_width = max(64, _strict_int("enemy width", enemy.width, minimum=1) + 24)
            sprite_height = max(64, _strict_int("enemy height", enemy.height, minimum=1) + 20)
            rect = _world_rect(
                enemy.x + enemy.width / 2 - sprite_width / 2,
                enemy.y + enemy.height - sprite_height,
                sprite_width,
                sprite_height,
                camera,
            )
            if not _is_visible(rect, canvas):
                continue
            sprite = self._scaled_frame(
                f"enemy.{enemy.enemy_kind}",
                frame_index,
                rect.size,
                flip_x=facing < 0,
            )
            if enemy.captured_by is not None:
                _strict_int("capturing player ID", enemy.captured_by, minimum=1)
                captured = sprite.copy()
                captured.set_alpha(120)
                canvas.blit(captured, rect)
                pygame.draw.circle(canvas, _CYAN, rect.center, max(rect.width, rect.height) // 2, 4)
            else:
                canvas.blit(sprite, rect)
            maximum_hp = _strict_int("enemy maximum HP", enemy.maximum_hp, minimum=1)
            hp = _strict_int("enemy HP", enemy.hp)
            if hp > maximum_hp:
                raise ValueError("enemy HP cannot exceed maximum HP")
            bar = pygame.Rect(rect.left, rect.top - 8, rect.width, 5)
            pygame.draw.rect(canvas, _INK, bar)
            pygame.draw.rect(canvas, _MINT, (bar.left, bar.top, round(bar.width * hp / maximum_hp), bar.height))

    def _draw_telegraph(self, canvas: pygame.Surface, marker: str, rect: pygame.Rect) -> None:
        ground = pygame.Rect(rect.left - 30, rect.bottom - 12, rect.width + 60, 24)
        if marker in {"ground", "lane"}:
            pygame.draw.rect(canvas, _GOLD, ground, 4, border_radius=8)
            for x in range(ground.left + 8, ground.right, 18):
                pygame.draw.line(canvas, _INK_LIGHT, (x, ground.top + 3), (x + 8, ground.bottom - 3), 2)
        elif marker == "orbit":
            pygame.draw.circle(canvas, _GOLD, rect.center, max(rect.width, rect.height) // 2 + 24, 4)
            pygame.draw.circle(canvas, _INK_LIGHT, rect.center, max(rect.width, rect.height) // 2 + 10, 2)
        elif marker == "beam":
            pygame.draw.line(canvas, _GOLD, (0, rect.centery), (LOGICAL_SIZE[0], rect.centery), 7)
            pygame.draw.line(canvas, _INK_LIGHT, (0, rect.centery), (LOGICAL_SIZE[0], rect.centery), 2)
        elif marker == "arena":
            pygame.draw.rect(canvas, _GOLD, canvas.get_rect().inflate(-80, -80), 4, border_radius=32)
        elif marker == "silhouette":
            pygame.draw.polygon(
                canvas,
                _GOLD,
                (rect.midtop, rect.topright, rect.midright, rect.midbottom, rect.midleft, rect.topleft),
                4,
            )
        else:
            raise ValueError(f"unsupported boss telegraph marker: {marker}")

    def _draw_bosses(
        self,
        canvas: pygame.Surface,
        bosses: tuple[BossView, ...],
        camera: CameraView,
        render_dt_ms: int,
    ) -> None:
        for boss in sorted(bosses, key=lambda item: item.entity_id):
            phase_number = BOSS_PHASE_NUMBER.get(boss.phase_id)
            if phase_number is None:
                raise ValueError(f"unsupported boss phase ID: {boss.phase_id}")
            facing = _facing(boss.facing)
            cursor = self._cursor("boss", boss.entity_id, boss.actor_state, render_dt_ms)
            frame_index = (phase_number - 1) * 6 + cursor.frame_index % 6
            sprite_width = max(128, _strict_int("boss width", boss.width, minimum=1))
            sprite_height = max(128, _strict_int("boss height", boss.height, minimum=1))
            rect = _world_rect(
                boss.x + boss.width / 2 - sprite_width / 2,
                boss.y + boss.height - sprite_height,
                sprite_width,
                sprite_height,
                camera,
            )
            if boss.telegraph_id is not None:
                marker = _BOSS_TELEGRAPH.get(boss.telegraph_id)
                if marker is None:
                    raise ValueError(f"unsupported boss telegraph ID: {boss.telegraph_id}")
                _strict_int("boss telegraph remaining time", boss.telegraph_remaining_ms)
                self._draw_telegraph(canvas, marker, rect)
            if not _is_visible(rect, canvas):
                continue
            sprite = self._scaled_frame(
                f"boss.{boss.boss_id}",
                frame_index,
                rect.size,
                flip_x=facing < 0,
            )
            if boss.vulnerability_state == "hidden":
                faded = sprite.copy()
                faded.set_alpha(110)
                canvas.blit(faded, rect)
            else:
                canvas.blit(sprite, rect)
            outline_width = {"vulnerable": 2, "armored": 6, "hidden": 2, "invulnerable": 5}.get(
                boss.vulnerability_state
            )
            if outline_width is None:
                raise ValueError(f"unsupported boss vulnerability: {boss.vulnerability_state}")
            pygame.draw.rect(canvas, _GOLD, rect.inflate(8, 8), outline_width, border_radius=20)
            if boss.vulnerability_state in {"armored", "invulnerable"}:
                for y in range(rect.top, rect.bottom, 14):
                    pygame.draw.line(canvas, _INK_LIGHT, (rect.left, y), (rect.right, y + 8), 2)

    def _draw_players(
        self,
        canvas: pygame.Surface,
        players: tuple[PlayerView, ...],
        camera: CameraView,
        render_dt_ms: int,
    ) -> None:
        for player in sorted(players, key=lambda item: (item.slot, item.entity_id)):
            slot = _strict_int("player slot", player.slot, minimum=1)
            if slot > 4:
                raise ValueError("player slot must be in [1, 4]")
            facing = _facing(player.facing)
            cursor = self._cursor("player", player.entity_id, player.actor_state, render_dt_ms)
            sprite_width = max(76, _strict_int("player width", player.width, minimum=1) + 30)
            sprite_height = max(84, _strict_int("player height", player.height, minimum=1) + 26)
            rect = _world_rect(
                player.x + player.width / 2 - sprite_width / 2,
                player.y + player.height - sprite_height,
                sprite_width,
                sprite_height,
                camera,
            )
            if not _is_visible(rect, canvas):
                continue
            slot_color = tuple(_SLOT_COLORS.values())[slot - 1]
            pygame.draw.ellipse(canvas, slot_color, rect.inflate(10, 6), 5)
            canvas.blit(
                self._scaled_frame(
                    "player.sprig",
                    cursor.frame_id,
                    rect.size,
                    flip_x=facing < 0,
                ),
                rect,
            )
            canvas.blit(self._icon(f"player_{slot}", 24), (rect.left - 4, rect.top - 4))
            if player.invulnerable:
                for offset in range(0, rect.width + rect.height, 12):
                    pygame.draw.line(
                        canvas,
                        _INK_LIGHT,
                        (rect.left + max(0, offset - rect.height), rect.bottom - min(offset, rect.height)),
                        (rect.left + min(offset, rect.width), rect.bottom - max(0, offset - rect.width)),
                        2,
                    )
            if player.captured_visual_id is not None:
                pygame.draw.circle(canvas, _CYAN, (rect.centerx, rect.top - 12), 12, 3)

    def _attack_mapping(self, attack: AttackView) -> tuple[str, str]:
        mapped = _ABILITY_ATTACK.get(attack.visual_id)
        if mapped is not None:
            return mapped
        marker = _BOSS_TELEGRAPH.get(attack.visual_id)
        if marker is not None:
            return "boss", marker
        raise ValueError(f"unsupported attack visual ID: {attack.visual_id}")

    def _draw_attack(self, canvas: pygame.Surface, attack: AttackView, camera: CameraView) -> None:
        _strict_int("attack owner entity ID", attack.owner_entity_id, minimum=1)
        _stable_id("attack kind", attack.attack_kind)
        _stable_id("attack visual ID", attack.visual_id)
        _strict_int("attack TTL", attack.ttl_ms)
        facing = _facing(attack.facing)
        icon_id, style = self._attack_mapping(attack)
        rect = _world_rect(attack.x, attack.y, attack.width, attack.height, camera)
        if not _is_visible(rect, canvas):
            return
        if style == "arc":
            pygame.draw.arc(
                canvas,
                _MINT,
                rect.inflate(22, 22),
                -1.2 if facing > 0 else 1.9,
                1.2 if facing > 0 else 4.3,
                8,
            )
        elif style == "projectile":
            pygame.draw.ellipse(canvas, (255, 112, 63), rect.inflate(10, 6))
            pygame.draw.line(canvas, _GOLD, rect.midleft, rect.midright, 3)
        elif style in {"area", "ground", "screen", "arena"}:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((190, 155, 255, 72) if style == "screen" else (255, 112, 63, 74))
            for x in range(-rect.height, rect.width, 14):
                pygame.draw.line(overlay, (*_INK_LIGHT[:3], 130), (x, rect.height), (x + rect.height, 0), 2)
            canvas.blit(overlay, rect)
            pygame.draw.rect(canvas, _GOLD, rect, 3, border_radius=10)
        elif style == "pulse":
            for inset in (0, 10, 20):
                candidate = rect.inflate(-inset, -inset)
                if candidate.width > 0 and candidate.height > 0:
                    pygame.draw.ellipse(canvas, _GOLD, candidate, 3)
        elif style == "return":
            pygame.draw.arc(canvas, _CYAN, rect.inflate(16, 16), 0.2, 5.8, 5)
            pygame.draw.polygon(
                canvas,
                _INK_LIGHT,
                (rect.midleft, (rect.left + 10, rect.top), (rect.left + 14, rect.centery)),
            )
        elif style == "launch":
            for offset in (-8, 0, 8):
                start = (rect.left - facing * 28, rect.centery + offset)
                end = (rect.right + facing * 8, rect.centery + offset)
                pygame.draw.line(canvas, _CYAN, start, end, 4)
        elif style in {"lane", "orbit", "beam", "silhouette"}:
            self._draw_telegraph(canvas, style, rect)
        else:
            raise ValueError(f"unsupported attack visual style: {style}")
        icon_size = max(18, min(34, rect.width, rect.height))
        canvas.blit(self._icon(icon_id, icon_size), (rect.centerx - icon_size // 2, rect.centery - icon_size // 2))

    def _draw_attacks_and_echoes(
        self,
        canvas: pygame.Surface,
        attacks: tuple[AttackView, ...],
        echo_pickups: tuple[EchoPickupView, ...],
        camera: CameraView,
    ) -> None:
        for attack in sorted(attacks, key=lambda item: item.entity_id):
            self._draw_attack(canvas, attack, camera)
        for echo in sorted(echo_pickups, key=lambda item: item.entity_id):
            if echo.ability_id not in {"bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest"}:
                raise ValueError(f"unsupported echo ability ID: {echo.ability_id}")
            rect = _world_rect(echo.x - 22, echo.y - 22, 44, 44, camera)
            if _is_visible(rect, canvas):
                pygame.draw.circle(canvas, _CYAN, rect.center, 24, 4)
                pygame.draw.circle(canvas, _INK_LIGHT, rect.center, 18, 2)
                canvas.blit(self._icon(echo.ability_id, 32), (rect.centerx - 16, rect.centery - 16))

    def _draw_flash(self, canvas: pygame.Surface, flash: Flash, camera: CameraView) -> None:
        center_x = round(flash.x - camera.x + camera.shake_x)
        center_y = round(flash.y - camera.y + camera.shake_y)
        color = _EFFECT_COLOR.get(flash.pattern_token)
        if color is None:
            raise ValueError(f"unsupported flash pattern token: {flash.pattern_token}")
        width = max(1, min(5, math.ceil(flash.duration_ms / 24)))
        pygame.draw.circle(canvas, _INK_LIGHT, (center_x, center_y), flash.radius_px, width)
        if flash.pattern_token == "pattern.mote":
            pygame.draw.circle(canvas, color, (center_x, center_y), max(3, flash.radius_px // 2), width)
            for offset_x, offset_y in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                endpoint = (
                    center_x + offset_x * flash.radius_px,
                    center_y + offset_y * flash.radius_px,
                )
                pygame.draw.circle(canvas, color, endpoint, width + 1)
        elif flash.pattern_token == "pattern.harmonize":
            radius = flash.radius_px
            pygame.draw.polygon(
                canvas,
                color,
                (
                    (center_x, center_y - radius),
                    (center_x + radius, center_y),
                    (center_x, center_y + radius),
                    (center_x - radius, center_y),
                ),
                width,
            )
        else:
            pygame.draw.line(
                canvas,
                color,
                (center_x - flash.radius_px, center_y),
                (center_x + flash.radius_px, center_y),
                width,
            )
            pygame.draw.line(
                canvas,
                color,
                (center_x, center_y - flash.radius_px),
                (center_x, center_y + flash.radius_px),
                width,
            )

    def _draw_particle(self, canvas: pygame.Surface, particle: Particle, camera: CameraView) -> None:
        if particle.kind not in _PARTICLE_COLOR:
            raise ValueError(f"unsupported particle kind: {particle.kind}")
        color = _EFFECT_COLOR.get(particle.color_token)
        if color is None:
            raise ValueError(f"unsupported particle color token: {particle.color_token}")
        x = round(particle.x - camera.x + camera.shake_x)
        y = round(particle.y - camera.y + camera.shake_y)
        radius = max(2, min(7, math.ceil(particle.life_ms / 45)))
        if particle.kind in {"streak", "wind_ribbon", "afterimage"}:
            pygame.draw.line(
                canvas,
                color,
                (x, y),
                (x - round(particle.vx * 0.05), y - round(particle.vy * 0.05)),
                max(2, radius - 1),
            )
        elif particle.kind in {"leaf", "paper", "confetti", "shard"}:
            pygame.draw.polygon(
                canvas,
                color,
                ((x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)),
            )
        elif particle.kind == "spark":
            pygame.draw.line(canvas, color, (x - radius, y), (x + radius, y), 2)
            pygame.draw.line(canvas, color, (x, y - radius), (x, y + radius), 2)
        elif particle.kind == "mote":
            pygame.draw.circle(canvas, color, (x, y), radius, 2)
        else:
            pygame.draw.circle(canvas, color, (x, y), radius)

    def _draw_effects(self, canvas: pygame.Surface, effects: EffectFrame, camera: CameraView) -> None:
        if effects.flash is not None:
            self._draw_flash(canvas, effects.flash, camera)
        for particle in effects.particles:
            self._draw_particle(canvas, particle, camera)

    def _draw_meter(
        self,
        canvas: pygame.Surface,
        rect: pygame.Rect,
        ratio: float,
        color: Color,
        *,
        pattern: str,
    ) -> None:
        if not 0.0 <= ratio <= 1.0 or not math.isfinite(ratio):
            raise ValueError("HUD meter ratio must be finite and in [0, 1]")
        pygame.draw.rect(canvas, _INK, rect, border_radius=3)
        fill = pygame.Rect(rect.left, rect.top, round(rect.width * ratio), rect.height)
        if fill.width:
            pygame.draw.rect(canvas, color, fill, border_radius=3)
            if pattern == "dots":
                for x in range(fill.left + 4, fill.right, 8):
                    pygame.draw.circle(canvas, _INK, (x, fill.centery), 1)
            elif pattern == "stripes":
                for x in range(fill.left, fill.right, 8):
                    pygame.draw.line(canvas, _INK, (x, fill.bottom), (x + 5, fill.top), 1)
            else:
                for x in range(fill.left, fill.right, 10):
                    pygame.draw.line(canvas, _INK, (x, fill.top), (x + 4, fill.bottom), 1)
        pygame.draw.rect(canvas, _INK_LIGHT, rect, 1, border_radius=3)

    def _draw_player_hud(self, canvas: pygame.Surface, player: HudPlayerVM, rect: pygame.Rect) -> None:
        color = _SLOT_COLORS.get(player.color_token)
        if color is None:
            raise ValueError(f"unsupported player color token: {player.color_token}")
        icon_id = _PLAYER_ICON_BY_TOKEN.get(player.icon_token)
        if icon_id is None:
            raise ValueError(f"unsupported player icon token: {player.icon_token}")
        pattern = _pattern_for(player.pattern_token)
        body_font = self.assets.font(17, 700)
        small_font = self.assets.font(14, 500)
        draw_panel(
            canvas,
            rect,
            fill=_PANEL,
            outline=color,
            pattern_token=pattern,
            icon=self._icon(icon_id, 32),
            label=f"{player.label}  {player.hp_label}",
            font=body_font,
            foreground=_INK_LIGHT,
            font_size_px=17,
            label_anchor="top",
        )
        segment_width = 12
        for index, filled in enumerate(player.hp_segments):
            segment = pygame.Rect(rect.left + 48 + index * (segment_width + 3), rect.top + 31, segment_width, 7)
            pygame.draw.rect(canvas, color if filled else _INK, segment, border_radius=2)
            pygame.draw.rect(canvas, _INK_LIGHT, segment, 1, border_radius=2)
        draw_text(
            canvas,
            small_font,
            player.ability_label,
            (rect.left + 78, rect.top + 43),
            foreground=_INK_LIGHT,
            background=_PANEL,
            size_px=14,
        )
        canvas.blit(self._icon(player.ability_icon, 24), (rect.left + 48, rect.top + 40))
        draw_text(
            canvas,
            small_font,
            player.lives_label,
            (rect.left + 184, rect.top + 43),
            foreground=_INK_LIGHT,
            background=_PANEL,
            size_px=14,
        )
        self._draw_meter(
            canvas,
            pygame.Rect(rect.left + 48, rect.top + 62, rect.width - 60, 8),
            player.ability_meter_ratio,
            _GOLD,
            pattern=pattern,
        )
        draw_text(
            canvas,
            small_font,
            player.hover_label,
            (rect.left + 48, rect.top + 74),
            foreground=_INK_LIGHT,
            background=_PANEL,
            size_px=14,
        )
        self._draw_meter(
            canvas,
            pygame.Rect(rect.left + 48, rect.top + 94, rect.width - 60, 7),
            player.hover_ratio,
            _CYAN,
            pattern=pattern,
        )
        status_icon = player.captured_icon
        if status_icon is None and player.dodge_active:
            status_icon = "dodge"
        elif status_icon is None and player.guard_active:
            status_icon = "guard"
        if status_icon is not None:
            canvas.blit(self._icon(status_icon, 22), (rect.left + 8, rect.bottom - 28))
        detail = player.captured_label or " · ".join(player.status_labels)
        if detail:
            draw_text(
                canvas,
                small_font,
                detail,
                (rect.left + 36, rect.bottom - 26),
                foreground=_INK_LIGHT,
                background=_PANEL,
                size_px=14,
            )
        if player.invulnerable_pattern:
            for x in range(rect.left + 4, rect.right - 4, 12):
                pygame.draw.line(canvas, _INK_LIGHT, (x, rect.top + 3), (x + 6, rect.top + 9), 2)

    def _draw_hud(self, canvas: pygame.Surface, hud: HudViewModel) -> None:
        margin = 8
        gap = 8
        panel_width = (LOGICAL_SIZE[0] - margin * 2 - gap * 3) // 4
        for index, player in enumerate(hud.players):
            rect = pygame.Rect(margin + index * (panel_width + gap), margin, panel_width, 130)
            self._draw_player_hud(canvas, player, rect)

        if hud.boss is not None:
            boss_rect = pygame.Rect(330, 150, 620, 72)
            boss_label = f"{hud.boss.name} · {hud.boss.phase_label}"
            if hud.boss.telegraph_label is not None:
                boss_label = f"{boss_label} · {hud.boss.telegraph_label}"
            draw_panel(
                canvas,
                boss_rect,
                fill=_PANEL,
                outline=_GOLD,
                pattern_token=hud.boss.telegraph_pattern or _pattern_for(hud.boss.vulnerability_pattern),
                icon=self._icon(hud.boss.telegraph_icon or "boss", 36),
                label=boss_label,
                font=self.assets.font(20, 700),
                foreground=_INK_LIGHT,
                font_size_px=20,
            )
            self._draw_meter(
                canvas,
                pygame.Rect(boss_rect.left + 54, boss_rect.bottom - 16, boss_rect.width - 68, 10),
                hud.boss.hp_ratio,
                _GOLD,
                pattern=_pattern_for(hud.boss.vulnerability_pattern),
            )

        if hud.gather_label is not None:
            gather_rect = pygame.Rect(500, 234, 280, 54)
            draw_panel(
                canvas,
                gather_rect,
                fill=_PANEL,
                outline=_GOLD,
                pattern_token="hatch",
                icon=self._icon("goal", 30),
                label=hud.gather_label,
                font=self.assets.font(18, 700),
                foreground=_INK_LIGHT,
                font_size_px=18,
            )

        mote_rect = pygame.Rect(1010, 650, 262, 58)
        draw_panel(
            canvas,
            mote_rect,
            fill=_PANEL,
            outline=_GOLD,
            pattern_token="dots",
            icon=self._icon("mote", 30),
            label=hud.motes_label,
            font=self.assets.font(17, 700),
            foreground=_INK_LIGHT,
            font_size_px=17,
        )
        for index, collected in enumerate(hud.mote_icons):
            center = (mote_rect.right - 74 + index * 20, mote_rect.centery)
            pygame.draw.circle(canvas, _GOLD if collected else _INK_LIGHT, center, 6, 0 if collected else 2)
            if not collected:
                pygame.draw.line(canvas, _INK_LIGHT, (center[0] - 4, center[1]), (center[0] + 4, center[1]), 1)

        save_rect = pygame.Rect(8, 662, 210, 46)
        draw_panel(
            canvas,
            save_rect,
            fill=_PANEL,
            outline=_MINT if hud.save_status_key == "save.saved" else _GOLD,
            pattern_token="stripes",
            icon=self._icon("cleared" if hud.save_status_key == "save.saved" else "available", 26),
            label=hud.save_status_label,
            font=self.assets.font(15, 700),
            foreground=_INK_LIGHT,
            font_size_px=15,
        )
        if hud.muted_indicator:
            muted_rect = pygame.Rect(226, 662, 330, 46)
            draw_panel(
                canvas,
                muted_rect,
                fill=_PANEL,
                outline=_GOLD,
                pattern_token="hatch",
                icon=self._icon("audio_muted", 26),
                label=hud.muted_label,
                font=self.assets.font(15, 700),
                foreground=_INK_LIGHT,
                font_size_px=15,
            )
        player_by_slot = {player.slot: player for player in hud.players}
        for cue in hud.catch_up_cues:
            player = player_by_slot[cue.slot]
            badge_x = 8 if cue.edge == "left" else LOGICAL_SIZE[0] - 120
            badge = pygame.Rect(badge_x, cue.edge_y, 112, 50)
            draw_panel(
                canvas,
                badge,
                fill=_PANEL,
                outline=_SLOT_COLORS[player.color_token],
                pattern_token=_pattern_for(player.pattern_token),
                icon=self._icon(_PLAYER_ICON_BY_TOKEN[player.icon_token], 26),
                label=f"{player.label} {cue.arrow}",
                font=self.assets.font(17, 700),
                foreground=_INK_LIGHT,
                font_size_px=17,
            )


__all__ = ["LOGICAL_SIZE", "RENDER_LAYER_ORDER", "StageRenderer"]
