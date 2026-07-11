from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pygame

from windsprig.config import GameConfig
from windsprig.content import load_campaign_catalog
from windsprig.gameplay.abilities import create_default_registry
from windsprig.input.commands import AbilityUseCommand, CancelCommand, ConfirmCommand, InputFrame
from windsprig.input.queue import InputQueue
from windsprig.input.roster import ActiveRoster, DeviceRef
from windsprig.input.router import InputRouter
from windsprig.meta import (
    SaveData,
    SaveLoadResult,
    SaveNotice,
    SaveWriteResult,
    migration_catalog,
)
from windsprig.screens.base import ScreenTransition
from windsprig.screens.foundation import FoundationScreen


class RecordingSaveService:
    def __init__(
        self,
        load_results: list[SaveLoadResult],
        save_results: list[SaveWriteResult] | None = None,
        confirm_results: list[SaveWriteResult] | None = None,
    ) -> None:
        self.load_results = load_results
        self.save_results = save_results or []
        self.confirm_results = confirm_results or []
        self.saved: list[SaveData] = []
        self.confirmed: list[SaveData] = []
        self.load_count = 0

    def load(self) -> SaveLoadResult:
        self.load_count += 1
        return self.load_results.pop(0)

    def save(self, data: SaveData) -> SaveWriteResult:
        self.saved.append(data)
        return self.save_results.pop(0) if self.save_results else SaveWriteResult(ok=True)

    def confirm_reset(self, data: SaveData) -> SaveWriteResult:
        self.confirmed.append(data)
        return self.confirm_results.pop(0) if self.confirm_results else SaveWriteResult(ok=True)


def make_foundation_screen(save_service: RecordingSaveService) -> FoundationScreen:
    config = GameConfig()
    catalog = load_campaign_catalog(config.content_dir)
    return FoundationScreen(
        config=config,
        roster=ActiveRoster(config.max_local_players),
        save_service=save_service,
        catalog=catalog,
        ability_registry=create_default_registry(config.content_dir),
        migration_catalog=migration_catalog(catalog),
    )


def test_stage_completion_never_auto_flushes_while_reset_is_unresolved() -> None:
    save_service = RecordingSaveService(
        [
            SaveLoadResult(
                SaveData(),
                SaveNotice("reset_required", "save.reset_required"),
            )
        ]
    )
    screen = make_foundation_screen(save_service)
    stage = screen.catalog.stages["world_1_stage_1"]
    screen.runtime = SimpleNamespace(
        stage=stage,
        world=SimpleNamespace(
            resources={"stage_cleared": True, "run_energy_spheres": 1},
            frame_index=10,
        ),
    )

    screen._on_stage_progress()

    assert screen.save_status == "reset_required"
    assert screen.tracker.clear_counts == {"world_1_stage_1": 1}
    assert save_service.saved == []


def test_reload_action_adopts_authoritative_data_before_saves_resume() -> None:
    authoritative = SaveData()
    save_service = RecordingSaveService(
        [
            SaveLoadResult(SaveData(), SaveNotice("read_failed", "save.read_failed")),
            SaveLoadResult(authoritative),
        ]
    )
    screen = make_foundation_screen(save_service)

    result = screen.reload_save()

    assert result.data == authoritative
    assert screen.save_data == authoritative
    assert screen.save_notice is None
    assert screen.save_status == "ready"


def test_reset_confirmation_remains_a_narrow_explicit_action() -> None:
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData(), SaveNotice("reset_required", "save.reset_required"))]
    )
    screen = make_foundation_screen(save_service)

    result = screen.confirm_save_reset()

    assert result.ok is True
    assert save_service.confirmed == [screen.save_data]
    assert screen.save_status == "saved"


def test_gamepad_ability_cancel_pair_reaches_playing_runtime_once_without_transition() -> None:
    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))
    screen.roster.join(DeviceRef("gamepad", "gamepad-42", "Controller"))
    routed = InputRouter().collect(
        [pygame.event.Event(pygame.JOYBUTTONDOWN, instance_id=42, joy=0, button=1)],
        (),  # No keyboard player is active, so key state is never sampled.
        screen.roster,
    )
    stepped_frames: list[InputFrame] = []
    runtime = SimpleNamespace(
        world=SimpleNamespace(resources={"stage_cleared": False}),
        step=stepped_frames.append,
    )
    screen.runtime = runtime
    screen.screen_id = "playing"

    transition = screen.fixed_update(screen.config.fixed_dt_ms, routed.frame)

    assert transition is None
    assert stepped_frames == [routed.frame]
    assert screen.runtime is runtime


def test_buffered_keyboard_ability_then_genuine_cancel_still_pauses() -> None:
    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))
    stepped_frames: list[InputFrame] = []
    runtime = SimpleNamespace(
        world=SimpleNamespace(resources={"stage_cleared": False}),
        step=stepped_frames.append,
    )
    screen.runtime = runtime
    screen.screen_id = "playing"
    queue = InputQueue()
    queue.push(
        InputFrame(commands_by_slot={1: [AbilityUseCommand(player_slot=1, pressed=True)]})
    )
    queue.push(InputFrame(commands_by_slot={1: [CancelCommand(player_slot=1)]}))

    transition = screen.fixed_update(screen.config.fixed_dt_ms, queue.consume_step())

    assert transition == ScreenTransition("paused")
    assert stepped_frames == []
    assert screen.runtime is runtime


