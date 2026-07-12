"""Foundation map, stage, and recovery screen backed by shared session state."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from datetime import datetime
from types import MappingProxyType
from typing import Literal

import pygame

from windsprig._build_flags import FOUNDATION_PROBE_AVAILABLE
from windsprig.config import GameConfig
from windsprig.content import CampaignCatalog, CatalogBundle, load_catalog_bundle
from windsprig.content.loader import WorldNode
from windsprig.core.rng import derive_stage_seed
from windsprig.feasibility import FoundationProbe
from windsprig.gameplay.abilities import AbilityRegistry, create_default_registry
from windsprig.gameplay.components import Collectible, Collider, EnemyAI, Health, StageGoal, Team, Transform
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.snapshot import StageOutcome
from windsprig.input.commands import (
    CancelCommand,
    ConfirmCommand,
    InputCommand,
    InputFrame,
    NavigateCommand,
    PauseCommand,
    ProbeCompleteCommand,
)
from windsprig.input.roster import ActiveRoster
from windsprig.meta import (
    CompletionTracker,
    SaveLoadResult,
    SaveManager,
    SaveMigrationCatalog,
    SaveNotice,
    SaveService,
    SaveWriteResult,
    UnlockRules,
    WorldMapService,
    apply_stage_result,
    migration_catalog,
)
from windsprig.meta.save_models import SaveData
from windsprig.platform.services import PlatformServices, WebTestStatus
from windsprig.screens.base import Screen, ScreenFactory, ScreenId, ScreenTransition

_RELOAD_NOTICE_CODES = {
    "backup_restore_failed",
    "quarantine_failed",
    "read_failed",
    "unsupported_version",
}
_SaveResolutionAction = Literal["reset", "reload", "retry"]


class FoundationScreen(Screen):
    """Own the foundation session's campaign, runtime, and save-recovery state."""

    def __init__(
        self,
        *,
        config: GameConfig,
        roster: ActiveRoster,
        save_service: SaveService,
        catalog: CampaignCatalog,
        ability_registry: AbilityRegistry,
        migration_catalog: SaveMigrationCatalog,
        probe: FoundationProbe,
        progression_catalog: CatalogBundle | None = None,
    ) -> None:
        self.config = config
        self.roster = roster
        self.save_service = save_service
        self.catalog = catalog
        self.ability_registry = ability_registry
        self.migration_catalog = migration_catalog
        self.probe = probe
        self.progression_catalog = progression_catalog or load_catalog_bundle(config.content_dir)
        if self.progression_catalog.campaign != catalog:
            raise ValueError("progression catalog campaign must match screen catalog")
        self.unlock_rules = UnlockRules(catalog)
        self.world_map_service = WorldMapService(catalog, self.unlock_rules)
        self.screen_id: ScreenId = "world_map"
        self.enter_payload: Mapping[str, object] = MappingProxyType({})
        self.runtime: StageRuntime | None = None
        self.selected_node_index = 0
        self.save_data = SaveData()
        self.save_notice: SaveNotice | None = None
        self.save_write_result: SaveWriteResult | None = None
        self.save_status = "ready"
        self._save_resolution_action: _SaveResolutionAction | None = None
        self.tracker = CompletionTracker()
        self.unlocked_nodes: set[str] = set()
        self.unlocked_worlds: set[str] = set()
        self._font: pygame.font.Font | None = None
        self._small_font: pygame.font.Font | None = None
        self._adopt_load_result(self.save_service.load())

    def on_enter(self, payload: Mapping[str, object]) -> None:
        """Activate the selected screen with an immutable payload snapshot."""
        self.enter_payload = MappingProxyType(dict(payload))

    def on_exit(self) -> None:
        """End one activation without discarding shared campaign state."""

    def fixed_update(self, dt_ms: int, input_frame: InputFrame) -> ScreenTransition | None:
        """Advance map, pause, recovery, or gameplay state by one deterministic step."""
        if dt_ms != self.config.fixed_dt_ms:
            raise ValueError("foundation screen requires the configured fixed step")
        commands = tuple(self._commands(input_frame))
        if self.screen_id != "recovery" and self.requires_save_resolution:
            return ScreenTransition("recovery")
        if self.screen_id == "world_map":
            return self._update_world_map(commands)
        if self.screen_id == "playing":
            return self._update_playing(input_frame, commands)
        if self.screen_id == "paused":
            return self._update_paused(commands)
        if self.screen_id == "recovery":
            return self._update_recovery(commands)
        if any(isinstance(command, ConfirmCommand) for command in commands):
            return ScreenTransition("world_map")
        return None

    def render(self, canvas: pygame.Surface, alpha: float) -> None:
        """Render current foundation state on the shared 1280x720 canvas."""
        _ = alpha
        font, small_font = self._fonts()
        if self.screen_id in {"playing", "paused"} and self.runtime is not None:
            self._render_stage(canvas, font, small_font)
            if self.screen_id == "paused":
                overlay = font.render(
                    "Paused - Pause: resume / Confirm: restart / Cancel: world map",
                    True,
                    (255, 255, 255),
                )
                canvas.blit(overlay, (20, 94))
        else:
            self._render_world_map(canvas, font, small_font)
        self._render_save_state(canvas, small_font)

    def confirm_save_reset(self) -> SaveWriteResult:
        """Run the save service's explicit, fingerprint-verified reset action."""
        result = self.save_service.confirm_reset(self.save_data)
        self.save_write_result = result
        if result.ok:
            self.save_status = "saved"
            self._save_resolution_action = None
            self.save_notice = None
        elif result.error_code == "recovery_required":
            self.save_status = "retry_required"
            self._save_resolution_action = "reload"
        else:
            self.save_status = "reset_required"
            self._save_resolution_action = "reset"
        return result

    def reload_save(self) -> SaveLoadResult:
        """Reload authoritative storage before retrying a recovery-blocked write."""
        result = self.save_service.load()
        self._adopt_load_result(result)
        return result

    @property
    def requires_save_resolution(self) -> bool:
        """Return whether an explicit retry, reload, or reset action is pending."""
        return self._save_resolution_action is not None

    def _select_screen(self, screen_id: ScreenId) -> None:
        self.screen_id = screen_id

    @staticmethod
    def _commands(input_frame: InputFrame) -> Iterator[InputCommand]:
        for slot in sorted(input_frame.commands_by_slot):
            yield from input_frame.commands_for(slot)

    def _update_world_map(self, commands: tuple[InputCommand, ...]) -> ScreenTransition | None:
        nodes = self._visible_nodes()
        for command in commands:
            if isinstance(command, NavigateCommand) and nodes:
                direction = command.x if command.x else command.y
                if direction:
                    self.selected_node_index = (self.selected_node_index + direction) % len(nodes)
            elif isinstance(command, ConfirmCommand) and self._start_selected_stage():
                return ScreenTransition("playing")
            elif isinstance(command, CancelCommand):
                return ScreenTransition("title")
        return None

    def _update_playing(
        self,
        input_frame: InputFrame,
        commands: tuple[InputCommand, ...],
    ) -> ScreenTransition | None:
        if any(isinstance(command, CancelCommand) and command.origin == "cancel" for command in commands):
            return ScreenTransition("paused")
        if any(isinstance(command, PauseCommand) for command in commands):
            return ScreenTransition("paused")
        runtime = self.runtime
        if runtime is None:
            return ScreenTransition("world_map")
        if any(isinstance(command, ProbeCompleteCommand) for command in commands):
            self.complete_probe_stage()
        runtime.step(input_frame)
        if self._on_stage_progress():
            target: ScreenId = "recovery" if self.requires_save_resolution else "world_map"
            return ScreenTransition(target)
        return None

    def complete_probe_stage(self) -> None:
        """Position the active real player at the real goal only for the opt-in probe."""
        if not self.probe.enabled or self.runtime is None or not self.runtime.player_entities:
            return
        player_id = self.runtime.player_entities[min(self.runtime.player_entities)]
        player_transform = self.runtime.world.get_component(player_id, Transform)
        goals = self.runtime.world.query(StageGoal, Transform, Collider)
        if not goals:
            return
        _, _, goal_transform, _ = goals[0]
        player_transform.x = goal_transform.x
        player_transform.y = goal_transform.y

    def _update_paused(self, commands: tuple[InputCommand, ...]) -> ScreenTransition | None:
        if any(isinstance(command, CancelCommand) for command in commands):
            self.runtime = None
            return ScreenTransition("world_map")
        if any(isinstance(command, ConfirmCommand) for command in commands) and self._restart_stage():
            return ScreenTransition("playing")
        if any(isinstance(command, PauseCommand) for command in commands):
            return ScreenTransition("playing")
        return None

    def _update_recovery(self, commands: tuple[InputCommand, ...]) -> ScreenTransition | None:
        if any(isinstance(command, ConfirmCommand) for command in commands):
            return self._resolve_save()
        if any(isinstance(command, CancelCommand) for command in commands):
            if self._save_resolution_action == "reload":
                self.reload_save()
            if not self.requires_save_resolution:
                return ScreenTransition("world_map")
        return None

    def _resolve_save(self) -> ScreenTransition | None:
        action = self._save_resolution_action
        if action == "reset":
            self.confirm_save_reset()
        elif action == "reload":
            self.reload_save()
        elif action == "retry":
            self._flush_save()
        if self.requires_save_resolution:
            return None
        if action in {"reset", "retry"}:
            self.save_notice = None
        return ScreenTransition("world_map")

    def _adopt_load_result(self, result: SaveLoadResult) -> None:
        self.save_data = result.data
        self.save_notice = result.notice
        self.save_write_result = None
        notice_code = result.notice.code if result.notice is not None else None
        if notice_code == "reset_required":
            self.save_status = "reset_required"
            self._save_resolution_action = "reset"
        elif notice_code in _RELOAD_NOTICE_CODES:
            self.save_status = "retry_required"
            self._save_resolution_action = "reload"
        else:
            self.save_status = "ready"
            self._save_resolution_action = None
        self._rebuild_progress()
        probe_stage_id = self.probe.read("stage_id")
        if probe_stage_id is not None and result.data.profiles[0].clear_counts.get(probe_stage_id, 0) > 0:
            self.probe.mark("save", "restored")
        if notice_code == "migrated_v1":
            self._apply_save_result(self.save_service.save(self.save_data))

    def _rebuild_progress(self) -> None:
        profile = self.save_data.profiles[0]
        cleared_nodes = {
            node_id
            for node_id, stage_id in self.migration_catalog.stage_id_by_node.items()
            if profile.clear_counts.get(stage_id, 0) > 0
        }
        self.tracker = CompletionTracker(
            cleared_nodes=cleared_nodes,
            collected_mote_ids=set(profile.collected_mote_ids),
            discovered_abilities=set(profile.discovered_abilities),
            challenge_rewards=set(profile.challenge_rewards),
            best_times_ms=dict(profile.best_times_ms),
            clear_counts=dict(profile.clear_counts),
        )
        self.unlocked_nodes = set(profile.unlocked_nodes)
        self.unlocked_worlds = set(profile.unlocked_worlds)

    def _apply_save_result(self, result: SaveWriteResult) -> None:
        self.save_write_result = result
        if result.ok:
            self.save_status = "saved"
            self._save_resolution_action = None
        elif result.error_code == "reset_confirmation_required":
            self.save_status = "reset_required"
            self._save_resolution_action = "reset"
        else:
            self.save_status = "retry_required"
            if result.error_code in {"recovery_required", "unsupported_version"}:
                self._save_resolution_action = "reload"
            else:
                self._save_resolution_action = "retry"

    def _visible_nodes(self) -> list[WorldNode]:
        visible = self.world_map_service.unlocked_nodes(self.tracker, self.unlocked_worlds)
        # WorldMapService already emits authored order; sorting IDs would redefine progression.
        return [node for world_nodes in visible.values() for node in world_nodes]

    def _start_selected_stage(self) -> bool:
        nodes = self._visible_nodes()
        if not nodes or not self.roster.players:
            return False
        node = nodes[self.selected_node_index % len(nodes)]
        self.runtime = StageRuntime(
            config=self.config,
            stage=self.catalog.stages[node.stage_id],
            ability_registry=self.ability_registry,
            active_players=self.roster.players,
            seed=derive_stage_seed(self.config.replay_seed, node.stage_id),
        )
        return True

    def _restart_stage(self) -> bool:
        runtime = self.runtime
        if runtime is None or not self.roster.players:
            return False
        stage = runtime.stage
        self.runtime = StageRuntime(
            config=self.config,
            stage=stage,
            ability_registry=self.ability_registry,
            active_players=self.roster.players,
            seed=derive_stage_seed(self.config.replay_seed, stage.stage_id),
        )
        return True

    def _on_stage_progress(self) -> bool:
        runtime = self.runtime
        if runtime is None or runtime.snapshot().outcome is not StageOutcome.COMPLETED:
            return False
        stage = runtime.stage
        self.probe.mark("stage_id", stage.stage_id)
        self.probe.mark("stage", "completed")
        result = runtime.result
        if result is None:
            raise RuntimeError("completed gameplay must provide its frozen StageResult")
        if result.stage_id != stage.stage_id:
            raise ValueError("runtime result stage must match the active stage")
        profile, _ = apply_stage_result(
            self.save_data.profiles[0],
            result,
            self.progression_catalog,
        )
        self.save_data = replace(
            self.save_data,
            profiles=(profile, self.save_data.profiles[1], self.save_data.profiles[2]),
        )
        self._rebuild_progress()
        self.runtime = None
        save_result = self._flush_save(automatic=True)
        if save_result is not None and save_result.ok:
            self.probe.mark("save", "written")
        return True

    def _flush_save(self, *, automatic: bool = False) -> SaveWriteResult | None:
        profile = replace(
            self.save_data.profiles[0],
            unlocked_nodes=frozenset(self.unlocked_nodes),
            unlocked_worlds=frozenset(self.unlocked_worlds),
            collected_mote_ids=frozenset(self.tracker.collected_mote_ids),
            discovered_abilities=frozenset(self.tracker.discovered_abilities),
            best_times_ms=dict(self.tracker.best_times_ms),
            clear_counts=dict(self.tracker.clear_counts),
            challenge_rewards=frozenset(self.tracker.challenge_rewards),
        )
        updated = replace(
            self.save_data,
            profiles=(profile, self.save_data.profiles[1], self.save_data.profiles[2]),
        )
        self.save_data = updated
        # Automatic progression writes must not probe or replace unresolved recovery sources.
        if automatic and self.requires_save_resolution:
            return None
        result = self.save_service.save(updated)
        self._apply_save_result(result)
        return result

    def _fonts(self) -> tuple[pygame.font.Font, pygame.font.Font]:
        if self._font is None or self._small_font is None:
            if not pygame.font.get_init():
                pygame.font.init()
            # WHY: SysFont performs host discovery and can block indefinitely in
            # WebAssembly. The release font is deterministic, bilingual, and is
            # verified by the asset manifest before publication.
            font_path = self.config.asset_dir / "fonts" / "WindsprigSansKR.ttf"
            self._font = pygame.font.Font(str(font_path), 20)
            self._small_font = pygame.font.Font(str(font_path), 16)
        return self._font, self._small_font

    def _render_world_map(
        self,
        canvas: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
    ) -> None:
        canvas.fill((25, 33, 64))
        heading = "World Map - Confirm: start / Cancel: title"
        if self.screen_id != "world_map":
            heading = f"Windsprig - {self.screen_id}"
        canvas.blit(font.render(heading, True, (240, 242, 255)), (20, 18))
        nodes = self._visible_nodes()
        if not nodes:
            canvas.blit(font.render("No unlocked nodes.", True, (255, 220, 220)), (20, 70))
            return
        for index, node in enumerate(nodes):
            selected = index == self.selected_node_index % len(nodes)
            cleared = node.node_id in self.tracker.cleared_nodes
            color = (95, 225, 150) if cleared else (255, 210, 94)
            if selected:
                color = (255, 255, 255)
            x, y = node.position
            pygame.draw.circle(canvas, color, (x, y), 18 if selected else 14)
            label = small_font.render(node.stage_id, True, (10, 10, 10))
            canvas.blit(label, (x - label.get_width() // 2, y - 34))
        info = small_font.render(
            f"Worlds: {', '.join(sorted(self.unlocked_worlds))} | Cleared: {len(self.tracker.cleared_nodes)}",
            True,
            (230, 230, 245),
        )
        canvas.blit(info, (20, canvas.get_height() - 30))

    def _render_stage(
        self,
        canvas: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
    ) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        stage = runtime.stage
        world = runtime.world
        snapshot = runtime.snapshot()
        canvas.fill((92, 160, 244))
        camera_x, camera_y = self._camera_offset(runtime)
        for tile_x, tile_y in stage.solids:
            pygame.draw.rect(
                canvas,
                (76, 98, 128),
                pygame.Rect(
                    tile_x * stage.tile_size - camera_x,
                    tile_y * stage.tile_size - camera_y,
                    stage.tile_size,
                    stage.tile_size,
                ),
            )
        for tile_x, tile_y in stage.one_way_tiles:
            pygame.draw.rect(
                canvas,
                (116, 140, 171),
                pygame.Rect(
                    tile_x * stage.tile_size - camera_x,
                    tile_y * stage.tile_size - camera_y,
                    stage.tile_size,
                    8,
                ),
            )
        for tile_x, tile_y in stage.hazards:
            pygame.draw.rect(
                canvas,
                (230, 85, 85),
                pygame.Rect(
                    tile_x * stage.tile_size - camera_x,
                    tile_y * stage.tile_size - camera_y,
                    stage.tile_size,
                    stage.tile_size,
                ),
            )
        for _, collectible, transform, collider in world.query(Collectible, Transform, Collider):
            if not collectible.collected:
                pygame.draw.ellipse(
                    canvas,
                    (255, 239, 120),
                    pygame.Rect(
                        transform.x - camera_x,
                        transform.y - camera_y,
                        collider.width,
                        collider.height,
                    ),
                )
        for _, _, transform, collider in world.query(StageGoal, Transform, Collider):
            pygame.draw.rect(
                canvas,
                (116, 230, 162),
                pygame.Rect(
                    transform.x - camera_x,
                    transform.y - camera_y,
                    collider.width,
                    collider.height,
                ),
            )
        for entity_id, team, transform, collider, health in world.query(
            Team,
            Transform,
            Collider,
            Health,
        ):
            color = (255, 167, 191) if team.name == "player" else (118, 192, 255)
            if health.dead:
                color = (100, 100, 100)
            pygame.draw.rect(
                canvas,
                color,
                pygame.Rect(
                    transform.x - camera_x,
                    transform.y - camera_y,
                    collider.width,
                    collider.height,
                ),
            )
            if world.has_component(entity_id, EnemyAI):
                pygame.draw.rect(
                    canvas,
                    (20, 20, 40),
                    pygame.Rect(
                        transform.x - camera_x,
                        transform.y - 8 - camera_y,
                        collider.width,
                        5,
                    ),
                )
                hp_ratio = health.current / max(1, health.maximum)
                pygame.draw.rect(
                    canvas,
                    (220, 84, 84),
                    pygame.Rect(
                        transform.x - camera_x,
                        transform.y - 8 - camera_y,
                        int(collider.width * hp_ratio),
                        5,
                    ),
                )
        canvas.blit(font.render(f"{stage.stage_id} | Cancel: map / Pause: pause", True, (250, 250, 255)), (16, 12))
        for index, player in enumerate(snapshot.players):
            label = small_font.render(
                f"P{player.slot} HP {player.hp}/{player.maximum_hp} "
                f"LIFE {player.lives_remaining} ABIL {player.ability_id}",
                True,
                (245, 245, 255),
            )
            canvas.blit(label, (16, 44 + index * 22))
        canvas.blit(
            small_font.render(
                f"Wind Motes (Run): {len(snapshot.collected_mote_ids)}",
                True,
                (255, 245, 170),
            ),
            (16, 50 + len(snapshot.players) * 22),
        )

    def _render_save_state(self, canvas: pygame.Surface, small_font: pygame.font.Font) -> None:
        if self.save_notice is None and self.save_status in {"ready", "saved"}:
            return
        notice_code = self.save_notice.code if self.save_notice is not None else "none"
        action = "Confirm to resolve" if self.requires_save_resolution else "Save ready"
        message = small_font.render(
            f"Save: {self.save_status} ({notice_code}) - {action}",
            True,
            (255, 230, 155),
        )
        canvas.blit(message, (20, canvas.get_height() - 56))

    def _camera_offset(self, runtime: StageRuntime) -> tuple[int, int]:
        targets = runtime.snapshot().camera_targets
        total_weight = sum(target.weight for target in targets)
        if total_weight > 0:
            target_x = sum(target.x * target.weight for target in targets) / total_weight
            target_y = sum(target.y * target.weight for target in targets) / total_weight
        else:
            target_x = target_y = 0.0
        view_width, view_height = self.config.resolution
        camera_x = int(max(0, min(target_x - view_width / 2, runtime.stage.pixel_width - view_width)))
        camera_y = int(max(0, min(target_y - view_height / 2, runtime.stage.pixel_height - view_height)))
        return camera_x, camera_y


class FoundationScreenFactory(ScreenFactory):
    """Return one shared foundation screen so campaign and recovery state cannot fork."""

    def __init__(
        self,
        config: GameConfig,
        services: PlatformServices,
        now_utc: Callable[[], datetime],
        *,
        roster: ActiveRoster | None = None,
        save_service: SaveService | None = None,
        probe: FoundationProbe | None = None,
    ) -> None:
        self.roster = roster or ActiveRoster(config.max_local_players)
        if probe is None:
            enabled = (
                FOUNDATION_PROBE_AVAILABLE
                and services.browser is not None
                and services.browser.query_param("foundation_probe") == "1"
            )
            probe = FoundationProbe(services.storage, enabled=enabled)
        probe.start_session()
        self.probe = probe
        progression_catalog = load_catalog_bundle(config.content_dir)
        catalog = progression_catalog.campaign
        migrations = migration_catalog(catalog)
        service = save_service or SaveManager(services.storage, migrations, now_utc)
        self.foundation_screen = FoundationScreen(
            config=config,
            roster=self.roster,
            save_service=service,
            catalog=catalog,
            ability_registry=create_default_registry(config.content_dir),
            migration_catalog=migrations,
            probe=self.probe,
            progression_catalog=progression_catalog,
        )

    def create(self, screen_id: ScreenId) -> FoundationScreen:
        """Select ``screen_id`` after the coordinator exits the prior activation."""
        self.foundation_screen._select_screen(screen_id)
        return self.foundation_screen

    def web_test_status(self, screen_id: ScreenId, active_players: int) -> WebTestStatus:
        """Project shared foundation state through the factory composition boundary."""
        profile = self.foundation_screen.save_data.profiles[0]
        return WebTestStatus(
            state=screen_id,
            save_version=self.foundation_screen.save_data.save_version,
            save_status=self.foundation_screen.save_status,
            cleared_stages=len(profile.clear_counts),
            active_players=active_players,
        )

    @property
    def initial_screen_id(self) -> ScreenId:
        """Start in recovery when persistence requires an explicit user action."""
        return "recovery" if self.foundation_screen.requires_save_resolution else "world_map"


def create_foundation_screen_factory(
    config: GameConfig,
    services: PlatformServices,
    now_utc: Callable[[], datetime],
    *,
    roster: ActiveRoster | None = None,
    save_service: SaveService | None = None,
    probe: FoundationProbe | None = None,
) -> FoundationScreenFactory:
    """Build the shared foundation screen and its platform-backed save service."""
    return FoundationScreenFactory(
        config,
        services,
        now_utc,
        roster=roster,
        save_service=save_service,
        probe=probe,
    )
