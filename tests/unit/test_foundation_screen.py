from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pygame

from windsprig.config import GameConfig
from windsprig.content import load_campaign_catalog
from windsprig.feasibility import FoundationProbe
from windsprig.gameplay.abilities import create_default_registry
from windsprig.gameplay.components import Transform
from windsprig.gameplay.snapshot import StageOutcome, StageResult
from windsprig.input.commands import (
    AbilityUseCommand,
    CancelCommand,
    ConfirmCommand,
    InputFrame,
    ProbeCompleteCommand,
)
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


class ProbeStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read_text(self, key: str) -> str | None:
        return self.values.get(key)

    def write_text(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def keys(self, prefix: str) -> tuple[str, ...]:
        return tuple(key for key in sorted(self.values) if key.startswith(prefix))


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


class RecordingFont:
    """Record rendered copy while returning surfaces accepted by pygame blits."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def render(
        self,
        text: str,
        antialias: bool,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        _ = antialias, color
        self.texts.append(text)
        return pygame.Surface((1, 1), pygame.SRCALPHA)


def stage_view(outcome: StageOutcome) -> SimpleNamespace:
    """Return the narrow typed outcome view consumed by FoundationScreen."""
    return SimpleNamespace(outcome=outcome)


def completed_runtime(stage: object, *, frame_index: int = 10) -> SimpleNamespace:
    """Return one gameplay-owned immutable result at a completed outcome."""

    result = StageResult(
        stage_id=stage.stage_id,
        world_id=stage.world_id,
        node_id=stage.node_id,
        clear_time_ms=frame_index * 16,
        collected_mote_ids=(),
        discovered_ability_ids=(),
        active_slots=(1,),
        deaths_by_slot=((1, 0),),
    )

    return SimpleNamespace(
        stage=stage,
        result=result,
        player_entities={1: 1001},
        world=SimpleNamespace(
            resources={
                "run_energy_spheres": 1,
                "collected_mote_ids": set(),
                "discovered_ability_ids": set(),
                "deaths_by_slot": {1: 0},
            },
            frame_index=frame_index,
        ),
        snapshot=lambda: stage_view(StageOutcome.COMPLETED),
    )


def make_foundation_screen(
    save_service: RecordingSaveService,
    probe: FoundationProbe | None = None,
) -> FoundationScreen:
    config = GameConfig()
    catalog = load_campaign_catalog(config.content_dir)
    active_probe = probe or FoundationProbe(ProbeStorage(), enabled=False)
    kwargs = {
        "config": config,
        "roster": ActiveRoster(config.max_local_players),
        "save_service": save_service,
        "catalog": catalog,
        "ability_registry": create_default_registry(config.content_dir),
        "migration_catalog": migration_catalog(catalog),
        "probe": active_probe,
    }
    return FoundationScreen(
        **kwargs,
    )


def test_foundation_fonts_never_consult_browser_host_fonts(monkeypatch) -> None:
    """Keep the first rendered frame independent of WebAssembly font discovery."""

    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))

    def reject_system_font(*_args: object, **_kwargs: object) -> pygame.font.Font:
        raise AssertionError("foundation rendering must use the bundled release font")

    monkeypatch.setattr(pygame.font, "SysFont", reject_system_font)

    title_font, small_font = screen._fonts()

    assert title_font.get_height() > small_font.get_height() > 0


def test_visible_nodes_preserves_the_map_service_authored_world_order() -> None:
    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))
    world_2_node = screen.catalog.worlds["world_2"][0]
    world_1_node = screen.catalog.worlds["world_1"][0]
    screen.world_map_service = SimpleNamespace(
        unlocked_nodes=lambda _tracker, _worlds: {
            "world_2": [world_2_node],
            "world_1": [world_1_node],
        }
    )

    assert tuple(node.world_id for node in screen._visible_nodes()) == (
        "world_2",
        "world_1",
    )


def test_disabled_probe_completion_cannot_position_the_real_player_at_the_goal() -> None:
    storage = ProbeStorage()
    probe = FoundationProbe(storage, enabled=False)
    screen = make_foundation_screen(
        RecordingSaveService([SaveLoadResult(SaveData())]),
        probe,
    )
    screen.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    assert screen._start_selected_stage() is True
    assert screen.runtime is not None
    player_id = screen.runtime.player_entities[1]
    transform = screen.runtime.world.get_component(player_id, Transform)
    original_position = (transform.x, transform.y)

    screen.complete_probe_stage()

    assert (transform.x, transform.y) == original_position
    assert storage.values == {}


def test_stage_hud_and_camera_ignore_contradictory_legacy_resources() -> None:
    screen = make_foundation_screen(RecordingSaveService([SaveLoadResult(SaveData())]))
    screen.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    assert screen._start_selected_stage() is True
    assert screen.runtime is not None
    runtime = screen.runtime
    player_transform = runtime.world.get_component(runtime.player_entities[1], Transform)
    player_transform.x = 1700.0
    runtime.world.resources["camera_target"] = (0.0, 0.0)
    runtime.world.resources["hud"] = {
        "players": [{"slot": 9, "hp": 1, "max_hp": 99, "lives": 0, "ability": "legacy"}],
        "energy_spheres": 99,
    }
    snapshot_target = runtime.snapshot().camera_targets[0]
    expected_x = int(
        max(
            0,
            min(
                snapshot_target.x - screen.config.resolution[0] / 2,
                runtime.stage.pixel_width - screen.config.resolution[0],
            ),
        )
    )
    expected_y = int(
        max(
            0,
            min(
                snapshot_target.y - screen.config.resolution[1] / 2,
                runtime.stage.pixel_height - screen.config.resolution[1],
            ),
        )
    )

    assert screen._camera_offset(runtime) == (expected_x, expected_y)
    assert expected_x > 0

    # The primitive fallback view stays snapshot-authoritative and never surfaces
    # the contradictory legacy HUD resources.
    title_font = RecordingFont()
    small_font = RecordingFont()
    screen._render_stage_primitive(
        pygame.Surface(screen.config.resolution),
        title_font,  # type: ignore[arg-type]
        small_font,  # type: ignore[arg-type]
    )

    assert "P1 HP 10/10 LIFE 3 ABIL none" in small_font.texts
    assert "Wind Motes (Run): 0" in small_font.texts
    assert all("P9" not in text and "99" not in text for text in small_font.texts)

    # The manifest-backed art renderer consumes the same deterministic snapshot
    # and draws a full frame without raising.
    art_canvas = pygame.Surface(screen.config.resolution)
    screen._render_stage(art_canvas, title_font, small_font)  # type: ignore[arg-type]
    assert screen._stage_presentation() is not None


def test_enabled_f9_uses_real_goal_system_then_marks_only_a_successful_save() -> None:
    storage = ProbeStorage()
    probe = FoundationProbe(storage, enabled=True)
    probe.start_session()
    save_service = RecordingSaveService([SaveLoadResult(SaveData())])
    screen = make_foundation_screen(save_service, probe)
    screen.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    assert screen._start_selected_stage() is True
    screen.screen_id = "playing"

    transition = screen.fixed_update(
        screen.config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [ProbeCompleteCommand(player_slot=1)]}),
    )

    assert transition == ScreenTransition("world_map")
    assert storage.values["probe/stage"] == "completed"
    assert storage.values["probe/stage_id"] == "world_1_stage_1"
    assert storage.values["probe/save"] == "written"
    assert save_service.saved == [screen.save_data]


def test_failed_stage_completion_save_never_publishes_written_evidence() -> None:
    storage = ProbeStorage()
    probe = FoundationProbe(storage, enabled=True)
    probe.start_session()
    save_service = RecordingSaveService(
        [SaveLoadResult(SaveData())],
        save_results=[SaveWriteResult(ok=False, error_code="storage_write_failed")],
    )
    screen = make_foundation_screen(save_service, probe)
    screen.roster.join(DeviceRef("keyboard", "keyboard-wasd", "Keyboard WASD"))
    assert screen._start_selected_stage() is True
    screen.screen_id = "playing"

    screen.fixed_update(
        screen.config.fixed_dt_ms,
        InputFrame(commands_by_slot={1: [ProbeCompleteCommand(player_slot=1)]}),
    )

    assert storage.values["probe/stage"] == "completed"
    assert "probe/save" not in storage.values


def test_initial_load_marks_restored_only_for_the_retained_completed_probe_stage() -> None:
    storage = ProbeStorage()
    storage.values["probe/stage_id"] = "world_1_stage_1"
    probe = FoundationProbe(storage, enabled=True)
    probe.start_session()
    baseline = SaveData()
    restored_profile = replace(
        baseline.profiles[0],
        clear_counts={"world_1_stage_1": 1},
    )
    restored = replace(
        baseline,
        profiles=(restored_profile, baseline.profiles[1], baseline.profiles[2]),
    )

    make_foundation_screen(RecordingSaveService([SaveLoadResult(restored)]), probe)

    assert storage.values["probe/save"] == "restored"


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
    screen.runtime = completed_runtime(stage)

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
        world=SimpleNamespace(resources={}),
        step=stepped_frames.append,
        snapshot=lambda: stage_view(StageOutcome.RUNNING),
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
        world=SimpleNamespace(resources={}),
        step=stepped_frames.append,
        snapshot=lambda: stage_view(StageOutcome.RUNNING),
    )
    screen.runtime = runtime
    screen.screen_id = "playing"
    queue = InputQueue()
    queue.push(InputFrame(commands_by_slot={1: [AbilityUseCommand(player_slot=1, pressed=True)]}))
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
        world=SimpleNamespace(resources={}),
        step=lambda _frame: None,
        snapshot=lambda: stage_view(StageOutcome.RUNNING),
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
    screen.runtime = completed_runtime(stage)
    screen.runtime.step = lambda _frame: None
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