def test_gamepad_b_remains_a_menu_cancel_on_world_map() -> None:
    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))
    screen.roster.join(DeviceRef("gamepad", "gamepad-42", "Controller"))
    routed = InputRouter().collect(
        [pygame.event.Event(pygame.JOYBUTTONDOWN, instance_id=42, joy=0, button=1)],
        (),
        screen.roster,
    )
    screen.screen_id = "world_map"

    transition = screen.fixed_update(screen.config.fixed_dt_ms, routed.frame)

    assert transition == ScreenTransition("title")


def test_standalone_playing_cancel_pauses_without_discarding_runtime() -> None:
    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))
    runtime = SimpleNamespace(
        world=SimpleNamespace(resources={"stage_cleared": False}),
        step=lambda _frame: None,
    )
    screen.runtime = runtime
    screen.screen_id = "playing"

    transition = screen.fixed_update(
        screen.config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [CancelCommand(player_slot=1)]}),
    )

    assert transition == ScreenTransition("paused")
    assert screen.runtime is runtime


def test_stage_completion_transitions_to_recovery_when_save_requires_reload() -> None:
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData())],
        save_results=[SaveWriteResult(ok=False, error_code="recovery_required")],
    )
    screen = make_foundation_screen(save_service)
    stage = screen.catalog.stages["world_1_stage_1"]
    screen.runtime = SimpleNamespace(
        stage=stage,
        world=SimpleNamespace(
            resources={"stage_cleared": True, "run_energy_spheres": 1},
            frame_index=10,
        ),
        step=lambda _frame: None,
    )
    screen.screen_id = "playing"

    transition = screen.fixed_update(screen.config.fixed_dt_ms, InputFrame.empty())

    assert transition == ScreenTransition("recovery")
    assert screen.save_status == "retry_required"
    assert screen.runtime is None
    assert len(save_service.saved) == 1


def test_recovery_confirm_reloads_and_adopts_authoritative_data_before_returning_safe() -> None:
    baseline = SaveData()
    authoritative_profile = replace(baseline.profiles[0], display_name="Authority")
    authoritative = replace(
        baseline,
        profiles=(authoritative_profile, baseline.profiles[1], baseline.profiles[2]),
    )
    save_service = RecordingSaveService(
        [SaveLoadResult(baseline), SaveLoadResult(authoritative)],
        save_results=[SaveWriteResult(ok=False, error_code="recovery_required")],
    )
    screen = make_foundation_screen(save_service)
    screen._flush_save()
    screen.screen_id = "recovery"

    transition = screen.fixed_update(
        screen.config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [ConfirmCommand(player_slot=1)]}),
    )

    assert transition == ScreenTransition("world_map")
    assert save_service.load_count == 2
    assert screen.save_data == authoritative
    assert screen.save_status == "ready"
    assert save_service.confirmed == []


def test_recovery_confirm_retries_unlocked_write_and_returns_safe_on_success() -> None:
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData())],
        save_results=[
            SaveWriteResult(ok=False, error_code="storage_write_failed"),
            SaveWriteResult(ok=True),
        ],
    )
    screen = make_foundation_screen(save_service)
    screen._flush_save()
    screen.screen_id = "recovery"

    transition = screen.fixed_update(
        screen.config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [ConfirmCommand(player_slot=1)]}),
    )

    assert transition == ScreenTransition("world_map")
    assert len(save_service.saved) == 2
    assert screen.save_status == "saved"


def test_recovery_confirm_explicitly_resets_and_failure_remains_recoverable() -> None:
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData(), SaveNotice("reset_required", "save.reset_required"))],
        confirm_results=[
            SaveWriteResult(ok=False, error_code="storage_write_failed"),
            SaveWriteResult(ok=True),
        ],
    )
    screen = make_foundation_screen(save_service)
    screen.screen_id = "recovery"
    confirm_frame = InputFrame(commands_by_slot={1: [ConfirmCommand(player_slot=1)]})
    assert save_service.confirmed == []

    failed_transition = screen.fixed_update(screen.config.fixed_dt_ms, confirm_frame)

    assert failed_transition is None
    assert screen.save_status == "reset_required"
    assert len(save_service.confirmed) == 1

    successful_transition = screen.fixed_update(screen.config.fixed_dt_ms, confirm_frame)

    assert successful_transition == ScreenTransition("world_map")
    assert screen.save_status == "saved"
    assert len(save_service.confirmed) == 2
    assert screen.save_notice is None


def test_successful_recovery_retry_clears_stale_migration_notice() -> None:
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData(), SaveNotice("migrated_v1", "save.migrated_v1"))],
        save_results=[
            SaveWriteResult(ok=False, error_code="storage_write_failed"),
            SaveWriteResult(ok=True),
        ],
    )
    screen = make_foundation_screen(save_service)
    screen.screen_id = "recovery"

    transition = screen.fixed_update(
        screen.config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [ConfirmCommand(player_slot=1)]}),
    )

    assert transition == ScreenTransition("world_map")
    assert screen.save_status == "saved"
    assert screen.save_notice is None
