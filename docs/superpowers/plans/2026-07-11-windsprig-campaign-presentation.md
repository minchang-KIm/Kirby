# Windsprig Campaign, Progression, and Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the complete six-world campaign and its camera-ready presentation: 30 distinct stages, six unique multi-phase bosses, 90 stable Wind Motes, progression screens, bilingual UI, original generated art/audio, accessible settings, and catalog-wide automated evidence.

**Architecture:** Deterministic authoring scripts expand compact, reviewed recipes into native campaign, boss, locale, art, and audio artifacts; one validator rejects referential, geometry, asset, translation, provenance, and full-catalog defects before runtime. Frozen progression and presentation view models consume the foundation save/services contracts and gameplay `StageSnapshot`/`StageResult` contracts, while rendering, animation, particles, camera, HUD, and audio subscribe to immutable snapshots and semantic events without entering replay hashes.

**Tech Stack:** Python 3.12, pygame-ce 2.5.7, frozen standard-library dataclasses with explicit JSON validation, standard-library WAV/hash tooling, Noto Sans KR under SIL OFL 1.1, pytest 8.x, Hypothesis 6.x, Ruff, mypy, uv.

## Global Constraints

- Public title: `Windsprig: Echoes of the Gale`; active Python package, imports, window title, and executable identity: `windsprig`.
- The public game, package, executable, documentation, screenshots, art, audio, levels, copy, and generated artifacts must contain no Nintendo, Kirby, Return to Dream Land, Nintendo character, logo, visual asset, audio, level, or public-facing identifier.
- v1.0 contains exactly six named worlds, five stages per world, 30 playable stages, six boss stages, six unique multi-phase bosses, and 90 stable collectible Wind Mote IDs.
- Each world has four non-boss stages and one boss stage; each stage has exactly three stable Wind Motes so the catalog total is 90. Boss-stage motes live on the authored pre-arena route and are collectible before the boss gate.
- Stage 1 introduces its world mechanic safely; stages 2–3 combine it with traversal and combat; stage 4 is a mastery gauntlet; stage 5 is the boss. An experienced solo clear target is two-to-six minutes.
- Critical progression never requires a hidden collectible. Optional routes reward motes, time-saving mastery, or ability choice rather than blind leaps.
- Public ability IDs are exactly `bloomblade`, `cinder`, `voltsong`, `galehook`, `stoneheart`, and `tempest`; every family appears in campaign enemy-source content.
- Clearing a stage unlocks the next node; clearing a boss unlocks the next world. Mote thresholds unlock challenge variants, gallery entries, and palette rewards, never mandatory story progress.
- Render to a 1280×720 logical canvas; gameplay requires a viewport of at least 1024×576; target 60 rendered FPS, minimum sustained gameplay floor 30 FPS, and deterministic simulation step 16 ms.
- Camera behavior includes smooth damped tracking, directional look-ahead, stage bounds, a solo safe frame, and co-op catch-up/respawn rules. Reduced motion disables shake and afterimage-heavy effects without hiding state.
- Sprig uses a seed/leaf body, wind-sail scarf, twig limbs, and asymmetrical leaf crest; Sprig must not be a pink sphere or imitate Kirby face, proportions, feet, pose language, or iconography.
- Every world has a distinct palette, parallax background, tile family, props, particles, and transition card. Every standard enemy, elite, boss phase, player slot, ability, collectible, hazard, checkpoint, and goal has a distinct readable silhouette.
- Required player animation states are idle, run, jump, fall, hover, draw, captured, harmonize, attack, guard, dodge, hurt, defeated, and victory.
- English is the source locale and Korean is fully supported. Player text comes from locale data. The bundled Korean-capable font is OFL-licensed and its unmodified license is retained.
- Body and critical HUD text target contrast ratio at least 4.5:1; large decorative text targets at least 3:1. Status never depends on color alone.
- Settings cover master/music/SFX volume, mute, fullscreen/windowed, integer scaling, screen shake, reduced motion, draw hold/toggle, guard hold/toggle, language, control reference, desktop remapping where stable, browser keyboard presets, and gamepad guidance.
- Ship original generated or authored music and SFX. Each world has a loop, each boss has phase-aware variations, title/map/results/credits have dedicated cues, and every core action has a distinct cue.
- Browser audio starts only after user engagement, resumes after tab suspension, and reports a visible muted state on initialization failure without blocking play.
- Mandatory content, sprite, font, or audio absence is a build/CI failure. Runtime diagnostic fallbacks are development-only.
- Presentation-only camera easing, animation cursors, particles, shake, and audio state are excluded from deterministic runtime snapshots and replay hashes.
- Production modules target at least 85% branch coverage overall. Full-catalog, content, localization, accessibility, and visual gates are required even when aggregate coverage passes.
- Browser compressed transfer target remains at most 30 MB; generated audio uses 22,050 Hz mono PCM and generated art uses packed atlases to stay within that budget.
- Native saves remain under `%LOCALAPPDATA%/Windsprig`; browser saves remain local browser storage; no task writes a release save relative to the launch directory.

---

## Exact File Map

```text
windsprig/
  content/
    models.py                       frozen world/stage/boss/asset content DTOs
    loader.py                       strict native JSON loaders and CatalogBundle
    campaign.json                   generated 6-world/30-stage/90-mote catalog
    bosses.json                     generated six bosses with three phases each
    rewards.json                    generated mote thresholds/challenges/gallery/palettes
    strings.en.json                 generated complete English source locale
    strings.ko.json                 generated key-identical Korean locale
    assets.json                     generated mandatory art/audio/font manifest
  gameplay/
    bosses.py                       deterministic boss phase/attack director
    snapshot.py                     adds immutable BossView to gameplay snapshot
    runtime.py                      loads boss definitions and emits boss semantic events
  meta/
    completion.py                   immutable completion calculation and StageResult application
    world_map.py                    locked/available/cleared graph and world-map VM builder
    presentation_models.py          profile/results/settings frozen view models
  localization.py                   strict locale loading, fallback, formatting, font coverage
  render/
    assets.py                       manifest-backed AssetCatalog and mandatory loading failures
    animation.py                    state clips and deterministic presentation animation cursors
    effects.py                      event-to-particle/shake/flash translation
    camera.py                       damped safe-frame camera and logical-canvas letterboxing
    ui.py                           contrast-checked text/panel/icon/pattern primitives
    hud.py                          immutable StageSnapshot-to-HudViewModel adapter
    renderer.py                     world/stage/boss renderer consuming view models only
  audio/
    music.py                        phase-aware MusicDirector over platform AudioService
    cues.py                         semantic-event-to-cue mapping
  screens/
    profile.py                      profile select/create/delete presentation
    world_map.py                    route/node presentation and selection
    results.py                      results/reward presentation and actions
    settings.py                     settings/accessibility/control presentation and persistence
assets/
  fonts/
    NotoSansKR[wght].ttf            pinned Korean-capable variable font
    OFL-NotoSansKR.txt              exact upstream SIL OFL 1.1 text
  generated/
    player/sprig.png                56-frame original player atlas
    enemies/*.png                   18 original four-frame enemy atlases
    bosses/*.png                    six original phase atlases
    worlds/*.png                    six background/tile/prop/transition atlas sets
    ui/icons.png                    action/status/pattern atlas
    ui/favicon.png                  192×192 original icon
    ui/social-card.png              1200×630 original release card
    audio/music/*.wav               28 original loop cues
    audio/sfx/*.wav                 29 original one-shot cues
    art-provenance.json             generated procedure/seed/parameters/hashes
    audio-provenance.json           generated synthesis/composition/hashes
  LICENSES.md                       font plus original art/audio provenance summary
tools/
  generate_campaign.py              deterministic campaign/boss/reward expansion
  generate_locales.py               deterministic English/Korean locale generation
  fetch_font.py                     pinned, hash-verified Noto Sans KR fetch
  generate_art.py                   deterministic vector-style raster atlas generation
  generate_audio.py                 deterministic original PCM composition/synthesis
  validate_content.py               all-schema/all-reference/all-asset validator CLI
  update_visual_baselines.py        explicit visual baseline approval command
tests/
  helpers/catalog.py                minimal valid catalog/boss fixture factories
  unit/content/
    test_models.py
    test_validator.py
    test_bosses.py
    test_localization.py
  unit/meta/
    test_completion.py
    test_world_map_views.py
    test_presentation_models.py
  unit/render/
    test_assets.py
    test_animation.py
    test_effects.py
    test_camera.py
    test_hud.py
  unit/audio/
    test_generated_audio.py
    test_music_director.py
  integration/
    test_campaign_catalog.py
    test_boss_catalog.py
    test_progression_flow.py
    test_presentation_flow.py
  visual/
    conftest.py
    test_screens.py
    test_worlds.py
    test_bosses.py
    baselines/*.json
```

Generated PNG, WAV, JSON, and TTF files are committed release inputs. Each generator supports `--check`, creates its output in a temporary directory, compares bytes or canonical decoded content, and exits nonzero without overwriting committed artifacts when drift is found.

## Locked Upstream Interfaces

Use these signatures verbatim. Reconcile an upstream plan before implementation if its checked-in code differs; do not create a second type with the same meaning.

```text
# windsprig/config.py
@dataclass(frozen=True)
class GameConfig:
    resolution: tuple[int, int] = (1280, 720)
    target_fps: int = 60
    fixed_dt_ms: int = 16
    replay_seed: int = 1337
    max_local_players: int = 4
    max_catch_up_steps: int = 5
    max_frame_elapsed_ms: int = 250

# windsprig/screens/base.py
ScreenId = Literal[
    "boot", "title", "profile", "hub", "world_map", "stage_intro",
    "playing", "paused", "results", "defeat", "settings", "controls",
    "credits", "recovery",
]

@dataclass(frozen=True)
class ScreenTransition:
    target: ScreenId
    payload: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

Screen.fixed_update(self, dt_ms: int, input_frame: InputFrame) -> ScreenTransition | None
Screen.render(self, canvas: pygame.Surface, alpha: float) -> None
Screen.on_enter(self, payload: Mapping[str, object]) -> None
Screen.on_exit(self) -> None

# windsprig/input/roster.py
@dataclass(frozen=True)
class DeviceRef:
    kind: Literal["keyboard", "gamepad"]
    uid: str
    label: str

@dataclass(frozen=True)
class ActivePlayer:
    slot: int
    device: DeviceRef
    color_token: str
    icon_token: str
    is_leader: bool

# windsprig/platform/services.py
AudioService.status(self) -> AudioStatus
AudioService.initialize(self, after_user_gesture: bool = False) -> Awaitable[AudioStatus]
AudioService.play_cue(self, cue_id: str, bus: Literal["music", "sfx"]) -> bool
AudioService.pause(self) -> None
AudioService.resume(self) -> None
AudioService.set_bus_volume(self, bus: Literal["music", "sfx"], value: float) -> None

DisplayService.create_window(self, logical_size: tuple[int, int], fullscreen: bool) -> pygame.Surface
DisplayService.present(self, canvas: pygame.Surface) -> None
DisplayService.set_fullscreen(self, enabled: bool) -> bool

# windsprig/meta/save_models.py -- all models are frozen slotted dataclasses
@dataclass(frozen=True, slots=True)
class SaveProfile:
    profile_id: str
    display_name: str
    unlocked_nodes: frozenset[str]
    unlocked_worlds: frozenset[str]
    collected_mote_ids: frozenset[str]
    best_times_ms: Mapping[str, int]
    clear_counts: Mapping[str, int]
    discovered_abilities: frozenset[str]
    challenge_rewards: frozenset[str]
    play_time_ms: int
    last_played_stage: str | None

@dataclass(frozen=True, slots=True)
class DisplaySettings:
    fullscreen: bool
    integer_scaling: bool

@dataclass(frozen=True, slots=True)
class AudioSettings:
    master_volume: float
    music_volume: float
    sfx_volume: float
    muted: bool

@dataclass(frozen=True, slots=True)
class AccessibilitySettings:
    screen_shake: bool
    reduced_motion: bool
    draw_toggle: bool
    guard_toggle: bool

@dataclass(frozen=True, slots=True)
class ControlSettings:
    keyboard_p1_preset: str
    keyboard_p2_preset: str
    gamepad_mapping: str

@dataclass(frozen=True, slots=True)
class GlobalSettings:
    display: DisplaySettings
    audio: AudioSettings
    accessibility: AccessibilitySettings
    language: str
    controls: ControlSettings

@dataclass(frozen=True, slots=True)
class SaveData:
    save_version: Literal[2]
    campaign_version: str
    profiles: tuple[SaveProfile, SaveProfile, SaveProfile]
    settings: GlobalSettings
    prototype_imported: bool

SaveService.load(self) -> SaveLoadResult
SaveService.save(self, data: SaveData) -> SaveWriteResult

# windsprig/gameplay/snapshot.py
class StageOutcome(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class StageSnapshot:
    frame_index: int
    elapsed_ms: int
    stage_id: str
    world_id: str
    node_id: str
    outcome: StageOutcome
    players: tuple[PlayerView, ...]
    enemies: tuple[EnemyView, ...]
    attacks: tuple[AttackView, ...]
    echo_pickups: tuple[EchoPickupView, ...]
    interactions: tuple[InteractionView, ...]
    checkpoints: tuple[CheckpointView, ...]
    goal_gather: GoalGatherView
    camera_targets: tuple[CameraTargetView, ...]
    collected_mote_ids: tuple[str, ...]

@dataclass(frozen=True)
class StageResult:
    stage_id: str
    world_id: str
    node_id: str
    clear_time_ms: int
    collected_mote_ids: tuple[str, ...]
    discovered_ability_ids: tuple[str, ...]
    active_slots: tuple[int, ...]
    deaths_by_slot: tuple[tuple[int, int], ...]

@dataclass(frozen=True)
class StageFrame:
    simulation: FrameSnapshot
    view: StageSnapshot
    events: tuple[GameEvent, ...]
    result: StageResult | None

StageRuntime(
    config: GameConfig,
    stage: StageSpec,
    ability_registry: AbilityRegistry,
    active_players: Sequence[ActivePlayer],
    seed: int,
)
StageRuntime.step(self, input_frame: InputFrame) -> StageFrame
StageRuntime.sync_active_players(self, active_players: Sequence[ActivePlayer]) -> tuple[GameEvent, ...]
StageRuntime.snapshot(self) -> StageSnapshot
StageRuntime.result: StageResult | None
```

## Interfaces Produced by This Plan

```text
# windsprig/content/models.py and loader.py
@dataclass(frozen=True, slots=True)
class MoteSpec:
    mote_id: str
    tile_x: int
    tile_y: int
    route: Literal["main", "optional", "mastery"]

@dataclass(frozen=True, slots=True)
class StageSpec:
    stage_id: str
    world_id: str
    node_id: str
    order: int
    name_key: str
    intro_key: str
    target_time_ms: int
    width_tiles: int
    height_tiles: int
    tile_size: int
    player_spawns: tuple[tuple[float, float], ...]
    enemy_spawns: tuple[EnemySpawn, ...]
    motes: tuple[MoteSpec, ...]
    checkpoints: tuple[CheckpointSpec, ...]
    interactions: tuple[InteractionSpec, ...]
    solids: tuple[tuple[int, int], ...]
    one_way_tiles: tuple[tuple[int, int], ...]
    hazards: tuple[tuple[int, int], ...]
    navigation: NavigationGraph
    goal_tile: tuple[int, int]
    boss_id: str | None

@dataclass(frozen=True, slots=True)
class CatalogBundle:
    campaign: CampaignCatalog
    bosses: Mapping[str, BossSpec]
    rewards: RewardCatalog

load_catalog_bundle(content_dir: Path) -> CatalogBundle
validate_bundle(bundle: CatalogBundle, assets: AssetManifest, locales: LocaleCatalog) -> ValidationReport

# windsprig/gameplay/bosses.py and snapshot.py
@dataclass(frozen=True, slots=True)
class BossView:
    entity_id: int
    boss_id: str
    phase_id: str
    x: float
    y: float
    width: int
    height: int
    facing: int
    actor_state: str
    hp: int
    maximum_hp: int
    telegraph_id: str | None
    telegraph_remaining_ms: int
    vulnerability_state: Literal["vulnerable", "armored", "hidden", "invulnerable"]

BossDirector.start(self, boss_id: str, entity_id: int) -> BossState
BossDirector.step(self, state: BossState, hp: int, dt_ms: int, rng: DeterministicRng) -> BossStep

# StageSnapshot gains exactly this field before collected_mote_ids:
bosses: tuple[BossView, ...]

# windsprig/meta/completion.py
apply_stage_result(
    profile: SaveProfile,
    result: StageResult,
    catalog: CatalogBundle,
) -> tuple[SaveProfile, CompletionDelta]

completion_percent(profile: SaveProfile, catalog: CatalogBundle) -> Decimal

# windsprig/meta/presentation_models.py
build_profile_cards(save: SaveData, catalog: CatalogBundle, tr: Localizer) -> tuple[ProfileCardVM, ...]
build_results_view(result: StageResult, delta: CompletionDelta, profile: SaveProfile, catalog: CatalogBundle, tr: Localizer) -> ResultsViewModel
build_settings_view(settings: GlobalSettings, capabilities: PlatformCapabilities, tr: Localizer) -> SettingsViewModel

# windsprig/meta/world_map.py
build_world_map_view(
    profile: SaveProfile,
    catalog: CatalogBundle,
    selected_node_id: str,
    tr: Localizer,
) -> WorldMapViewModel

# windsprig/localization.py
Localizer.load(content_dir: Path, language: Literal["en", "ko"]) -> Localizer
Localizer.text(self, key: str, **values: str | int | float) -> str

# windsprig/render/assets.py
AssetCatalog.load(root: Path, manifest: AssetManifest, *, developer_mode: bool = False) -> AssetCatalog
AssetCatalog.image(self, asset_id: str) -> pygame.Surface
AssetCatalog.sound_path(self, cue_id: str) -> Path
AssetCatalog.font(self, size_px: int, weight: int = 500) -> pygame.font.Font

# windsprig/render/camera.py
CameraController.update(
        self,
        targets: tuple[CameraTargetView, ...],
        bounds_px: pygame.Rect,
        dt_ms: int,
        reduced_motion: bool,
) -> CameraView

compute_letterbox(
    window_size: tuple[int, int],
    logical_size: tuple[int, int] = (1280, 720),
    integer_scaling: bool = False,
) -> Letterbox

# windsprig/audio/music.py
MusicDirector.start(self, cue_id: str) -> bool
MusicDirector.handle(self, events: Sequence[GameEvent]) -> tuple[str, ...]
MusicDirector.apply_settings(self, settings: AudioSettings) -> None
```

---

### Task 1: Native content models, strict loaders, and reusable validator

**Files:**
- Create: `windsprig/content/models.py`
- Rewrite: `windsprig/content/loader.py`
- Create: `tools/validate_content.py`
- Create: `tests/helpers/catalog.py`
- Create: `tests/unit/content/test_models.py`
- Create: `tests/unit/content/test_validator.py`

**Interfaces:**
- Consumes: gameplay-owned `EnemySpawn`, `CheckpointSpec`, and `InteractionSpec`; ability IDs listed in Global Constraints.
- Produces: frozen `WorldSpec`, `WorldNode`, `NavigationNode`, `NavigationGraph`, `StageSpec`, `BossAttackSpec`, `BossPhaseSpec`, `BossSpec`, `RewardSpec`, `CampaignCatalog`, `RewardCatalog`, `CatalogBundle`, `ValidationIssue`, `ValidationReport`, `load_catalog_bundle()`, and `validate_bundle()`.

- [ ] **Step 1: Write failing strict-model and validator tests**

```python
# tests/unit/content/test_models.py
from pathlib import Path

import pytest

from windsprig.content.loader import ContentError, load_catalog_bundle
from tests.helpers.catalog import write_minimal_bundle


def test_loader_rejects_unknown_stage_fields(tmp_path: Path) -> None:
    write_minimal_bundle(tmp_path, stage_patch={"copied_layout": True})
    with pytest.raises(ContentError, match=r"campaign\.stages\[0\].copied_layout: unknown field"):
        load_catalog_bundle(tmp_path)


def test_stage_layout_signature_includes_geometry_encounters_and_mote_routes(tmp_path: Path) -> None:
    bundle = load_catalog_bundle(write_minimal_bundle(tmp_path))
    stage = next(iter(bundle.campaign.stages.values()))
    assert stage.layout_signature() == "852bdf67e28f429de18f"


# tests/unit/content/test_validator.py
from windsprig.content.validator import validate_bundle
from tests.helpers.catalog import load_minimal_bundle


def test_validator_reports_duplicate_layout_mote_and_unreachable_goal() -> None:
    bundle, assets, locales = load_minimal_bundle(
        duplicate_stage=True,
        duplicate_mote=True,
        disconnect_goal=True,
    )
    report = validate_bundle(bundle, assets, locales)
    assert [(item.code, item.path) for item in report.errors] == [
        ("duplicate_layout", "campaign.stages.demo_02"),
        ("duplicate_mote_id", "campaign.stages.demo_02.motes[0]"),
        ("unreachable_goal", "campaign.stages.demo_02.navigation.goal"),
    ]
```

- [ ] **Step 2: Run the focused tests and confirm imports fail**

Run: `python -m pytest tests/unit/content/test_models.py tests/unit/content/test_validator.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'windsprig.content.validator'` or the first missing content symbol.

- [ ] **Step 3: Implement the exact frozen schema and canonical layout signature**

```python
# windsprig/content/models.py
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Literal, Mapping

RouteKind = Literal["main", "optional", "mastery"]
InteractionKind = Literal[
    "gust_lift", "breakable", "conveyor", "heat_vent", "timed_shutter",
    "current", "buoyant_pod", "falling_water", "rail", "conductor",
    "rotating_tower", "mirror", "color_beam", "gravity_bloom",
    "silence_field", "ability_lock", "breakable_floor", "switch",
]


@dataclass(frozen=True, slots=True)
class EnemySpawn:
    spawn_id: str
    kind: str
    ability_id: str | None
    tile_x: int
    tile_y: int
    patrol_left: int
    patrol_right: int
    elite: bool = False


@dataclass(frozen=True, slots=True)
class MoteSpec:
    mote_id: str
    tile_x: int
    tile_y: int
    route: RouteKind


@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    checkpoint_id: str
    tile_x: int
    tile_y: int


@dataclass(frozen=True, slots=True)
class InteractionSpec:
    interaction_id: str
    kind: InteractionKind
    tile_x: int
    tile_y: int
    width_tiles: int = 1
    height_tiles: int = 1
    params: tuple[tuple[str, int | float | str | bool], ...] = ()


@dataclass(frozen=True, slots=True)
class NavigationNode:
    nav_id: str
    tile_x: int
    tile_y: int
    route: RouteKind


@dataclass(frozen=True, slots=True)
class NavigationGraph:
    start: str
    goal: str
    nodes: tuple[NavigationNode, ...]
    edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class StageSpec:
    stage_id: str
    world_id: str
    node_id: str
    order: int
    name_key: str
    intro_key: str
    target_time_ms: int
    width_tiles: int
    height_tiles: int
    tile_size: int
    player_spawns: tuple[tuple[float, float], ...]
    enemy_spawns: tuple[EnemySpawn, ...]
    motes: tuple[MoteSpec, ...]
    checkpoints: tuple[CheckpointSpec, ...]
    interactions: tuple[InteractionSpec, ...]
    solids: tuple[tuple[int, int], ...]
    one_way_tiles: tuple[tuple[int, int], ...]
    hazards: tuple[tuple[int, int], ...]
    navigation: NavigationGraph
    goal_tile: tuple[int, int]
    boss_id: str | None

    @property
    def pixel_width(self) -> int:
        return self.width_tiles * self.tile_size

    @property
    def pixel_height(self) -> int:
        return self.height_tiles * self.tile_size

    def layout_signature(self) -> str:
        payload = {
            "size": [self.width_tiles, self.height_tiles],
            "solids": sorted(self.solids),
            "one_way": sorted(self.one_way_tiles),
            "hazards": sorted(self.hazards),
            "encounters": [
                [e.kind, e.ability_id, e.tile_x, e.tile_y, e.elite]
                for e in self.enemy_spawns
            ],
            "mote_routes": [
                [m.tile_x, m.tile_y, m.route] for m in self.motes
            ],
            "interactions": [
                [i.kind, i.tile_x, i.tile_y, i.width_tiles, i.height_tiles, list(i.params)]
                for i in self.interactions
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class WorldNode:
    node_id: str
    world_id: str
    stage_id: str
    position: tuple[int, int]
    requires: tuple[str, ...]
    is_boss: bool


@dataclass(frozen=True, slots=True)
class WorldSpec:
    world_id: str
    order: int
    name_key: str
    identity_key: str
    mechanic_keys: tuple[str, ...]
    palette_id: str
    nodes: tuple[WorldNode, ...]


@dataclass(frozen=True, slots=True)
class BossAttackSpec:
    attack_id: str
    telegraph_ms: int
    active_ms: int
    recovery_ms: int
    marker: Literal["ground", "silhouette", "lane", "orbit", "beam", "arena"]
    cue_id: str
    parameters: tuple[tuple[str, int | float | str | bool], ...]


@dataclass(frozen=True, slots=True)
class BossPhaseSpec:
    phase_id: str
    enter_at_hp_ratio: float
    vulnerability: Literal["vulnerable", "armored", "hidden", "invulnerable"]
    arena_rule: str
    attacks: tuple[BossAttackSpec, ...]


@dataclass(frozen=True, slots=True)
class BossSpec:
    boss_id: str
    name_key: str
    max_hp: int
    visual_id: str
    phases: tuple[BossPhaseSpec, ...]


@dataclass(frozen=True, slots=True)
class RewardSpec:
    threshold: int
    reward_id: str
    kind: Literal["challenge", "gallery", "palette"]
    name_key: str


@dataclass(frozen=True, slots=True)
class CampaignCatalog:
    version: str
    worlds: tuple[WorldSpec, ...]
    stages: Mapping[str, StageSpec]
    nodes: Mapping[str, WorldNode]


@dataclass(frozen=True, slots=True)
class RewardCatalog:
    mote_thresholds: tuple[RewardSpec, ...]


@dataclass(frozen=True, slots=True)
class CatalogBundle:
    campaign: CampaignCatalog
    bosses: Mapping[str, BossSpec]
    rewards: RewardCatalog


def frozen_map(values: dict[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(sorted(values.items())))
```

The loader must use explicit required/optional key sets for every object, report paths such as `campaign.stages[4].motes[2].mote_id`, reject booleans where an integer is expected, reject non-finite floats, sort map keys, convert every mutable JSON list to a tuple, and return `MappingProxyType` maps. It must not preserve the legacy `energy_spheres` integer/count representation.

- [ ] **Step 4: Implement one deterministic validator entry point and CLI**

```python
# tools/validate_content.py
from __future__ import annotations

import argparse
from pathlib import Path

from windsprig.content.loader import load_asset_manifest, load_catalog_bundle, load_locales
from windsprig.content.validator import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", type=Path, default=Path("windsprig/content"))
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    parser.add_argument("--all", action="store_true", dest="validate_all")
    args = parser.parse_args()
    bundle = load_catalog_bundle(args.content)
    manifest = load_asset_manifest(args.content / "assets.json")
    locales = load_locales(args.content)
    report = validate_bundle(bundle, manifest, locales, asset_root=args.assets)
    for issue in report.errors:
        print(f"ERROR {issue.code} {issue.path}: {issue.message}")
    if report.errors:
        print(f"FAILED: {len(report.errors)} validation errors")
        return 1
    counts = report.counts
    print(
        "OK: "
        f"{counts['worlds']} worlds, {counts['stages']} stages, "
        f"{counts['bosses']} bosses, {counts['motes']} motes, "
        f"{counts['locales']} locales, {counts['music']} music cues, "
        f"{counts['sfx']} sfx cues, {counts['duplicate_layouts']} duplicate layouts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`validate_bundle()` performs these checks in this exact stable order: schema/load issues; world/node/stage references; exact counts; ID uniqueness; per-stage bounds; safe spawn tiles; three motes per stage; navigation reachability from start to goal/checkpoints/motes; ability-source coverage; boss existence/phase rules; layout signature uniqueness; reward threshold ordering; locale key parity and formatting placeholders; manifest ID/reference/file presence; font license; provenance records; music/SFX coverage. Sort each category by path before concatenating errors.

- [ ] **Step 5: Run model and validator tests**

Run: `python -m pytest tests/unit/content/test_models.py tests/unit/content/test_validator.py -q`

Expected: `4 passed`.

- [ ] **Step 6: Commit the schema and validation boundary**

```powershell
git add windsprig/content/models.py windsprig/content/loader.py tools/validate_content.py tests/helpers/catalog.py tests/unit/content/test_models.py tests/unit/content/test_validator.py
git commit -m "feat: define strict campaign content contracts"
```

---
### Task 2: Deterministically author all 30 stages, 90 motes, and rewards

**Files:**
- Create: `tools/generate_campaign.py`
- Rewrite: `windsprig/content/campaign.json`
- Create: `windsprig/content/rewards.json`
- Create: `tests/integration/test_campaign_catalog.py`

**Interfaces:**
- Consumes: `StageSpec`, `CampaignCatalog`, the six ability IDs, and the validator from Task 1.
- Produces: canonical JSON containing six `WorldSpec` records, 30 `StageSpec` records, 30 nodes, 90 mote IDs, six ability-source families, 18 enemy silhouettes, and 18 optional reward thresholds.

- [ ] **Step 1: Write the failing complete-catalog test**

```python
# tests/integration/test_campaign_catalog.py
from pathlib import Path

from windsprig.content.loader import load_catalog_bundle


def test_campaign_has_exact_release_catalog_and_stable_ids() -> None:
    bundle = load_catalog_bundle(Path("windsprig/content"))
    campaign = bundle.campaign
    stages = tuple(campaign.stages.values())
    mote_ids = [mote.mote_id for stage in stages for mote in stage.motes]
    assert [world.world_id for world in campaign.worlds] == [
        "world_1", "world_2", "world_3",
        "world_4", "world_5", "world_6",
    ]
    assert len(stages) == 30
    assert sum(stage.boss_id is not None for stage in stages) == 6
    assert len(mote_ids) == len(set(mote_ids)) == 90
    assert all(len(stage.motes) == 3 for stage in stages)
    assert len({stage.layout_signature() for stage in stages}) == 30
    assert {enemy.ability_id for stage in stages for enemy in stage.enemy_spawns} >= {
        "bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest",
    }


def test_progression_is_one_connected_30_node_chain() -> None:
    bundle = load_catalog_bundle(Path("windsprig/content"))
    nodes = [node for world in bundle.campaign.worlds for node in world.nodes]
    assert nodes[0].requires == ()
    assert all(nodes[index].requires == (nodes[index - 1].node_id,) for index in range(1, 30))
    assert [node.is_boss for node in nodes].count(True) == 6
```

- [ ] **Step 2: Run the catalog test and confirm the legacy content fails**

Run: `python -m pytest tests/integration/test_campaign_catalog.py -q`

Expected: tests fail because native fields `version`, `name_key`, `motes`, `navigation`, and `boss_id` are absent or because legacy ability IDs are present.

- [ ] **Step 3: Add the complete reviewed recipe table**

Use this exact schema and data in `tools/generate_campaign.py`. Coordinates are tile coordinates in a 24-tile-high stage with the walkable ground surface at row 20. `gaps` contains half-open x ranges; `platforms` and `hazards` contain `(x, y, width)`; mechanics contain `(kind, x, y, width, height)`; encounters contain `(enemy_kind, ability_id, x, y, elite)`; mote triples contain `(x, y, route)`.

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
from typing import Literal

Route = Literal["main", "optional", "mastery"]


@dataclass(frozen=True)
class Recipe:
    world: str
    slug: str
    title: str
    target_ms: int
    width: int
    gaps: tuple[tuple[int, int], ...]
    platforms: tuple[tuple[int, int, int], ...]
    hazards: tuple[tuple[int, int, int], ...]
    mechanics: tuple[tuple[str, int, int, int, int], ...]
    encounters: tuple[tuple[str, str | None, int, int, bool], ...]
    motes: tuple[tuple[int, int, Route], tuple[int, int, Route], tuple[int, int, Route]]
    checkpoints: tuple[int, ...]
    boss_id: str | None = None


WORLDS = (
    ("world_1", "Sunleaf Vale", ("gust_lift", "breakable"), "palette.sunleaf",
     ((150, 500), (350, 410), (555, 480), (765, 345), (1040, 300))),
    ("world_2", "Emberglass Works", ("conveyor", "heat_vent", "timed_shutter"), "palette.emberglass",
     ((145, 430), (350, 505), (560, 390), (780, 475), (1045, 330))),
    ("world_3", "Tidemoon Grotto", ("current", "buoyant_pod", "falling_water"), "palette.tidemoon",
     ((140, 510), (360, 455), (555, 340), (790, 410), (1040, 285))),
    ("world_4", "Thunderrail Heights", ("rail", "conductor", "rotating_tower"), "palette.thunderrail",
     ((145, 490), (345, 350), (565, 445), (780, 315), (1040, 390))),
    ("world_5", "Prismbloom Dream", ("mirror", "color_beam", "gravity_bloom"), "palette.prismbloom",
     ((140, 455), (350, 330), (565, 480), (785, 365), (1040, 265))),
    ("world_6", "Stillstar Crown", ("silence_field", "ability_lock"), "palette.stillstar",
     ((145, 500), (355, 385), (570, 500), (790, 335), (1040, 250))),
)

R = Recipe
STAGES = (
    R("world_1", "first-flight", "First Flight", 150000, 92, ((31,35),(68,72)),
      ((12,16,7),(39,14,6),(57,12,5),(77,15,6)), ((31,20,4),(68,20,4)),
      (("gust_lift",18,16,3,4),("gust_lift",60,12,3,8)),
      (("breezeling","galehook",22,19,False),("bramblekin","bloomblade",49,19,False),("millmite","voltsong",80,19,False)),
      ((17,14,"main"),(46,12,"optional"),(79,13,"mastery")),(38,67)),
    R("world_1", "millstream-run", "Millstream Run", 165000, 98, ((24,28),(51,56),(82,86)),
      ((9,15,6),(31,13,8),(60,16,5),(72,11,7),(88,14,5)), ((24,20,4),(52,20,4),(82,20,4)),
      (("gust_lift",26,13,2,7),("breakable",43,17,3,3),("gust_lift",83,11,3,9)),
      (("millmite","voltsong",18,19,False),("breezeling","galehook",36,12,False),("bramblekin","bloomblade",64,19,True),("breezeling","galehook",90,13,False)),
      ((13,13,"main"),(44,15,"optional"),(75,9,"mastery")),(48,80)),
    R("world_1", "bramble-updraft", "Bramble Updraft", 180000, 104, ((19,23),(45,49),(73,79)),
      ((7,14,6),(27,16,6),(36,11,5),(52,13,8),(64,9,5),(82,15,9),(94,11,5)), ((19,20,4),(45,20,4),(74,20,5)),
      (("breakable",30,14,2,2),("gust_lift",47,12,3,8),("breakable",86,13,3,2)),
      (("bramblekin","bloomblade",15,19,False),("millmite","voltsong",32,15,False),("breezeling","galehook",58,12,False),("bramblekin","bloomblade",69,19,True),("millmite","voltsong",91,14,False)),
      ((10,12,"main"),(38,9,"optional"),(96,9,"mastery")),(43,72)),
    R("world_1", "valewind-gauntlet", "Valewind Gauntlet", 210000, 112, ((16,20),(37,42),(61,65),(88,94)),
      ((6,15,5),(22,12,7),(45,15,6),(53,9,5),(68,13,8),(79,8,6),(97,14,9)), ((16,20,4),(38,20,4),(61,20,4),(89,20,5)),
      (("gust_lift",17,11,3,9),("breakable",48,13,2,2),("gust_lift",62,9,3,11),("breakable",101,12,3,2)),
      (("breezeling","galehook",12,19,False),("bramblekin","bloomblade",27,11,True),("millmite","voltsong",50,14,False),("breezeling","galehook",73,12,True),("bramblekin","bloomblade",84,19,False),("millmite","tempest",103,13,True)),
      ((8,13,"main"),(55,7,"mastery"),(102,12,"optional")),(36,87)),
    R("world_1", "rootjaw-burrow", "Rootjaw Burrow", 240000, 100, ((27,31),(52,56)),
      ((10,15,7),(34,12,6),(59,14,8),(78,11,6)), ((27,20,4),(52,20,4)),
      (("gust_lift",28,12,3,8),("breakable",64,12,3,2),("switch",82,10,2,2)),
      (("bramblekin","bloomblade",19,19,True),("breezeling","galehook",42,11,False),("millmite","voltsong",70,19,True)),
      ((13,13,"main"),(37,10,"optional"),(80,9,"mastery")),(50,78),"rootjaw"),

    R("world_2", "kilnwalk", "Kilnwalk", 150000, 94, ((29,34),(69,73)),
      ((11,15,6),(38,13,7),(55,16,6),(77,12,7)), ((29,20,5),(69,20,4)),
      (("conveyor",15,19,8,1),("heat_vent",31,17,2,3),("timed_shutter",62,14,2,6)),
      (("cinderling","cinder",21,19,False),("slagroller","stoneheart",48,19,False),("shutterimp","galehook",80,11,False)),
      ((14,13,"main"),(43,11,"optional"),(81,10,"mastery")),(36,67)),
    R("world_2", "conveyor-crossing", "Conveyor Crossing", 170000, 101, ((20,24),(46,51),(78,84)),
      ((7,14,6),(27,16,7),(36,10,6),(54,13,8),(66,8,6),(87,15,8)), ((20,20,4),(46,20,5),(79,20,5)),
      (("conveyor",9,19,10,1),("conveyor",28,15,8,1),("heat_vent",48,16,2,4),("timed_shutter",73,9,2,11)),
      (("slagroller","stoneheart",16,19,False),("cinderling","cinder",32,15,False),("shutterimp","galehook",58,12,False),("slagroller","stoneheart",91,14,True)),
      ((10,12,"main"),(38,8,"optional"),(68,6,"mastery")),(45,77)),
    R("world_2", "shutter-furnace", "Shutter Furnace", 185000, 106, ((25,30),(57,61),(90,95)),
      ((8,16,6),(33,12,9),(48,8,5),(64,15,7),(76,10,8),(98,14,5)), ((25,20,5),(57,20,4),(90,20,5)),
      (("timed_shutter",19,12,2,8),("heat_vent",27,15,2,5),("conveyor",65,14,9,1),("timed_shutter",87,9,2,11)),
      (("shutterimp","galehook",14,15,False),("cinderling","cinder",38,11,False),("slagroller","stoneheart",68,14,True),("cinderling","cinder",80,9,False),("shutterimp","voltsong",100,13,True)),
      ((11,14,"main"),(50,6,"mastery"),(79,8,"optional")),(52,88)),
    R("world_2", "molten-clockwork", "Molten Clockwork", 220000, 116, ((18,23),(42,47),(65,70),(94,101)),
      ((6,13,6),(26,16,7),(33,9,5),(50,12,8),(73,15,8),(84,8,6),(104,13,7)), ((18,20,5),(42,20,5),(65,20,5),(95,20,6)),
      (("conveyor",7,19,10,1),("heat_vent",20,14,2,6),("timed_shutter",39,10,2,10),("conveyor",74,14,10,1),("heat_vent",98,13,2,7)),
      (("cinderling","cinder",13,19,False),("slagroller","stoneheart",30,15,True),("shutterimp","galehook",54,11,False),("cinderling","cinder",78,14,True),("slagroller","stoneheart",89,19,False),("shutterimp","tempest",108,12,True)),
      ((9,11,"main"),(35,7,"mastery"),(106,11,"optional")),(41,92)),
    R("world_2", "crucible-crab", "Crucible Crab", 250000, 102, ((32,37),(61,66)),
      ((12,15,7),(40,11,7),(69,14,8),(84,10,6)), ((32,20,5),(61,20,5)),
      (("conveyor",13,19,10,1),("heat_vent",34,15,2,5),("timed_shutter",79,9,2,11)),
      (("cinderling","cinder",20,19,True),("shutterimp","voltsong",45,10,False),("slagroller","stoneheart",72,13,True)),
      ((15,13,"main"),(43,9,"optional"),(86,8,"mastery")),(55,81),"crucible_crab"),

    R("world_3", "pod-pools", "Pod Pools", 155000, 96, ((26,32),(70,76)),
      ((9,16,7),(35,13,8),(52,10,6),(79,15,8)), ((26,20,6),(70,20,6)),
      (("current",27,15,5,5),("buoyant_pod",42,16,2,2),("falling_water",62,8,3,12)),
      (("bubblefin","cinder",18,19,False),("shellskiff","stoneheart",47,12,False),("moonjelly","voltsong",82,14,False)),
      ((12,14,"main"),(54,8,"optional"),(64,6,"mastery")),(39,69)),
    R("world_3", "current-choir", "Current Choir", 175000, 103, ((18,24),(49,55),(83,88)),
      ((6,14,6),(27,16,8),(38,9,6),(58,13,9),(72,7,6),(91,15,7)), ((18,20,6),(49,20,6),(83,20,5)),
      (("current",19,12,5,8),("buoyant_pod",32,15,2,2),("falling_water",50,9,4,11),("current",84,14,4,6)),
      (("bubblefin","cinder",13,19,False),("moonjelly","voltsong",31,15,False),("shellskiff","stoneheart",62,12,True),("bubblefin","galehook",94,14,False)),
      ((9,12,"main"),(40,7,"optional"),(74,5,"mastery")),(47,81)),
    R("world_3", "waterfall-vault", "Waterfall Vault", 190000, 108, ((22,28),(54,59),(88,94)),
      ((8,15,7),(31,11,8),(43,7,5),(62,14,8),(75,9,7),(97,13,6)), ((22,20,6),(54,20,5),(88,20,6)),
      (("falling_water",23,8,5,12),("buoyant_pod",35,14,2,2),("current",55,15,4,5),("falling_water",86,7,3,13)),
      (("moonjelly","voltsong",16,14,False),("shellskiff","stoneheart",36,10,False),("bubblefin","galehook",66,13,False),("moonjelly","voltsong",78,8,True),("shellskiff","cinder",100,12,True)),
      ((11,13,"main"),(45,5,"mastery"),(77,7,"optional")),(51,86)),
    R("world_3", "mooncurrent-maze", "Mooncurrent Maze", 225000, 118, ((17,23),(39,45),(67,73),(98,105)),
      ((6,16,5),(26,12,8),(33,7,5),(48,15,8),(58,9,6),(76,13,8),(87,6,6),(108,14,6)), ((17,20,6),(39,20,6),(67,20,6),(98,20,7)),
      (("current",18,11,5,9),("falling_water",40,8,5,12),("buoyant_pod",52,14,2,2),("current",68,12,5,8),("falling_water",99,7,5,13)),
      (("bubblefin","galehook",13,19,False),("shellskiff","stoneheart",30,11,True),("moonjelly","voltsong",51,14,False),("bubblefin","cinder",80,12,True),("shellskiff","stoneheart",91,19,False),("moonjelly","tempest",110,13,True)),
      ((8,14,"main"),(35,5,"mastery"),(89,4,"optional")),(38,96)),
    R("world_3", "luma-eel", "Luma Eel", 255000, 104, ((30,36),(63,69)),
      ((11,14,8),(39,10,7),(72,13,8),(88,8,6)), ((30,20,6),(63,20,6)),
      (("current",31,12,5,8),("buoyant_pod",44,13,2,2),("falling_water",83,7,3,13)),
      (("bubblefin","galehook",19,19,True),("moonjelly","voltsong",45,9,False),("shellskiff","stoneheart",76,12,True)),
      ((14,12,"main"),(42,8,"optional"),(90,6,"mastery")),(57,84),"luma_eel"),

    R("world_4", "live-line", "Live Line", 155000, 97, ((28,33),(72,77)),
      ((10,15,7),(36,12,8),(55,16,6),(80,11,8)), ((28,20,5),(72,20,5)),
      (("rail",13,17,12,1),("conductor",42,10,2,2),("rotating_tower",66,8,4,12)),
      (("coilbird","voltsong",20,14,False),("railrunner","galehook",48,19,False),("stormlens","cinder",83,10,False)),
      ((13,13,"main"),(43,10,"optional"),(68,6,"mastery")),(40,70)),
    R("world_4", "conductor-crossing", "Conductor Crossing", 175000, 102, ((21,26),(50,56),(84,90)),
      ((7,14,6),(29,16,8),(39,8,6),(59,13,8),(73,7,6),(93,15,5)), ((21,20,5),(50,20,6),(84,20,6)),
      (("rail",8,17,12,1),("conductor",32,14,2,2),("conductor",63,11,2,2),("rotating_tower",85,8,5,12)),
      (("railrunner","galehook",15,19,False),("coilbird","voltsong",34,15,False),("stormlens","cinder",62,12,True),("coilbird","voltsong",95,13,False)),
      ((10,12,"main"),(41,6,"optional"),(75,5,"mastery")),(48,82)),
    R("world_4", "turntable-tempest", "Turntable Tempest", 195000, 110, ((24,29),(56,62),(92,98)),
      ((8,16,7),(32,11,8),(45,7,6),(65,14,8),(78,9,7),(101,13,5)), ((24,20,5),(56,20,6),(92,20,6)),
      (("rotating_tower",25,9,4,11),("rail",34,12,15,1),("conductor",69,12,2,2),("rotating_tower",94,7,4,13)),
      (("stormlens","cinder",16,15,False),("coilbird","voltsong",37,10,False),("railrunner","galehook",69,19,True),("stormlens","voltsong",81,8,False),("coilbird","cinder",103,12,True)),
      ((11,14,"main"),(47,5,"mastery"),(80,7,"optional")),(53,90)),
    R("world_4", "observatory-ascent", "Observatory Ascent", 230000, 120, ((18,24),(43,49),(70,76),(101,108)),
      ((6,13,6),(27,16,8),(35,8,6),(52,12,8),(60,6,5),(79,15,8),(90,9,7),(111,13,6)), ((18,20,6),(43,20,6),(70,20,6),(101,20,7)),
      (("rail",7,14,10,1),("rotating_tower",19,8,5,12),("conductor",55,10,2,2),("rail",80,16,12,1),("rotating_tower",103,6,5,14)),
      (("railrunner","galehook",13,19,False),("coilbird","voltsong",31,15,True),("stormlens","cinder",56,11,False),("railrunner","galehook",83,14,True),("coilbird","voltsong",94,8,False),("stormlens","tempest",113,12,True)),
      ((9,11,"main"),(62,4,"mastery"),(92,7,"optional")),(42,98)),
    R("world_4", "volt-roc", "Volt Roc", 260000, 106, ((31,37),(65,71)),
      ((12,15,7),(40,10,8),(74,14,8),(91,8,6)), ((31,20,6),(65,20,6)),
      (("rail",13,17,12,1),("conductor",44,8,2,2),("rotating_tower",86,7,5,13)),
      (("coilbird","voltsong",20,14,True),("stormlens","cinder",46,9,False),("railrunner","galehook",78,19,True)),
      ((15,13,"main"),(43,8,"optional"),(93,6,"mastery")),(59,87),"volt_roc"),

    R("world_5", "mirror-seed", "Mirror Seed", 160000, 98, ((27,32),(71,76)),
      ((10,15,7),(35,12,8),(54,16,6),(79,11,8)), ((27,20,5),(71,20,5)),
      (("mirror",18,13,2,4),("color_beam",39,10,9,2),("gravity_bloom",64,12,4,8)),
      (("petalisk","bloomblade",21,19,False),("mirrormite","galehook",47,11,False),("gravitybud","stoneheart",82,10,False)),
      ((13,13,"main"),(40,10,"optional"),(66,8,"mastery")),(42,69)),
    R("world_5", "chromatic-canopy", "Chromatic Canopy", 180000, 104, ((20,25),(48,54),(85,91)),
      ((7,14,6),(28,16,8),(39,8,6),(57,13,8),(72,7,6),(94,15,6)), ((20,20,5),(48,20,6),(85,20,6)),
      (("color_beam",9,12,11,2),("mirror",34,14,2,4),("gravity_bloom",50,10,4,10),("mirror",79,5,2,6)),
      (("petalisk","bloomblade",15,19,False),("gravitybud","stoneheart",33,15,False),("mirrormite","galehook",61,12,True),("petalisk","cinder",96,14,False)),
      ((10,12,"main"),(41,6,"optional"),(74,5,"mastery")),(46,83)),
    R("world_5", "gravity-petal", "Gravity Petal", 200000, 111, ((23,29),(58,64),(93,99)),
      ((8,16,7),(32,11,8),(46,7,6),(67,14,8),(80,8,7),(102,13,6)), ((23,20,6),(58,20,6),(93,20,6)),
      (("gravity_bloom",24,9,5,11),("mirror",38,9,2,4),("color_beam",61,12,12,2),("gravity_bloom",94,7,5,13)),
      (("gravitybud","stoneheart",16,15,False),("petalisk","bloomblade",37,10,False),("mirrormite","galehook",71,13,True),("gravitybud","voltsong",83,7,False),("petalisk","cinder",104,12,True)),
      ((11,14,"main"),(48,5,"mastery"),(82,6,"optional")),(55,91)),
    R("world_5", "refraction-labyrinth", "Refraction Labyrinth", 235000, 121, ((17,23),(44,50),(72,78),(103,110)),
      ((6,13,6),(26,16,8),(35,8,6),(53,12,8),(62,6,5),(81,15,8),(92,9,7),(113,13,6)), ((17,20,6),(44,20,6),(72,20,6),(103,20,7)),
      (("mirror",14,11,2,5),("color_beam",18,9,14,2),("gravity_bloom",45,8,5,12),("mirror",68,4,2,6),("color_beam",83,13,12,2)),
      (("petalisk","bloomblade",13,19,False),("mirrormite","galehook",30,15,True),("gravitybud","stoneheart",57,11,False),("petalisk","cinder",85,14,True),("mirrormite","voltsong",96,8,False),("gravitybud","tempest",115,12,True)),
      ((9,11,"main"),(64,4,"mastery"),(94,7,"optional")),(43,100)),
    R("world_5", "prism-warden", "Prism Warden", 265000, 108, ((32,38),(67,73)),
      ((12,15,7),(41,10,8),(76,14,8),(93,8,6)), ((32,20,6),(67,20,6)),
      (("mirror",19,13,2,4),("color_beam",43,8,10,2),("gravity_bloom",88,6,5,14)),
      (("petalisk","bloomblade",20,19,True),("mirrormite","voltsong",47,9,False),("gravitybud","stoneheart",80,13,True)),
      ((15,13,"main"),(44,8,"optional"),(95,6,"mastery")),(61,89),"prism_warden"),

    R("world_6", "hushed-court", "Hushed Court", 165000, 100, ((29,34),(74,80)),
      ((10,15,7),(37,12,8),(56,16,6),(83,11,8)), ((29,20,5),(74,20,6)),
      (("silence_field",18,11,7,9),("ability_lock",44,13,4,7),("gust_lift",66,12,3,8)),
      (("hushshade","bloomblade",21,19,False),("lockwarden","stoneheart",49,11,False),("riftling","voltsong",86,10,False)),
      ((13,13,"main"),(42,10,"optional"),(68,8,"mastery")),(45,72)),
    R("world_6", "shattered-orbit", "Shattered Orbit", 185000, 106, ((21,27),(51,57),(87,93)),
      ((7,14,6),(30,16,8),(41,8,6),(60,13,8),(75,7,6),(96,15,6)), ((21,20,6),(51,20,6),(87,20,6)),
      (("gravity_bloom",22,10,5,10),("silence_field",35,9,7,11),("rail",62,14,12,1),("ability_lock",82,8,4,12)),
      (("riftling","voltsong",15,19,False),("hushshade","bloomblade",35,15,False),("lockwarden","stoneheart",64,12,True),("riftling","galehook",98,14,False)),
      ((10,12,"main"),(43,6,"optional"),(77,5,"mastery")),(49,85)),
    R("world_6", "locked-echoes", "Locked Echoes", 205000, 113, ((24,30),(60,66),(95,102)),
      ((8,16,7),(33,11,8),(47,7,6),(69,14,8),(82,8,7),(105,13,5)), ((24,20,6),(60,20,6),(95,20,7)),
      (("ability_lock",25,9,5,11),("timed_shutter",39,8,2,12),("silence_field",61,10,6,10),("conductor",87,6,2,2)),
      (("lockwarden","stoneheart",16,15,False),("hushshade","bloomblade",38,10,False),("riftling","galehook",73,13,True),("lockwarden","cinder",85,7,False),("hushshade","voltsong",107,12,True)),
      ((11,14,"main"),(49,5,"mastery"),(84,6,"optional")),(57,93)),
    R("world_6", "crown-of-motion", "Crown of Motion", 240000, 124, ((18,24),(45,51),(74,80),(106,113)),
      ((6,13,6),(27,16,8),(36,8,6),(54,12,8),(64,6,5),(83,15,8),(94,9,7),(116,13,6)), ((18,20,6),(45,20,6),(74,20,6),(106,20,7)),
      (("silence_field",19,9,6,11),("heat_vent",46,14,2,6),("current",75,11,5,9),("mirror",90,6,2,6),("ability_lock",107,7,5,13)),
      (("hushshade","bloomblade",13,19,False),("lockwarden","stoneheart",31,15,True),("riftling","galehook",58,11,False),("hushshade","cinder",87,14,True),("lockwarden","voltsong",98,8,False),("riftling","tempest",118,12,True)),
      ((9,11,"main"),(66,4,"mastery"),(96,7,"optional")),(44,103)),
    R("world_6", "the-stillness", "The Stillness", 280000, 112, ((34,40),(70,76)),
      ((12,15,7),(43,10,8),(79,14,8),(97,8,6)), ((34,20,6),(70,20,6)),
      (("silence_field",18,11,8,9),("ability_lock",46,8,5,12),("gravity_bloom",92,6,5,14)),
      (("hushshade","bloomblade",20,19,True),("riftling","voltsong",49,9,False),("lockwarden","stoneheart",83,13,True)),
      ((15,13,"main"),(46,8,"optional"),(99,6,"mastery")),(64,93),"the_stillness"),
)

REWARDS = tuple(
    (threshold, reward_id, kind)
    for threshold, reward_id, kind in (
        (6,"gallery.sunleaf","gallery"), (12,"palette.mint","palette"),
        (18,"challenge.sunleaf","challenge"), (24,"gallery.emberglass","gallery"),
        (30,"palette.ember","palette"), (36,"challenge.emberglass","challenge"),
        (42,"gallery.tidemoon","gallery"), (48,"palette.moon","palette"),
        (54,"challenge.tidemoon","challenge"), (60,"gallery.thunderrail","gallery"),
        (66,"palette.storm","palette"), (72,"challenge.thunderrail","challenge"),
        (78,"gallery.prismbloom","gallery"), (82,"palette.prism","palette"),
        (84,"challenge.prismbloom","challenge"), (86,"gallery.stillstar","gallery"),
        (88,"palette.stillstar","palette"), (90,"challenge.stillstar","challenge"),
    )
)
```

- [ ] **Step 4: Implement deterministic expansion and canonical writes**

```python
# append to tools/generate_campaign.py
def run_cells(run: tuple[int, int, int]) -> list[list[int]]:
    x, y, width = run
    return [[tile_x, y] for tile_x in range(x, x + width)]


def stage_payload(recipe: Recipe, world_index: int, stage_index: int) -> dict[str, object]:
    stage_id = f"{recipe.world}_stage_{stage_index}"
    node_id = f"{recipe.world}_node_{stage_index}"
    gap_x = {x for start, stop in recipe.gaps for x in range(start, stop)}
    solids = [
        [x, y]
        for y in range(20, 24)
        for x in range(recipe.width)
        if x not in gap_x
    ]
    one_way = [cell for platform in recipe.platforms for cell in run_cells(platform)]
    hazards = [cell for hazard in recipe.hazards for cell in run_cells(hazard)]
    checkpoint_ids = [f"{stage_id}:checkpoint:{n + 1}" for n in range(len(recipe.checkpoints))]
    main_nodes = (
        [{"nav_id": "start", "tile_x": 2, "tile_y": 19, "route": "main"}]
        + [
            {"nav_id": checkpoint_ids[n], "tile_x": x, "tile_y": 19, "route": "main"}
            for n, x in enumerate(recipe.checkpoints)
        ]
        + [{"nav_id": "goal", "tile_x": recipe.width - 4, "tile_y": 19, "route": "main"}]
    )
    mote_nodes = [
        {
            "nav_id": f"nav.{mote_id}",
            "tile_x": x,
            "tile_y": y,
            "route": route,
        }
        for mote_id, (x, y, route) in zip(
            [f"{stage_id}:mote:{number}" for number in range(1, 4)],
            recipe.motes,
            strict=True,
        )
    ]
    main_ids = [node["nav_id"] for node in main_nodes]
    edges = [[main_ids[n], main_ids[n + 1]] for n in range(len(main_ids) - 1)]
    for mote in mote_nodes:
        nearest = min(main_nodes, key=lambda node: abs(int(node["tile_x"]) - int(mote["tile_x"])))
        edges.extend([[nearest["nav_id"], mote["nav_id"]], [mote["nav_id"], nearest["nav_id"]]])
    return {
        "stage_id": stage_id,
        "world_id": recipe.world,
        "node_id": node_id,
        "order": (world_index - 1) * 5 + stage_index,
        "name_key": f"stage.{recipe.world}.{stage_index:02d}.name",
        "intro_key": f"stage.{recipe.world}.{stage_index:02d}.intro",
        "target_time_ms": recipe.target_ms,
        "width_tiles": recipe.width,
        "height_tiles": 24,
        "tile_size": 32,
        "player_spawns": [[64.0 + offset * 30.0, 580.0] for offset in range(4)],
        "enemy_spawns": [
            {
                "spawn_id": f"enemy.{recipe.world}.{stage_index:02d}.{n + 1}",
                "kind": kind,
                "ability_id": ability,
                "tile_x": x,
                "tile_y": y,
                "patrol_left": max(1, x - 4),
                "patrol_right": min(recipe.width - 2, x + 4),
                "elite": elite,
            }
            for n, (kind, ability, x, y, elite) in enumerate(recipe.encounters)
        ],
        "motes": [
            {
                "mote_id": f"{stage_id}:mote:{number}",
                "tile_x": mote[0],
                "tile_y": mote[1],
                "route": mote[2],
            }
            for number, mote in zip(range(1, 4), recipe.motes, strict=True)
        ],
        "checkpoints": [
            {"checkpoint_id": checkpoint_ids[n], "tile_x": x, "tile_y": 19}
            for n, x in enumerate(recipe.checkpoints)
        ],
        "interactions": [
            {
                "interaction_id": f"interaction.{recipe.world}.{stage_index:02d}.{n + 1}",
                "kind": kind,
                "tile_x": x,
                "tile_y": y,
                "width_tiles": width,
                "height_tiles": height,
                "params": [],
            }
            for n, (kind, x, y, width, height) in enumerate(recipe.mechanics)
        ],
        "solids": solids,
        "one_way_tiles": one_way,
        "hazards": hazards,
        "navigation": {
            "start": "start",
            "goal": "goal",
            "nodes": main_nodes + mote_nodes,
            "edges": edges,
        },
        "goal_tile": [recipe.width - 4, 19],
        "boss_id": recipe.boss_id,
    }


def build_campaign() -> dict[str, object]:
    stages: list[dict[str, object]] = []
    worlds: list[dict[str, object]] = []
    previous_node: str | None = None
    for world_index, (world_id, _title, mechanics, palette_id, positions) in enumerate(WORLDS, 1):
        recipes = [recipe for recipe in STAGES if recipe.world == world_id]
        nodes: list[dict[str, object]] = []
        for stage_index, recipe in enumerate(recipes, 1):
            stage = stage_payload(recipe, world_index, stage_index)
            node_id = str(stage["node_id"])
            nodes.append({
                "node_id": node_id,
                "stage_id": stage["stage_id"],
                "position": list(positions[stage_index - 1]),
                "requires": [] if previous_node is None else [previous_node],
                "is_boss": recipe.boss_id is not None,
            })
            previous_node = node_id
            stages.append(stage)
        worlds.append({
            "world_id": world_id,
            "order": world_index,
            "name_key": f"world.{world_id}.name",
            "identity_key": f"world.{world_id}.identity",
            "mechanic_keys": [f"mechanic.{kind}.name" for kind in mechanics],
            "palette_id": palette_id,
            "nodes": nodes,
        })
    return {"version": "1.0", "worlds": worlds, "stages": stages}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_outputs() -> dict[Path, object]:
    return {
        Path("windsprig/content/campaign.json"): build_campaign(),
        Path("windsprig/content/rewards.json"): {
            "mote_thresholds": [
                {"threshold": n, "reward_id": reward, "kind": kind, "name_key": f"reward.{reward}.name"}
                for n, reward, kind in REWARDS
            ]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale: list[str] = []
    for path, payload in generated_outputs().items():
        canonical = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != canonical:
                stale.append(path.as_posix())
        else:
            write_json(path, payload)
    if stale:
        print("STALE: " + ", ".join(stale))
        return 1
    print("campaign: 6 worlds, 30 stages, 90 motes, 18 rewards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Generate, check, and test the complete campaign**

Run: `python tools/generate_campaign.py`

Expected: `campaign: 6 worlds, 30 stages, 90 motes, 18 rewards`.

Run: `python tools/generate_campaign.py --check && python -m pytest tests/integration/test_campaign_catalog.py -q`

Expected: generator exits 0 without rewriting files and pytest reports `2 passed`.

- [ ] **Step 6: Commit the authored campaign**

```powershell
git add tools/generate_campaign.py windsprig/content/campaign.json windsprig/content/rewards.json tests/integration/test_campaign_catalog.py
git commit -m "feat: author thirty-stage Windsprig campaign"
```

---

### Task 3: Six unique three-phase bosses and runtime boss snapshots

**Files:**
- Modify: `tools/generate_campaign.py`
- Create: `windsprig/content/bosses.json`
- Create: `windsprig/gameplay/bosses.py`
- Modify: `windsprig/gameplay/snapshot.py`
- Modify: `windsprig/gameplay/runtime.py`
- Create: `tests/unit/content/test_bosses.py`
- Create: `tests/integration/test_boss_catalog.py`

**Interfaces:**
- Consumes: `DeterministicRng`, `GameEvent`, `StageSpec.boss_id`, `StageRuntime`, and the locked gameplay DTOs.
- Produces: `BossState`, `BossCommand`, `BossStep`, `BossDirector`, `BossView`, `StageSnapshot.bosses`, and semantic events `BossAttackTelegraphed`, `BossPhaseChanged`, and `BossDefeated`.

- [ ] **Step 1: Write failing catalog and phase-transition tests**

```python
# tests/unit/content/test_bosses.py
from pathlib import Path

from windsprig.content.loader import load_catalog_bundle


def test_six_bosses_have_three_unique_phase_signatures() -> None:
    bosses = load_catalog_bundle(Path("windsprig/content")).bosses
    assert tuple(bosses) == (
        "rootjaw", "crucible_crab", "luma_eel",
        "volt_roc", "prism_warden", "the_stillness",
    )
    signatures = set()
    for boss in bosses.values():
        assert len(boss.phases) == 3
        assert [phase.enter_at_hp_ratio for phase in boss.phases] == [1.0, 0.66, 0.33]
        assert all(attack.telegraph_ms >= 600 for phase in boss.phases for attack in phase.attacks)
        signature = tuple(
            (phase.arena_rule, tuple(attack.attack_id for attack in phase.attacks))
            for phase in boss.phases
        )
        signatures.add(signature)
    assert len(signatures) == 6


def test_boss_stage_ids_map_one_to_one_to_bosses() -> None:
    bundle = load_catalog_bundle(Path("windsprig/content"))
    stage_bosses = [stage.boss_id for stage in bundle.campaign.stages.values() if stage.boss_id]
    assert stage_bosses == list(bundle.bosses)
```

```python
# tests/integration/test_boss_catalog.py
from windsprig.core.rng import DeterministicRng
from windsprig.gameplay.bosses import BossDirector
from tests.helpers.catalog import load_release_bosses


def test_rootjaw_changes_phase_once_and_telegraphs_before_attack() -> None:
    director = BossDirector(load_release_bosses())
    state = director.start("rootjaw", entity_id=41)
    first = director.step(state, hp=120, dt_ms=16, rng=DeterministicRng(7))
    assert first.events[0].topic == "BossAttackTelegraphed"
    assert first.events[0].payload["attack_id"] == "rootjaw.burrow_line"
    changed = director.step(first.state, hp=70, dt_ms=16, rng=DeterministicRng(7))
    assert [event.topic for event in changed.events] == ["BossPhaseChanged"]
    assert changed.state.phase_id == "rootjaw.tangled_fury"
```

- [ ] **Step 2: Run the boss tests and confirm missing content/runtime failures**

Run: `python -m pytest tests/unit/content/test_bosses.py tests/integration/test_boss_catalog.py -q`

Expected: collection fails because `windsprig.gameplay.bosses` and `bosses.json` do not exist.

- [ ] **Step 3: Add every boss phase and attack to the deterministic generator**

```python
# add to tools/generate_campaign.py
def attack(
    attack_id: str,
    telegraph_ms: int,
    active_ms: int,
    recovery_ms: int,
    marker: str,
    cue_id: str,
    **parameters: int | float | str | bool,
) -> dict[str, object]:
    return {
        "attack_id": attack_id,
        "telegraph_ms": telegraph_ms,
        "active_ms": active_ms,
        "recovery_ms": recovery_ms,
        "marker": marker,
        "cue_id": cue_id,
        "parameters": [[key, parameters[key]] for key in sorted(parameters)],
    }


def phase(
    phase_id: str,
    ratio: float,
    vulnerability: str,
    arena_rule: str,
    attacks: tuple[dict[str, object], dict[str, object]],
) -> dict[str, object]:
    return {
        "phase_id": phase_id,
        "enter_at_hp_ratio": ratio,
        "vulnerability": vulnerability,
        "arena_rule": arena_rule,
        "attacks": list(attacks),
    }


BOSSES = (
    {
        "boss_id": "rootjaw", "name_key": "boss.rootjaw.name", "max_hp": 120,
        "visual_id": "boss.rootjaw",
        "phases": [
            phase("rootjaw.buried_hunger", 1.0, "hidden", "burrow_tells",
                  (attack("rootjaw.burrow_line",900,500,700,"ground","sfx.boss.rootjaw",lanes=1,speed=180),
                   attack("rootjaw.seed_spit",700,650,800,"orbit","sfx.boss.rootjaw",projectiles=5,arc=70))),
            phase("rootjaw.tangled_fury", 0.66, "vulnerable", "root_cages",
                  (attack("rootjaw.root_cage",850,900,750,"arena","sfx.boss.rootjaw",columns=3,gap=2),
                   attack("rootjaw.bramble_sweep",650,700,850,"silhouette","sfx.boss.rootjaw",sweeps=2,width=96))),
            phase("rootjaw.heartwood_quake", 0.33, "armored", "alternating_burrows",
                  (attack("rootjaw.quake_bloom",1000,800,650,"ground","sfx.boss.rootjaw",rings=3,spacing=64),
                   attack("rootjaw.tunnel_feint",750,950,550,"lane","sfx.boss.rootjaw",feints=2,lanes=4))),
        ],
    },
    {
        "boss_id": "crucible_crab", "name_key": "boss.crucible_crab.name", "max_hp": 132,
        "visual_id": "boss.crucible_crab",
        "phases": [
            phase("crucible_crab.forged_shell",1.0,"armored","cooling_vents",
                  (attack("crucible_crab.claw_press",750,550,700,"ground","sfx.boss.crucible_crab",presses=2,width=80),
                   attack("crucible_crab.slag_cast",800,900,650,"lane","sfx.boss.crucible_crab",lanes=2,duration=1200))),
            phase("crucible_crab.molten_lanes",0.66,"vulnerable","moving_molten_lanes",
                  (attack("crucible_crab.lane_pour",950,1300,500,"lane","sfx.boss.crucible_crab",lanes=3,safe_lane=1),
                   attack("crucible_crab.shell_spin",650,850,750,"silhouette","sfx.boss.crucible_crab",bounces=3,speed=240))),
            phase("crucible_crab.overheat",0.33,"vulnerable","vent_cycle",
                  (attack("crucible_crab.vent_burst",700,900,550,"ground","sfx.boss.crucible_crab",vents=6,interval=140),
                   attack("crucible_crab.forge_drop",1050,600,600,"ground","sfx.boss.crucible_crab",drops=4,radius=44))),
        ],
    },
    {
        "boss_id": "luma_eel", "name_key": "boss.luma_eel.name", "max_hp": 126,
        "visual_id": "boss.luma_eel",
        "phases": [
            phase("luma_eel.moonlit_current",1.0,"vulnerable","clockwise_current",
                  (attack("luma_eel.current_dash",800,650,700,"silhouette","sfx.boss.luma_eel",passes=2,speed=260),
                   attack("luma_eel.lumen_orbs",700,1000,650,"orbit","sfx.boss.luma_eel",orbs=6,turn_rate=40))),
            phase("luma_eel.decoy_tide",0.66,"hidden","light_decoys",
                  (attack("luma_eel.decoy_flash",900,750,650,"arena","sfx.boss.luma_eel",decoys=3,true_index_cycle=3),
                   attack("luma_eel.reverse_current",750,1200,550,"lane","sfx.boss.luma_eel",direction=-1,strength=190))),
            phase("luma_eel.eclipse_spiral",0.33,"vulnerable","alternating_currents",
                  (attack("luma_eel.eclipse_ring",1000,1000,500,"orbit","sfx.boss.luma_eel",rings=2,gaps=2),
                   attack("luma_eel.spiral_dive",700,1100,500,"silhouette","sfx.boss.luma_eel",dives=3,curve=0.7))),
        ],
    },
    {
        "boss_id": "volt_roc", "name_key": "boss.volt_roc.name", "max_hp": 138,
        "visual_id": "boss.volt_roc",
        "phases": [
            phase("volt_roc.storm_perch",1.0,"vulnerable","charged_perches",
                  (attack("volt_roc.dive_lane",850,600,650,"lane","sfx.boss.volt_roc",dives=2,speed=320),
                   attack("volt_roc.feather_bolts",650,900,750,"orbit","sfx.boss.volt_roc",bolts=7,spread=100))),
            phase("volt_roc.chain_sky",0.66,"vulnerable","linked_conductors",
                  (attack("volt_roc.lightning_chain",950,800,600,"ground","sfx.boss.volt_roc",nodes=4,jumps=3),
                   attack("volt_roc.rail_talon",700,1000,550,"silhouette","sfx.boss.volt_roc",rails=2,passes=2))),
            phase("volt_roc.tempest_dive",0.33,"invulnerable","eye_of_storm_windows",
                  (attack("volt_roc.tempest_wall",1050,1100,500,"arena","sfx.boss.volt_roc",walls=2,gap=96),
                   attack("volt_roc.thunder_dive",750,1200,450,"ground","sfx.boss.volt_roc",dives=4,shock_radius=72))),
        ],
    },
    {
        "boss_id": "prism_warden", "name_key": "boss.prism_warden.name", "max_hp": 144,
        "visual_id": "boss.prism_warden",
        "phases": [
            phase("prism_warden.reflection",1.0,"armored","mirror_weak_side",
                  (attack("prism_warden.prism_beam",900,900,650,"beam","sfx.boss.prism_warden",bounces=2,width=24),
                   attack("prism_warden.mirror_guard",650,700,800,"silhouette","sfx.boss.prism_warden",reflect_ms=700,weak_side="rear"))),
            phase("prism_warden.clone_garden",0.66,"hidden","three_clones",
                  (attack("prism_warden.clone_cast",850,1000,600,"arena","sfx.boss.prism_warden",clones=3,real_glint_ms=180),
                   attack("prism_warden.color_cross",750,900,650,"beam","sfx.boss.prism_warden",beams=4,rotation=45))),
            phase("prism_warden.gravity_refraction",0.33,"vulnerable","gravity_flip_beams",
                  (attack("prism_warden.gravity_shard",1000,1100,500,"ground","sfx.boss.prism_warden",shards=8,gravity=-1),
                   attack("prism_warden.refraction_bloom",800,1200,450,"orbit","sfx.boss.prism_warden",petals=10,gaps=2))),
        ],
    },
    {
        "boss_id": "the_stillness", "name_key": "boss.the_stillness.name", "max_hp": 180,
        "visual_id": "boss.the_stillness",
        "phases": [
            phase("the_stillness.silenced_motion",1.0,"vulnerable","moving_silence_fields",
                  (attack("the_stillness.hush_wave",900,1000,600,"arena","sfx.boss.the_stillness",fields=2,speed=90),
                   attack("the_stillness.locked_echo",750,850,700,"silhouette","sfx.boss.the_stillness",lock_ms=1200,orbs=4))),
            phase("the_stillness.stolen_systems",0.66,"armored","learned_world_remix",
                  (attack("the_stillness.system_chain",1050,1300,500,"arena","sfx.boss.the_stillness",systems="gust,vent,current,rail",interval=260),
                   attack("the_stillness.prism_lock",800,1000,550,"beam","sfx.boss.the_stillness",beams=3,lock_zones=2))),
            phase("the_stillness.motion_returns",0.33,"vulnerable","ability_rotation",
                  (attack("the_stillness.echo_crown",1100,1400,400,"orbit","sfx.boss.the_stillness",rings=3,ability_windows=6),
                   attack("the_stillness.final_release",900,1500,350,"arena","sfx.boss.the_stillness",waves=5,safe_arc=50))),
        ],
    },
)
```

Extend `generated_outputs()` with `Path("windsprig/content/bosses.json"): {"bosses": list(BOSSES)}` and change the success line to `campaign: 6 worlds, 30 stages, 6 bosses, 90 motes, 18 rewards`.

- [ ] **Step 4: Implement the boss director and immutable presentation DTO**

```python
# windsprig/gameplay/bosses.py
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from windsprig.content.models import BossAttackSpec, BossSpec
from windsprig.core.events import GameEvent
from windsprig.core.rng import DeterministicRng


@dataclass(frozen=True, slots=True)
class BossState:
    boss_id: str
    entity_id: int
    phase_index: int
    phase_id: str
    attack_index: int
    mode: str
    remaining_ms: int
    active_attack_id: str | None
    defeated: bool = False


@dataclass(frozen=True, slots=True)
class BossCommand:
    command: str
    attack_id: str
    parameters: tuple[tuple[str, int | float | str | bool], ...]


@dataclass(frozen=True, slots=True)
class BossStep:
    state: BossState
    commands: tuple[BossCommand, ...]
    events: tuple[GameEvent, ...]


class BossDirector:
    def __init__(self, specs: Mapping[str, BossSpec]) -> None:
        self.specs = specs

    def start(self, boss_id: str, entity_id: int) -> BossState:
        spec = self.specs[boss_id]
        return BossState(boss_id, entity_id, 0, spec.phases[0].phase_id, 0, "ready", 0, None)

    def step(self, state: BossState, hp: int, dt_ms: int, rng: DeterministicRng) -> BossStep:
        spec = self.specs[state.boss_id]
        if hp <= 0 and not state.defeated:
            ended = replace(state, mode="defeated", remaining_ms=0, active_attack_id=None, defeated=True)
            return BossStep(ended, (), (GameEvent("BossDefeated", {"boss_id": state.boss_id}),))
        ratio = max(0.0, hp / spec.max_hp)
        desired = max(index for index, phase in enumerate(spec.phases) if ratio <= phase.enter_at_hp_ratio)
        if desired != state.phase_index:
            phase_state = replace(
                state, phase_index=desired, phase_id=spec.phases[desired].phase_id,
                attack_index=0, mode="ready", remaining_ms=0, active_attack_id=None,
            )
            event = GameEvent("BossPhaseChanged", {
                "boss_id": state.boss_id, "phase_id": phase_state.phase_id, "phase_index": desired + 1,
            })
            return BossStep(phase_state, (), (event,))
        remaining = max(0, state.remaining_ms - dt_ms)
        phase = spec.phases[state.phase_index]
        if state.mode != "ready" and remaining > 0:
            return BossStep(replace(state, remaining_ms=remaining), (), ())
        attack_spec: BossAttackSpec = phase.attacks[state.attack_index % len(phase.attacks)]
        if state.mode in {"ready", "recovery"}:
            telegraph = replace(
                state, mode="telegraph", remaining_ms=attack_spec.telegraph_ms,
                active_attack_id=attack_spec.attack_id,
            )
            event = GameEvent("BossAttackTelegraphed", {
                "boss_id": state.boss_id, "phase_id": state.phase_id,
                "attack_id": attack_spec.attack_id, "marker": attack_spec.marker,
                "telegraph_ms": attack_spec.telegraph_ms, "cue_id": attack_spec.cue_id,
            })
            return BossStep(telegraph, (), (event,))
        if state.mode == "telegraph":
            command = BossCommand("execute", attack_spec.attack_id, attack_spec.parameters)
            active = replace(state, mode="active", remaining_ms=attack_spec.active_ms)
            return BossStep(active, (command,), ())
        next_index = (state.attack_index + 1) % len(phase.attacks)
        recovery = replace(
            state, mode="recovery", remaining_ms=attack_spec.recovery_ms,
            attack_index=next_index, active_attack_id=None,
        )
        rng.next_u32()
        return BossStep(recovery, (), ())
```

Add `BossView` with the exact fields in “Interfaces Produced by This Plan.” Append `bosses: tuple[BossView, ...] = ()` to `StageSnapshot`, exclude boss entities from `enemies`, and have `StageRuntime` create a director only when `stage.boss_id` is non-null. The runtime publishes the three boss topics returned by `BossDirector`, applies `BossCommand` through the gameplay-owned interaction/attack factory, and snapshots telegraph marker and vulnerability without exposing `BossState` to render code.

- [ ] **Step 5: Generate boss content and run tests**

Run: `python tools/generate_campaign.py && python tools/generate_campaign.py --check`

Expected: both commands print `campaign: 6 worlds, 30 stages, 6 bosses, 90 motes, 18 rewards` and exit 0.

Run: `python -m pytest tests/unit/content/test_bosses.py tests/integration/test_boss_catalog.py -q`

Expected: `4 passed`.

- [ ] **Step 6: Commit all six boss implementations**

```powershell
git add tools/generate_campaign.py windsprig/content/bosses.json windsprig/gameplay/bosses.py windsprig/gameplay/snapshot.py windsprig/gameplay/runtime.py tests/unit/content/test_bosses.py tests/integration/test_boss_catalog.py
git commit -m "feat: add six multi-phase Windsprig bosses"
```

---

### Task 4: Idempotent progression, completion math, and frozen profile/map/results view models

**Files:**
- Rewrite: `windsprig/meta/completion.py`
- Rewrite: `windsprig/meta/world_map.py`
- Create: `windsprig/meta/presentation_models.py`
- Create: `tests/unit/meta/test_completion.py`
- Create: `tests/unit/meta/test_world_map_views.py`
- Create: `tests/unit/meta/test_presentation_models.py`
- Create: `tests/integration/test_progression_flow.py`

**Interfaces:**
- Consumes: foundation `SaveProfile`/`SaveData`/`GlobalSettings`, gameplay `StageResult`, `CatalogBundle`, and `Localizer.text()`.
- Produces: `CompletionDelta`, `CompletionBreakdown`, `completion_percent()`, `apply_stage_result()`, `NodeState`, `WorldMapViewModel`, `ProfileCardVM`, `ResultsViewModel`, and their exact builders.

- [ ] **Step 1: Write failing idempotence and completion-formula tests**

```python
# tests/unit/meta/test_completion.py
from dataclasses import replace
from decimal import Decimal

import pytest

from windsprig.gameplay.snapshot import StageResult
from windsprig.meta.completion import apply_stage_result, completion_percent
from tests.helpers.catalog import empty_profile, release_bundle


def result(*motes: str, time_ms: int = 90000) -> StageResult:
    return StageResult(
        stage_id="world_1_stage_1",
        world_id="world_1",
        node_id="world_1_node_1",
        clear_time_ms=time_ms,
        collected_mote_ids=tuple(motes),
        discovered_ability_ids=("galehook",),
        active_slots=(1,),
        deaths_by_slot=((1, 0),),
    )


def test_replay_improves_time_without_inflating_motes() -> None:
    bundle = release_bundle()
    profile = empty_profile()
    first, first_delta = apply_stage_result(
        profile, result("world_1_stage_1:mote:1", "world_1_stage_1:mote:2"), bundle
    )
    replay, replay_delta = apply_stage_result(
        first, result("world_1_stage_1:mote:2", "world_1_stage_1:mote:3", time_ms=80000), bundle
    )
    assert replay.collected_mote_ids == frozenset({
        "world_1_stage_1:mote:1", "world_1_stage_1:mote:2", "world_1_stage_1:mote:3",
    })
    assert replay.best_times_ms["world_1_stage_1"] == 80000
    assert replay.clear_counts["world_1_stage_1"] == 2
    assert first_delta.new_mote_ids == ("world_1_stage_1:mote:1", "world_1_stage_1:mote:2")
    assert replay_delta.new_mote_ids == ("world_1_stage_1:mote:3",)


def test_unknown_stage_mote_is_rejected() -> None:
    with pytest.raises(ValueError, match="world_2_stage_1:mote:1 is not in world_1_stage_1"):
        apply_stage_result(empty_profile(), result("world_2_stage_1:mote:1"), release_bundle())


def test_documented_completion_weighting() -> None:
    profile = replace(
        empty_profile(),
        clear_counts={f"stage-{n}": 1 for n in range(15)},
        collected_mote_ids=frozenset(f"mote-{n}" for n in range(45)),
        challenge_rewards=frozenset({"challenge.sunleaf", "challenge.emberglass", "challenge.tidemoon"}),
    )
    assert completion_percent(profile, release_bundle(), cleared_bosses=3) == Decimal("50.0")
```

- [ ] **Step 2: Run the focused progression tests and confirm they fail**

Run: `python -m pytest tests/unit/meta/test_completion.py -q`

Expected: collection fails because `apply_stage_result` and the documented completion calculation are absent.

- [ ] **Step 3: Implement immutable result application and the formula**

```python
# windsprig/meta/completion.py
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP

from windsprig.content.models import CatalogBundle
from windsprig.gameplay.snapshot import StageResult
from windsprig.meta.save_models import SaveProfile


@dataclass(frozen=True, slots=True)
class CompletionDelta:
    first_clear: bool
    new_mote_ids: tuple[str, ...]
    newly_discovered_abilities: tuple[str, ...]
    newly_unlocked_node_ids: tuple[str, ...]
    newly_unlocked_world_ids: tuple[str, ...]
    new_reward_ids: tuple[str, ...]
    previous_best_ms: int | None
    is_new_best: bool


@dataclass(frozen=True, slots=True)
class CompletionBreakdown:
    cleared_stages: int
    total_stages: int
    collected_motes: int
    total_motes: int
    cleared_bosses: int
    total_bosses: int
    challenge_rewards: int
    total_challenges: int
    percent: Decimal


def completion_percent(
    profile: SaveProfile,
    catalog: CatalogBundle,
    *,
    cleared_bosses: int | None = None,
) -> Decimal:
    stages = tuple(catalog.campaign.stages.values())
    cleared_ids = {stage_id for stage_id, count in profile.clear_counts.items() if count > 0}
    boss_ids = {stage.stage_id for stage in stages if stage.boss_id is not None}
    boss_count = len(cleared_ids & boss_ids) if cleared_bosses is None else cleared_bosses
    challenges = {reward.reward_id for reward in catalog.rewards.mote_thresholds if reward.kind == "challenge"}
    score = (
        Decimal("0.50") * Decimal(len(cleared_ids)) / Decimal(30)
        + Decimal("0.30") * Decimal(len(profile.collected_mote_ids)) / Decimal(90)
        + Decimal("0.10") * Decimal(boss_count) / Decimal(6)
        + Decimal("0.10") * Decimal(len(profile.challenge_rewards & challenges)) / Decimal(len(challenges))
    ) * Decimal(100)
    return min(Decimal("100.0"), score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def apply_stage_result(
    profile: SaveProfile,
    result: StageResult,
    catalog: CatalogBundle,
) -> tuple[SaveProfile, CompletionDelta]:
    stage = catalog.campaign.stages[result.stage_id]
    if stage.node_id != result.node_id or stage.world_id != result.world_id:
        raise ValueError("stage result identity does not match catalog")
    allowed_motes = {mote.mote_id for mote in stage.motes}
    for mote_id in result.collected_mote_ids:
        if mote_id not in allowed_motes:
            raise ValueError(f"{mote_id} is not in {result.stage_id}")
    previous_best = profile.best_times_ms.get(result.stage_id)
    counts = dict(profile.clear_counts)
    first_clear = counts.get(result.stage_id, 0) == 0
    counts[result.stage_id] = counts.get(result.stage_id, 0) + 1
    best_times = dict(profile.best_times_ms)
    best_times[result.stage_id] = min(result.clear_time_ms, previous_best or result.clear_time_ms)
    new_motes = tuple(sorted(set(result.collected_mote_ids) - profile.collected_mote_ids))
    all_motes = profile.collected_mote_ids | frozenset(result.collected_mote_ids)
    new_abilities = tuple(sorted(set(result.discovered_ability_ids) - profile.discovered_abilities))
    ordered_nodes = [node for world in catalog.campaign.worlds for node in world.nodes]
    node_index = next(index for index, node in enumerate(ordered_nodes) if node.node_id == result.node_id)
    unlocked_nodes = set(profile.unlocked_nodes) | {result.node_id}
    new_nodes: set[str] = set()
    new_worlds: set[str] = set()
    if node_index + 1 < len(ordered_nodes):
        next_node = ordered_nodes[node_index + 1]
        if next_node.node_id not in unlocked_nodes:
            unlocked_nodes.add(next_node.node_id)
            new_nodes.add(next_node.node_id)
        if next_node.world_id not in profile.unlocked_worlds:
            new_worlds.add(next_node.world_id)
    unlocked_worlds = profile.unlocked_worlds | frozenset(new_worlds) | {stage.world_id}
    earned = {
        reward.reward_id
        for reward in catalog.rewards.mote_thresholds
        if len(all_motes) >= reward.threshold
    }
    new_rewards = tuple(sorted(earned - profile.challenge_rewards))
    updated = replace(
        profile,
        unlocked_nodes=frozenset(unlocked_nodes),
        unlocked_worlds=frozenset(unlocked_worlds),
        collected_mote_ids=all_motes,
        best_times_ms=best_times,
        clear_counts=counts,
        discovered_abilities=profile.discovered_abilities | frozenset(result.discovered_ability_ids),
        challenge_rewards=profile.challenge_rewards | frozenset(earned),
        last_played_stage=result.stage_id,
    )
    delta = CompletionDelta(
        first_clear=first_clear,
        new_mote_ids=new_motes,
        newly_discovered_abilities=new_abilities,
        newly_unlocked_node_ids=tuple(sorted(new_nodes)),
        newly_unlocked_world_ids=tuple(sorted(new_worlds)),
        new_reward_ids=new_rewards,
        previous_best_ms=previous_best,
        is_new_best=previous_best is None or result.clear_time_ms < previous_best,
    )
    return updated, delta
```

The formula is normative: cleared stages contribute 50%, unique motes 30%, cleared bosses 10%, and the six optional challenge rewards 10%. Values are clamped to 100.0 and rounded half-up to one decimal place.

- [ ] **Step 4: Write failing profile, world-map, and results VM tests**

```python
# tests/unit/meta/test_world_map_views.py
from windsprig.meta.world_map import NodeState, build_world_map_view
from tests.helpers.catalog import FakeLocalizer, empty_profile, release_bundle


def test_map_exposes_shape_icon_text_and_locked_connectors() -> None:
    vm = build_world_map_view(
        empty_profile(), release_bundle(), "world_1_node_1", FakeLocalizer()
    )
    first, second = vm.worlds[0].nodes[:2]
    assert (first.state, first.shape_token, first.icon_token, first.selected) == (
        NodeState.AVAILABLE, "node.round", "stage.leaf", True
    )
    assert second.state is NodeState.LOCKED
    assert vm.worlds[0].connectors[0].unlocked is False


# tests/unit/meta/test_presentation_models.py
from windsprig.meta.presentation_models import build_profile_cards, build_results_view
from tests.helpers.catalog import FakeLocalizer, release_bundle, save_with_empty_profiles


def test_profile_cards_show_required_summary_fields() -> None:
    cards = build_profile_cards(save_with_empty_profiles(), release_bundle(), FakeLocalizer())
    assert len(cards) == 3
    assert cards[0].completion_label == "0.0%"
    assert cards[0].mote_label == "0 / 90"
    assert cards[0].play_time_label == "00:00:00"
    assert cards[0].last_stage_label == "No stage played"
```

- [ ] **Step 5: Implement the exact view-model types and builders**

```python
# windsprig/meta/world_map.py
from dataclasses import dataclass, replace
from enum import StrEnum


class NodeState(StrEnum):
    LOCKED = "locked"
    AVAILABLE = "available"
    CLEARED = "cleared"


@dataclass(frozen=True, slots=True)
class MapNodeVM:
    node_id: str
    stage_id: str
    label: str
    x: int
    y: int
    state: NodeState
    shape_token: str
    icon_token: str
    mote_states: tuple[bool, bool, bool]
    best_time_label: str
    selected: bool
    is_boss: bool


@dataclass(frozen=True, slots=True)
class ConnectorVM:
    from_node_id: str
    to_node_id: str
    unlocked: bool


@dataclass(frozen=True, slots=True)
class MapWorldVM:
    world_id: str
    label: str
    identity: str
    palette_id: str
    locked: bool
    nodes: tuple[MapNodeVM, ...]
    connectors: tuple[ConnectorVM, ...]


@dataclass(frozen=True, slots=True)
class WorldMapViewModel:
    worlds: tuple[MapWorldVM, ...]
    total_motes_label: str
    completion_label: str
    selected_node_id: str
    save_status_key: str
```

```python
# windsprig/meta/presentation_models.py
@dataclass(frozen=True, slots=True)
class ProfileCardVM:
    slot_index: int
    profile_id: str
    display_name: str
    completion_label: str
    mote_label: str
    last_stage_label: str
    play_time_label: str
    is_empty: bool


@dataclass(frozen=True, slots=True)
class ResultMoteVM:
    mote_id: str
    collected_before: bool
    collected_this_run: bool


@dataclass(frozen=True, slots=True)
class UnlockVM:
    reward_id: str
    label: str
    kind: str


@dataclass(frozen=True, slots=True)
class ResultsViewModel:
    stage_name: str
    clear_time_label: str
    best_time_label: str
    comparison_label: str
    new_best: bool
    motes: tuple[ResultMoteVM, ResultMoteVM, ResultMoteVM]
    ability_labels: tuple[str, ...]
    unlocks: tuple[UnlockVM, ...]
    completion_label: str
    can_next_stage: bool
    next_stage_id: str | None
```

`build_world_map_view()` derives node state from `unlocked_nodes` and `clear_counts`, derives each three-icon mote tuple from the stage mote IDs, uses `node.hex-boss`/`boss.crown` for boss nodes and `node.round`/`stage.leaf` for normal nodes, and marks connectors unlocked only when both endpoints are unlocked. `build_results_view()` compares the incoming time with `CompletionDelta.previous_best_ms`, localizes every ability/reward/stage name, and enables Next Stage only when a following node exists and was unlocked by the result.

- [ ] **Step 6: Run unit and full progression-flow tests**

Run: `python -m pytest tests/unit/meta tests/integration/test_progression_flow.py -q`

Expected: `12 passed`.

- [ ] **Step 7: Commit progression and view models**

```powershell
git add windsprig/meta/completion.py windsprig/meta/world_map.py windsprig/meta/presentation_models.py tests/unit/meta tests/integration/test_progression_flow.py
git commit -m "feat: add idempotent campaign progression views"
```

---

### Task 5: Complete English/Korean locale catalogs and licensed Korean font

**Files:**
- Create: `tools/generate_locales.py`
- Create: `tools/fetch_font.py`
- Create: `windsprig/content/strings.en.json`
- Create: `windsprig/content/strings.ko.json`
- Create: `windsprig/localization.py`
- Create: `assets/fonts/NotoSansKR[wght].ttf`
- Create: `assets/fonts/OFL-NotoSansKR.txt`
- Rewrite: `assets/LICENSES.md`
- Create: `tests/unit/content/test_localization.py`

**Interfaces:**
- Consumes: content name/intro/reward keys, `GlobalSettings.language`, and pygame font loading.
- Produces: key-identical `en`/`ko` JSON, strict `LocaleCatalog`, `Localizer.load()`, `Localizer.text()`, and a pinned, hash-verified Noto Sans KR font/license pair.

- [ ] **Step 1: Write failing locale parity, formatting, and Hangul-glyph tests**

```python
# tests/unit/content/test_localization.py
from pathlib import Path
import string

import pygame

from windsprig.localization import Localizer, load_locale_catalog


def fields(value: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(value) if name}


def test_locales_have_identical_keys_and_placeholders() -> None:
    catalog = load_locale_catalog(Path("windsprig/content"))
    assert set(catalog.strings["en"]) == set(catalog.strings["ko"])
    assert len(catalog.strings["en"]) >= 180
    for key in catalog.strings["en"]:
        assert fields(catalog.strings["en"][key]) == fields(catalog.strings["ko"][key])


def test_localizer_formats_and_falls_back_to_english() -> None:
    ko = Localizer.load(Path("windsprig/content"), "ko")
    assert ko.text("results.time", time="01:23.456") == "기록 01:23.456"
    assert ko.text("debug.english_only") == "English diagnostic"


def test_bundled_font_renders_release_korean_sample() -> None:
    pygame.font.init()
    font = pygame.font.Font("assets/fonts/NotoSansKR[wght].ttf", 28)
    sample = "바람싹 메아리 수집 완료 설정 접근성"
    assert all(metric is not None for metric in font.metrics(sample))
    assert font.render(sample, True, "white").get_bounding_rect().width > 200
```

- [ ] **Step 2: Run the locale tests and confirm missing files fail**

Run: `SDL_VIDEODRIVER=dummy python -m pytest tests/unit/content/test_localization.py -q`

Expected: collection or setup fails because `windsprig.localization`, locale JSON, and the bundled font do not exist.

- [ ] **Step 3: Encode every stage title and intro in both languages**

```python
# tools/generate_locales.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

STAGE_COPY = (
    ("world_1",1,"First Flight","첫 비행","Ride gentle gusts over the waking meadow.","깨어나는 들판의 잔잔한 돌풍을 타세요."),
    ("world_1",2,"Millstream Run","물레바람 질주","Cross turning mills and open a bramble shortcut.","회전하는 풍차를 건너 덩굴 지름길을 여세요."),
    ("world_1",3,"Bramble Updraft","가시덤불 상승풍","Break thorn gates while chaining rising gusts.","상승풍을 이어 타며 가시 문을 부수세요."),
    ("world_1",4,"Valewind Gauntlet","계곡바람 시련","Master gust timing across the high vale.","높은 계곡에서 돌풍 타이밍을 완성하세요."),
    ("world_1",5,"Rootjaw Burrow","뿌리턱 굴","Follow the trembling roots to Rootjaw's den.","떨리는 뿌리를 따라 뿌리턱의 굴로 가세요."),
    ("world_2",1,"Kilnwalk","가마길","Learn the rhythm of conveyors and cooling vents.","컨베이어와 냉각 통풍구의 리듬을 익히세요."),
    ("world_2",2,"Conveyor Crossing","컨베이어 교차로","Change lanes before the furnace gaps open.","용광로 틈이 열리기 전에 선로를 바꾸세요."),
    ("world_2",3,"Shutter Furnace","차단문 용광로","Read timed shutters through waves of heat.","열기 파동 사이에서 차단문 시간을 읽으세요."),
    ("world_2",4,"Molten Clockwork","용융 태엽장치","Chain every factory mechanism without stopping.","멈추지 말고 모든 공장 장치를 이어 가세요."),
    ("world_2",5,"Crucible Crab","도가니 게","Cool the armored keeper of the molten lanes.","용융 선로의 갑옷 수호자를 식히세요."),
    ("world_3",1,"Pod Pools","부유열매 웅덩이","Use buoyant pods to cross the moonlit pools.","부유열매로 달빛 웅덩이를 건너세요."),
    ("world_3",2,"Current Choir","해류 합창","Let aligned currents carry each echo onward.","정렬된 해류에 메아리를 실어 보내세요."),
    ("world_3",3,"Waterfall Vault","폭포 금고","Climb behind falling water to find the upper route.","떨어지는 물 뒤로 올라가 위쪽 길을 찾으세요."),
    ("world_3",4,"Mooncurrent Maze","달해류 미로","Reverse currents and navigate the deepest grotto.","해류를 뒤집어 가장 깊은 동굴을 통과하세요."),
    ("world_3",5,"Luma Eel","루마 장어","Track the true light through Luma Eel's decoys.","루마 장어의 미끼 빛 사이에서 진짜 빛을 찾으세요."),
    ("world_4",1,"Live Line","활선","Ride the first rail and ground its charge safely.","첫 전기 레일을 타고 안전하게 접지하세요."),
    ("world_4",2,"Conductor Crossing","도체 교차로","Link conductors to open a path through the storm.","도체를 연결해 폭풍 속 길을 여세요."),
    ("world_4",3,"Turntable Tempest","회전탑 폭풍","Transfer between rotating towers at full speed.","최고 속도로 회전탑 사이를 갈아타세요."),
    ("world_4",4,"Observatory Ascent","관측소 등반","Master rails, conductors, and tower rotation.","레일과 도체와 회전탑을 모두 정복하세요."),
    ("world_4",5,"Volt Roc","볼트 로크","Ground the sky hunter before its chain lightning lands.","연쇄 번개가 닿기 전에 하늘 사냥꾼을 접지하세요."),
    ("world_5",1,"Mirror Seed","거울씨앗","Turn one beam with a living mirror.","살아 있는 거울로 한 줄기 빛을 돌리세요."),
    ("world_5",2,"Chromatic Canopy","색채 수관","Match beam colors across the crystal canopy.","수정 수관에서 빛줄기 색을 맞추세요."),
    ("world_5",3,"Gravity Petal","중력 꽃잎","Bloom new gravity paths through the garden.","정원에 새로운 중력 길을 피우세요."),
    ("world_5",4,"Refraction Labyrinth","굴절 미궁","Reflect, recolor, and invert the longest route.","가장 긴 길을 반사하고 채색하고 뒤집으세요."),
    ("world_5",5,"Prism Warden","프리즘 수호자","Find the real Warden among mirrored clones.","거울 분신 사이에서 진짜 수호자를 찾으세요."),
    ("world_6",1,"Hushed Court","고요한 뜰","Carry motion through the first silence field.","첫 침묵장을 지나 움직임을 이어 가세요."),
    ("world_6",2,"Shattered Orbit","부서진 궤도","Remix gravity, rails, and silence in open sky.","열린 하늘에서 중력과 레일과 침묵을 엮으세요."),
    ("world_6",3,"Locked Echoes","잠긴 메아리","Recover each ability after the crown locks it away.","왕관이 잠근 능력을 하나씩 되찾으세요."),
    ("world_6",4,"Crown of Motion","움직임의 왕관","Prove mastery of all six islands in one ascent.","한 번의 등반으로 여섯 섬의 숙련을 증명하세요."),
    ("world_6",5,"The Stillness","정지","Release every learned motion against the final silence.","배운 모든 움직임을 마지막 침묵에 풀어놓으세요."),
)
```

- [ ] **Step 4: Add the complete shared copy table and deterministic locale writer**

```python
# append to tools/generate_locales.py
ROWS = {
    "game.title": ("Windsprig: Echoes of the Gale","바람싹: 질풍의 메아리"),
    "action.start": ("Start","시작"), "action.continue": ("Continue","계속"),
    "action.back": ("Back","뒤로"), "action.confirm": ("Confirm","확인"),
    "action.cancel": ("Cancel","취소"), "action.next_stage": ("Next Stage","다음 스테이지"),
    "action.replay": ("Replay","다시 하기"), "action.world_map": ("World Map","월드맵"),
    "action.retry_checkpoint": ("Retry Checkpoint","체크포인트 재도전"),
    "action.retry_stage": ("Retry Stage","스테이지 재도전"),
    "action.create_profile": ("Create Profile","프로필 만들기"),
    "action.delete_profile": ("Hold to Delete","길게 눌러 삭제"),
    "screen.profile.title": ("Choose a Profile","프로필 선택"),
    "screen.map.title": ("Sky Island Map","하늘섬 지도"),
    "screen.results.title": ("Stage Clear","스테이지 완료"),
    "screen.settings.title": ("Settings","설정"),
    "screen.controls.title": ("Controls & Accessibility","조작 및 접근성"),
    "screen.credits.title": ("Credits","제작진"),
    "screen.pause.title": ("Paused","일시 정지"),
    "screen.defeat.title": ("The wind rests","바람이 잠시 쉽니다"),
    "profile.empty": ("New profile","새 프로필"), "profile.completion": ("Completion {percent}%","달성도 {percent}%"),
    "profile.motes": ("Wind Motes {found} / 90","바람 티끌 {found} / 90"),
    "profile.play_time": ("Play time {time}","플레이 시간 {time}"),
    "profile.no_stage": ("No stage played","플레이 기록 없음"),
    "map.locked": ("Locked","잠김"), "map.available": ("Available","입장 가능"),
    "map.cleared": ("Cleared","완료"), "map.best": ("Best {time}","최고 {time}"),
    "results.time": ("Time {time}","기록 {time}"), "results.best": ("Best {time}","최고 {time}"),
    "results.new_best": ("New best! {delta} faster","신기록! {delta} 단축"),
    "results.first_clear": ("First clear","첫 완료"), "results.motes": ("Wind Motes","바람 티끌"),
    "results.abilities": ("Echoes discovered","발견한 메아리"), "results.unlocks": ("Unlocked","해금"),
    "save.saved": ("Saved","저장됨"), "save.saving": ("Saving","저장 중"),
    "save.failed": ("Save failed — retry","저장 실패 — 다시 시도"),
    "audio.muted_failure": ("Audio unavailable — muted","오디오를 사용할 수 없어 음소거됨"),
    "settings.master": ("Master volume","전체 음량"), "settings.music": ("Music volume","음악 음량"),
    "settings.sfx": ("SFX volume","효과음 음량"), "settings.mute": ("Mute","음소거"),
    "settings.fullscreen": ("Fullscreen","전체 화면"), "settings.integer_scale": ("Integer scaling","정수 배율"),
    "settings.shake": ("Screen shake","화면 흔들림"), "settings.reduced_motion": ("Reduced motion","동작 줄이기"),
    "settings.draw_toggle": ("Draw action: toggle","끌어당기기: 전환"),
    "settings.draw_hold": ("Draw action: hold","끌어당기기: 누르기"),
    "settings.guard_toggle": ("Guard: toggle","가드: 전환"), "settings.guard_hold": ("Guard: hold","가드: 누르기"),
    "settings.language": ("Language","언어"), "settings.english": ("English","영어"),
    "settings.korean": ("Korean","한국어"), "settings.controls": ("Control reference","조작 안내"),
    "settings.keyboard_p1": ("Keyboard layout 1","키보드 배치 1"),
    "settings.keyboard_p2": ("Keyboard layout 2","키보드 배치 2"),
    "settings.gamepad": ("Gamepad mapping guide","게임패드 배치 안내"),
    "hud.hp": ("HP {current}/{maximum}","체력 {current}/{maximum}"),
    "hud.lives": ("Lives {count}","목숨 {count}"), "hud.motes": ("Motes {found}/3","티끌 {found}/3"),
    "hud.hover": ("Hover","활공"), "hud.captured": ("Held echo: {ability}","보유 메아리: {ability}"),
    "hud.none": ("None","없음"), "hud.gather": ("Gather {seconds}","집결 {seconds}"),
    "status.invulnerable": ("Invulnerable","무적"), "status.guard": ("Guard","가드"),
    "status.dodge_ready": ("Dodge ready","회피 준비"), "status.boss_phase": ("Phase {phase}/3","단계 {phase}/3"),
    "ability.bloomblade.name": ("Bloomblade","꽃날"), "ability.cinder.name": ("Cinder","불씨"),
    "ability.voltsong.name": ("Voltsong","전율노래"), "ability.galehook.name": ("Galehook","질풍갈고리"),
    "ability.stoneheart.name": ("Stoneheart","돌심장"), "ability.tempest.name": ("Tempest","대폭풍"),
    "world.sunleaf.name": ("Sunleaf Vale","햇잎 골짜기"), "world.sunleaf.identity": ("Warm meadows and windmills","따뜻한 초원과 풍차"),
    "world.emberglass.name": ("Emberglass Works","잿불유리 공방"), "world.emberglass.identity": ("A glowing kiln city","빛나는 가마 도시"),
    "world.tidemoon.name": ("Tidemoon Grotto","밀물달 동굴"), "world.tidemoon.identity": ("Moonlit water caverns","달빛 물동굴"),
    "world.thunderrail.name": ("Thunderrail Heights","천둥레일 고지"), "world.thunderrail.identity": ("A storm observatory","폭풍 관측소"),
    "world.prismbloom.name": ("Prismbloom Dream","프리즘꽃 꿈"), "world.prismbloom.identity": ("A crystalline living garden","수정으로 살아 있는 정원"),
    "world.stillstar.name": ("Stillstar Crown","고요별 왕관"), "world.stillstar.identity": ("A fractured sky palace","부서진 하늘 궁전"),
    "mechanic.gust_lift.name": ("Gust lifts","돌풍 상승기류"), "mechanic.breakable.name": ("Breakables","파괴물"),
    "mechanic.conveyor.name": ("Conveyors","컨베이어"), "mechanic.heat_vent.name": ("Heat vents","열기 통풍구"),
    "mechanic.timed_shutter.name": ("Timed shutters","시간 차단문"), "mechanic.current.name": ("Currents","해류"),
    "mechanic.buoyant_pod.name": ("Buoyant pods","부유열매"), "mechanic.falling_water.name": ("Falling water","낙수"),
    "mechanic.rail.name": ("Storm rails","폭풍 레일"), "mechanic.conductor.name": ("Conductors","도체"),
    "mechanic.rotating_tower.name": ("Rotating towers","회전탑"), "mechanic.mirror.name": ("Mirrors","거울"),
    "mechanic.color_beam.name": ("Color beams","색광선"), "mechanic.gravity_bloom.name": ("Gravity blooms","중력꽃"),
    "mechanic.silence_field.name": ("Silence fields","침묵장"), "mechanic.ability_lock.name": ("Ability locks","능력 잠금"),
    "boss.rootjaw.name": ("Rootjaw","뿌리턱"), "boss.crucible_crab.name": ("Crucible Crab","도가니 게"),
    "boss.luma_eel.name": ("Luma Eel","루마 장어"), "boss.volt_roc.name": ("Volt Roc","볼트 로크"),
    "boss.prism_warden.name": ("Prism Warden","프리즘 수호자"), "boss.the_stillness.name": ("The Stillness","정지"),
    "enemy.breezeling.name": ("Breezeling","산들씨"), "enemy.bramblekin.name": ("Bramblekin","덤불족"),
    "enemy.millmite.name": ("Millmite","풍차진드기"), "enemy.cinderling.name": ("Cinderling","불씨족"),
    "enemy.slagroller.name": ("Slag Roller","광재굴림이"), "enemy.shutterimp.name": ("Shutter Imp","차단도깨비"),
    "enemy.bubblefin.name": ("Bubblefin","거품지느러미"), "enemy.shellskiff.name": ("Shell Skiff","조개배"),
    "enemy.moonjelly.name": ("Moonjelly","달해파리"), "enemy.coilbird.name": ("Coilbird","코일새"),
    "enemy.railrunner.name": ("Rail Runner","레일달림이"), "enemy.stormlens.name": ("Storm Lens","폭풍눈"),
    "enemy.petalisk.name": ("Petalisk","꽃잎뱀"), "enemy.mirrormite.name": ("Mirror Mite","거울진드기"),
    "enemy.gravitybud.name": ("Gravity Bud","중력봉오리"), "enemy.hushshade.name": ("Hush Shade","고요그늘"),
    "enemy.lockwarden.name": ("Lock Warden","잠금수호자"), "enemy.riftling.name": ("Riftling","균열씨"),
    "debug.english_only": ("English diagnostic","English diagnostic"),
}

REWARD_COPY = {
    "gallery.sunleaf":("Sunleaf gallery","햇잎 갤러리"), "palette.mint":("Mint palette","민트 팔레트"),
    "challenge.sunleaf":("Sunleaf challenge","햇잎 도전"), "gallery.emberglass":("Emberglass gallery","잿불유리 갤러리"),
    "palette.ember":("Ember palette","잿불 팔레트"), "challenge.emberglass":("Emberglass challenge","잿불유리 도전"),
    "gallery.tidemoon":("Tidemoon gallery","밀물달 갤러리"), "palette.moon":("Moon palette","달빛 팔레트"),
    "challenge.tidemoon":("Tidemoon challenge","밀물달 도전"), "gallery.thunderrail":("Thunderrail gallery","천둥레일 갤러리"),
    "palette.storm":("Storm palette","폭풍 팔레트"), "challenge.thunderrail":("Thunderrail challenge","천둥레일 도전"),
    "gallery.prismbloom":("Prismbloom gallery","프리즘꽃 갤러리"), "palette.prism":("Prism palette","프리즘 팔레트"),
    "challenge.prismbloom":("Prismbloom challenge","프리즘꽃 도전"), "gallery.stillstar":("Stillstar gallery","고요별 갤러리"),
    "palette.stillstar":("Stillstar palette","고요별 팔레트"), "challenge.stillstar":("Stillstar challenge","고요별 도전"),
}


def build() -> dict[str, dict[str, str]]:
    rows = dict(ROWS)
    for world, index, en_name, ko_name, en_intro, ko_intro in STAGE_COPY:
        rows[f"stage.{world}.{index:02d}.name"] = (en_name, ko_name)
        rows[f"stage.{world}.{index:02d}.intro"] = (en_intro, ko_intro)
    for reward_id, pair in REWARD_COPY.items():
        rows[f"reward.{reward_id}.name"] = pair
    return {
        "en": {key: pair[0] for key, pair in sorted(rows.items())},
        "ko": {key: pair[1] for key, pair in sorted(rows.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalogs = build()
    stale: list[str] = []
    for locale, payload in catalogs.items():
        path = Path(f"windsprig/content/strings.{locale}.json")
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.as_posix())
        else:
            path.write_text(text, encoding="utf-8")
    if stale:
        print("STALE: " + ", ".join(stale))
        return 1
    print(f"locales: {len(catalogs['en'])} keys in en/ko")
    return 0
```

- [ ] **Step 5: Implement strict lookup and formatting**

```python
# windsprig/localization.py
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import string
from types import MappingProxyType
from typing import Literal, Mapping


@dataclass(frozen=True, slots=True)
class LocaleCatalog:
    strings: Mapping[str, Mapping[str, str]]


def _fields(value: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(value) if name}


def load_locale_catalog(content_dir: Path) -> LocaleCatalog:
    en = json.loads((content_dir / "strings.en.json").read_text(encoding="utf-8"))
    ko = json.loads((content_dir / "strings.ko.json").read_text(encoding="utf-8"))
    if set(en) != set(ko):
        raise ValueError("locale key sets differ")
    for key in en:
        if _fields(en[key]) != _fields(ko[key]):
            raise ValueError(f"locale placeholders differ for {key}")
    return LocaleCatalog(MappingProxyType({
        "en": MappingProxyType(dict(sorted(en.items()))),
        "ko": MappingProxyType(dict(sorted(ko.items()))),
    }))


@dataclass(frozen=True, slots=True)
class Localizer:
    catalog: LocaleCatalog
    language: Literal["en", "ko"]

    @classmethod
    def load(cls, content_dir: Path, language: Literal["en", "ko"]) -> "Localizer":
        return cls(load_locale_catalog(content_dir), language)

    def text(self, key: str, **values: str | int | float) -> str:
        source = self.catalog.strings[self.language].get(key)
        if source is None:
            source = self.catalog.strings["en"].get(key)
        if source is None:
            raise KeyError(f"missing locale key: {key}")
        return source.format_map(values)
```

- [ ] **Step 6: Add the pinned, hash-verified font fetch**

```python
# tools/fetch_font.py
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

COMMIT = "ec0464b978de222073645d6d3366f3fdf03376d8"
FILES = {
    "NotoSansKR[wght].ttf": (
        f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
        "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252",
    ),
    "OFL-NotoSansKR.txt": (
        f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/notosanskr/OFL.txt",
        "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path("assets/fonts")
    root.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in FILES.items():
        path = root / name
        if args.check:
            if not path.exists() or digest(path.read_bytes()) != expected:
                print(f"INVALID: {path.as_posix()}")
                return 1
            continue
        data = urlopen(url, timeout=30).read()
        if digest(data) != expected:
            raise RuntimeError(f"hash mismatch for {name}")
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    print("font: Noto Sans KR at pinned Google Fonts commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Write `assets/LICENSES.md` with the font family/file names, upstream repository and pinned commit above, both SHA-256 values, the statement “Noto Sans KR is redistributed unmodified under the SIL Open Font License 1.1,” a link to `assets/fonts/OFL-NotoSansKR.txt`, and sections reserving exact generated-art/audio provenance paths used by Tasks 6 and 8.

- [ ] **Step 7: Generate and verify localization assets**

Run: `python tools/generate_locales.py && python tools/fetch_font.py`

Expected: locale command prints at least `locales: 180 keys in en/ko`; font command prints `font: Noto Sans KR at pinned Google Fonts commit`.

Run: `python tools/generate_locales.py --check && python tools/fetch_font.py --check && SDL_VIDEODRIVER=dummy python -m pytest tests/unit/content/test_localization.py -q`

Expected: both checks exit 0 and pytest reports `3 passed`.

- [ ] **Step 8: Commit locale data, font, and license**

```powershell
git add tools/generate_locales.py tools/fetch_font.py windsprig/content/strings.en.json windsprig/content/strings.ko.json windsprig/localization.py assets/fonts assets/LICENSES.md tests/unit/content/test_localization.py
git commit -m "feat: add English and Korean presentation"
```

---

### Task 6: Original procedural vector-style art, packed atlases, and mandatory asset loading

**Files:**
- Create: `tools/generate_art.py`
- Create: `windsprig/content/assets.json`
- Create: `windsprig/render/assets.py`
- Create: `assets/generated/player/sprig.png`
- Create: `assets/generated/enemies/*.png` (18 files)
- Create: `assets/generated/bosses/*.png` (6 files)
- Create: `assets/generated/worlds/*.png` (24 files)
- Create: `assets/generated/ui/icons.png`
- Create: `assets/generated/ui/favicon.png`
- Create: `assets/generated/ui/social-card.png`
- Create: `assets/generated/art-provenance.json`
- Create: `tests/unit/render/test_assets.py`

**Interfaces:**
- Consumes: world/enemy/boss/ability IDs, locale font path, pygame-ce drawing/image APIs.
- Produces: 52 original PNGs, 56 named Sprig frames across 14 required states, 18 enemy silhouettes, 18 boss-phase frames, six world art sets, UI/action/status icons, provenance hashes, `AssetManifest`, and mandatory `AssetCatalog`.

- [ ] **Step 1: Write failing generation and mandatory-load tests**

```python
# tests/unit/render/test_assets.py
from pathlib import Path

import pytest

from windsprig.content.loader import load_asset_manifest
from windsprig.render.assets import AssetCatalog, MissingAssetError


def test_release_art_manifest_is_complete_and_original() -> None:
    manifest = load_asset_manifest(Path("windsprig/content/assets.json"))
    art = manifest.art
    assert len(art) == 52
    assert art["player.sprig"].frames == 56
    assert len([asset_id for asset_id in art if asset_id.startswith("enemy.")]) == 18
    assert len([asset_id for asset_id in art if asset_id.startswith("boss.")]) == 6
    assert len([asset_id for asset_id in art if asset_id.startswith("world.")]) == 24
    assert all(item.provenance == "procedural-vector-v1" for item in art.values())


def test_missing_mandatory_asset_fails_release_load(tmp_path: Path) -> None:
    manifest = load_asset_manifest(Path("windsprig/content/assets.json"))
    with pytest.raises(MissingAssetError, match="player.sprig"):
        AssetCatalog.load(tmp_path, manifest, developer_mode=False)
```

- [ ] **Step 2: Run the asset tests and confirm missing manifest/art failures**

Run: `SDL_VIDEODRIVER=dummy python -m pytest tests/unit/render/test_assets.py -q`

Expected: tests fail because generated art and the strict asset manifest are absent.

- [ ] **Step 3: Define the complete art inventory and distinct silhouette data**

```python
# tools/generate_art.py
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import tempfile

import pygame

CLIPS = {
    "idle": 4, "run": 6, "jump": 2, "fall": 2, "hover": 4, "draw": 4,
    "captured": 2, "harmonize": 6, "attack": 6, "guard": 2, "dodge": 4,
    "hurt": 2, "defeated": 4, "victory": 6,
}

WORLD_ART = {
    "world_1": {"sky":(151,220,214),"far":(91,177,123),"near":(45,111,76),"accent":(244,198,76),"paper":(239,229,180)},
    "world_2":{"sky":(70,38,66),"far":(126,54,49),"near":(55,29,43),"accent":(255,135,54),"paper":(221,102,66)},
    "world_3":{"sky":(25,50,91),"far":(43,89,119),"near":(21,47,76),"accent":(130,224,220),"paper":(101,157,176)},
    "world_4":{"sky":(42,51,88),"far":(72,79,123),"near":(32,38,66),"accent":(245,224,82),"paper":(130,147,174)},
    "world_5":{"sky":(93,68,128),"far":(85,153,155),"near":(48,83,92),"accent":(244,145,218),"paper":(177,222,181)},
    "world_6":{"sky":(19,25,54),"far":(49,54,91),"near":(17,20,42),"accent":(190,227,255),"paper":(116,119,160)},
}

ENEMY_SHAPES = {
    "breezeling":((8,34),(22,12),(45,18),(55,36),(33,54),(14,48)),
    "bramblekin":((9,48),(14,18),(25,26),(32,7),(39,27),(53,17),(55,49),(31,56)),
    "millmite":((8,24),(18,17),(24,7),(34,16),(45,9),(48,22),(57,30),(48,38),(51,51),(37,49),(29,57),(20,47),(8,45),(14,33)),
    "cinderling":((16,53),(12,35),(23,24),(28,7),(38,24),(49,31),(47,52),(31,57)),
    "slagroller":((7,32),(14,14),(31,7),(50,15),(57,32),(49,51),(30,57),(13,49)),
    "shutterimp":((10,13),(52,13),(55,51),(36,45),(31,57),(26,45),(7,51)),
    "bubblefin":((6,31),(18,17),(39,15),(55,31),(39,48),(18,46)),
    "shellskiff":((7,39),(17,18),(32,8),(47,19),(57,39),(46,52),(18,52)),
    "moonjelly":((13,13),(31,6),(50,14),(56,34),(47,31),(43,54),(34,35),(26,55),(20,32),(8,35)),
    "coilbird":((7,35),(23,25),(28,8),(38,25),(56,31),(45,40),(51,54),(31,46),(14,53)),
    "railrunner":((7,22),(23,11),(45,14),(57,29),(48,41),(54,54),(33,49),(17,56),(20,42),(7,36)),
    "stormlens":((7,31),(18,17),(31,11),(47,18),(57,31),(46,45),(31,52),(17,45)),
    "petalisk":((7,34),(20,25),(15,10),(31,20),(45,8),(43,25),(57,34),(43,43),(47,56),(31,47),(16,55),(20,42)),
    "mirrormite":((31,5),(55,31),(31,57),(7,31)),
    "gravitybud":((9,46),(14,24),(27,29),(31,7),(36,29),(50,23),(55,46),(41,56),(22,56)),
    "hushshade":((10,52),(13,20),(24,9),(32,21),(40,8),(52,21),(55,52),(42,44),(33,56),(23,44)),
    "lockwarden":((10,27),(18,13),(24,7),(40,7),(47,14),(54,28),(50,55),(14,55)),
    "riftling":((7,49),(17,15),(29,24),(35,6),(43,29),(57,18),(50,54),(29,47)),
}

BOSS_SHAPES = {
    "rootjaw":((4,51),(10,20),(22,10),(31,24),(43,7),(59,21),(61,52),(39,45),(31,61),(22,45)),
    "crucible_crab":((4,43),(13,21),(25,26),(31,9),(38,26),(51,20),(60,43),(49,57),(15,57)),
    "luma_eel":((3,35),(14,18),(28,12),(43,18),(61,9),(52,30),(61,48),(42,43),(27,55),(12,49)),
    "volt_roc":((3,35),(20,24),(26,5),(34,22),(45,9),(43,27),(61,34),(45,43),(49,60),(31,49),(14,59),(19,42)),
    "prism_warden":((32,3),(59,22),(51,54),(32,62),(12,53),(5,22)),
    "the_stillness":((5,53),(11,15),(25,22),(32,3),(39,22),(54,14),(59,53),(43,46),(32,61),(20,46)),
}

ABILITY_COLORS = {
    "bloomblade":(126,224,132), "cinder":(255,112,63), "voltsong":(255,226,73),
    "galehook":(100,218,214), "stoneheart":(154,144,134), "tempest":(190,155,255),
}
```

- [ ] **Step 4: Implement deterministic atlas drawing and provenance**

```python
# append to tools/generate_art.py
OUTLINE = (25, 35, 43)
SPRIG_MINT = (126, 222, 151)
SPRIG_GOLD = (247, 196, 73)


def pixel_hash(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA")).hexdigest()


def save(surface: pygame.Surface, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, path)


def draw_sprig(cell: pygame.Surface, state: str, frame: int) -> None:
    phase = frame / CLIPS[state] * math.tau
    lean = {"run":4,"dodge":8,"hurt":-5,"defeated":10}.get(state, 0)
    bob = round(math.sin(phase) * (2 if state in {"idle","hover","victory"} else 1))
    body = [(18+lean,48+bob),(14+lean,31+bob),(22+lean,16+bob),(34+lean,10+bob),(46+lean,22+bob),(50+lean,42+bob),(36+lean,55+bob)]
    pygame.draw.polygon(cell, OUTLINE, body)
    inner = [(x + (1 if x < 32 else -1), y + (2 if y < 30 else -2)) for x, y in body]
    pygame.draw.polygon(cell, SPRIG_MINT, inner)
    crest = [(29+lean,14+bob),(36+lean,2+bob),(42+lean,17+bob)]
    pygame.draw.polygon(cell, OUTLINE, crest)
    pygame.draw.polygon(cell, (82,184,112), [(31+lean,13+bob),(36+lean,5+bob),(39+lean,16+bob)])
    scarf_wave = 5 + round(math.sin(phase) * 3)
    scarf = [(41+lean,23+bob),(60,19+scarf_wave),(53,29+scarf_wave),(40+lean,30+bob)]
    pygame.draw.polygon(cell, OUTLINE, scarf)
    pygame.draw.polygon(cell, SPRIG_GOLD, [(42+lean,24+bob),(57,21+scarf_wave),(51,27+scarf_wave),(41+lean,28+bob)])
    eye_y = 27 + bob
    pygame.draw.line(cell, OUTLINE, (29+lean,eye_y), (31+lean,eye_y), 2)
    pygame.draw.line(cell, OUTLINE, (39+lean,eye_y), (41+lean,eye_y), 2)
    stride = round(math.sin(phase) * 5) if state == "run" else 0
    pygame.draw.line(cell, OUTLINE, (25+lean,48+bob), (21+lean-stride,59), 3)
    pygame.draw.line(cell, OUTLINE, (40+lean,47+bob), (44+lean+stride,59), 3)
    if state == "guard":
        pygame.draw.arc(cell, (226,244,197), pygame.Rect(7,8,51,51), -1.2, 1.2, 4)
    if state == "draw":
        pygame.draw.arc(cell, (126,233,224), pygame.Rect(43,19,18+frame*4,22), -1.0, 1.0, 3)
    if state == "captured":
        pygame.draw.circle(cell, ABILITY_COLORS["galehook"], (32,7), 5, 2)
    if state == "harmonize":
        pygame.draw.circle(cell, tuple(ABILITY_COLORS.values())[frame % 6], (32,32), 27, 3)
    if state == "attack":
        pygame.draw.arc(cell, ABILITY_COLORS["bloomblade"], pygame.Rect(31,8,31,47), -1.4, 1.3, 5)
    if state == "dodge":
        pygame.draw.line(cell, (126,233,224), (4,24+frame*3), (20,24+frame*3), 3)
    if state == "victory":
        pygame.draw.circle(cell, SPRIG_GOLD, (10+frame*8,8+frame%2*4), 2)


def player_atlas() -> tuple[pygame.Surface, dict[str, list[int]]]:
    atlas = pygame.Surface((64 * 8, 64 * 7), pygame.SRCALPHA)
    frames: dict[str, list[int]] = {}
    cursor = 0
    for state, count in CLIPS.items():
        frames[state] = []
        for frame in range(count):
            cell = pygame.Surface((64,64), pygame.SRCALPHA)
            draw_sprig(cell, state, frame)
            atlas.blit(cell, ((cursor % 8) * 64, (cursor // 8) * 64))
            frames[state].append(cursor)
            cursor += 1
    assert cursor == 56
    return atlas, frames


def silhouette_atlas(points: tuple[tuple[int,int], ...], color: tuple[int,int,int], frames: int) -> pygame.Surface:
    atlas = pygame.Surface((64 * frames, 64), pygame.SRCALPHA)
    for frame in range(frames):
        cell = pygame.Surface((64,64), pygame.SRCALPHA)
        offset = frame % 2
        shifted = [(x, y - offset) for x, y in points]
        pygame.draw.polygon(cell, OUTLINE, shifted)
        center = pygame.Vector2(32,32)
        inner = [
            tuple(center + (pygame.Vector2(x,y) - center) * 0.86)
            for x, y in shifted
        ]
        pygame.draw.polygon(cell, color, inner)
        pygame.draw.circle(cell, (248,250,230), (24,29-offset), 3)
        pygame.draw.circle(cell, OUTLINE, (25,29-offset), 1)
        atlas.blit(cell, (frame*64,0))
    return atlas


def vertical_gradient(size: tuple[int,int], top: tuple[int,int,int], bottom: tuple[int,int,int]) -> pygame.Surface:
    surface = pygame.Surface(size)
    for y in range(size[1]):
        t = y / max(1, size[1]-1)
        color = tuple(round(top[i] + (bottom[i]-top[i])*t) for i in range(3))
        pygame.draw.line(surface, color, (0,y), (size[0],y))
    return surface


def world_set(world_id: str, palette: dict[str, tuple[int,int,int]], seed: int) -> dict[str, pygame.Surface]:
    rng = random.Random(seed)
    background = pygame.Surface((1280, 720*4))
    for layer in range(4):
        panel = vertical_gradient((1280,720), palette["sky"], palette["far"])
        for index in range(18 - layer*3):
            x = rng.randrange(0,1280)
            y = rng.randrange(80+layer*80,620)
            radius = rng.randrange(20,70)
            pygame.draw.circle(panel, palette["paper"], (x,y), radius, 2)
        background.blit(panel, (0,layer*720))
    tiles = pygame.Surface((64*6,64), pygame.SRCALPHA)
    for index in range(6):
        rect = pygame.Rect(index*64,0,64,64)
        pygame.draw.rect(tiles, palette["near"], rect)
        pygame.draw.polygon(tiles, palette["paper"], [(rect.left,14),(rect.centerx,4),(rect.right,18),(rect.right,28),(rect.left,28)])
        pygame.draw.rect(tiles, OUTLINE, rect, 3)
    props = pygame.Surface((96*4,96), pygame.SRCALPHA)
    for index in range(4):
        cx = index*96+48
        pygame.draw.line(props, OUTLINE, (cx,78),(cx,30),7)
        pygame.draw.circle(props, palette["accent"], (cx,24), 14+index*2)
        pygame.draw.circle(props, OUTLINE, (cx,24), 14+index*2, 3)
    transition = vertical_gradient((1280,720), palette["sky"], palette["near"])
    pygame.draw.polygon(transition, palette["paper"], [(0,590),(260,390),(510,540),(790,320),(1030,500),(1280,360),(1280,720),(0,720)])
    pygame.draw.arc(transition, palette["accent"], pygame.Rect(360,110,560,320), 0.2, 2.8, 12)
    return {"background":background,"tiles":tiles,"props":props,"transition":transition}


def build(root: Path) -> dict[str, object]:
    pygame.init()
    art: dict[str, object] = {}
    sprig, clips = player_atlas()
    entries: list[tuple[str, Path, pygame.Surface, int]] = [
        ("player.sprig", root/"player/sprig.png", sprig, 56)
    ]
    enemy_colors = [palette["accent"] for palette in WORLD_ART.values() for _ in range(3)]
    for (enemy_id, points), color in zip(ENEMY_SHAPES.items(), enemy_colors, strict=True):
        entries.append((f"enemy.{enemy_id}", root/f"enemies/{enemy_id}.png", silhouette_atlas(points,color,4),4))
    for boss_index, (boss_id, points) in enumerate(BOSS_SHAPES.items()):
        color = list(WORLD_ART.values())[boss_index]["accent"]
        entries.append((f"boss.{boss_id}", root/f"bosses/{boss_id}.png", silhouette_atlas(points,color,18),18))
    for world_index, (world_id, palette) in enumerate(WORLD_ART.items(), 1):
        for kind, surface in world_set(world_id,palette,1000+world_index).items():
            entries.append((f"world.{world_id}.{kind}",root/f"worlds/{world_id}-{kind}.png",surface,4 if kind=="background" else 1))
    icons = pygame.Surface((64*32,64), pygame.SRCALPHA)
    for index in range(32):
        color = list(ABILITY_COLORS.values())[index % 6]
        pygame.draw.circle(icons, OUTLINE, (index*64+32,32), 24)
        pygame.draw.polygon(icons, color, [(index*64+32,10),(index*64+53,45),(index*64+11,45)])
    favicon = pygame.transform.smoothscale(sprig.subsurface(pygame.Rect(0,0,64,64)),(192,192))
    social = vertical_gradient((1200,630),WORLD_ART["world_1"]["sky"],WORLD_ART["world_6"]["near"])
    social.blit(pygame.transform.smoothscale(favicon,(360,360)),(80,135))
    pygame.draw.arc(social,SPRIG_GOLD,pygame.Rect(430,120,680,390),0.2,2.9,18)
    entries.extend([
        ("ui.icons",root/"ui/icons.png",icons,32),
        ("ui.favicon",root/"ui/favicon.png",favicon,1),
        ("ui.social_card",root/"ui/social-card.png",social,1),
    ])
    for asset_id, path, surface, frames in entries:
        save(surface,path)
        art[asset_id] = {
            "path": path.as_posix().removeprefix("assets/"),
            "width": surface.get_width(), "height": surface.get_height(),
            "frames": frames, "pixel_sha256": pixel_hash(surface),
            "mandatory": True, "provenance": "procedural-vector-v1",
        }
    provenance = {
        "generator":"tools/generate_art.py", "algorithm":"procedural-vector-v1",
        "seeds":{world:1000+index for index,world in enumerate(WORLD_ART,1)},
        "asset_hashes":{key:value["pixel_sha256"] for key,value in sorted(art.items())},
        "license":"Original project art distributed under the root MIT license",
    }
    (root/"art-provenance.json").write_text(json.dumps(provenance,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest_path = Path("windsprig/content/assets.json")
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    existing["art"] = dict(sorted(art.items()))
    existing["font"] = {"path":"fonts/NotoSansKR[wght].ttf","license":"fonts/OFL-NotoSansKR.txt","mandatory":True}
    manifest_path.write_text(json.dumps(existing,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    assert len(art) == 52
    return existing
```

`main()` initializes SDL dummy drivers, generates into `assets/generated` normally, and for `--check` generates into `TemporaryDirectory`, loads each committed/generated image, compares dimensions and `pixel_hash`, compares canonical manifest/provenance JSON after replacing the temporary prefix, prints every stale asset ID, and exits 1 without modifying committed files. On success it prints `art: 52 PNGs, 56 player frames, 18 enemies, 18 boss phases, 6 world sets`.

- [ ] **Step 5: Implement mandatory asset loading with developer diagnostics**

```python
# windsprig/render/assets.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame


class MissingAssetError(RuntimeError):
    pass


@dataclass(slots=True)
class AssetCatalog:
    images: dict[str, pygame.Surface]
    sound_paths: dict[str, Path]
    font_path: Path
    developer_mode: bool

    @classmethod
    def load(cls, root: Path, manifest, *, developer_mode: bool = False) -> "AssetCatalog":
        images: dict[str, pygame.Surface] = {}
        missing: list[str] = []
        for asset_id, spec in manifest.art.items():
            path = root / spec.path
            if not path.is_file():
                missing.append(asset_id)
                continue
            surface = pygame.image.load(path.as_posix())
            if surface.get_size() != (spec.width, spec.height):
                raise MissingAssetError(f"{asset_id}: invalid dimensions")
            images[asset_id] = surface.convert_alpha() if pygame.display.get_surface() else surface
        font_path = root / manifest.font.path
        if not font_path.is_file():
            missing.append("font.noto_sans_kr")
        if missing and not developer_mode:
            raise MissingAssetError("missing mandatory assets: " + ", ".join(sorted(missing)))
        if missing:
            for asset_id in missing:
                surface = pygame.Surface((64,64), pygame.SRCALPHA)
                surface.fill((255,0,255,180))
                pygame.draw.line(surface,(0,0,0),(0,0),(63,63),6)
                pygame.draw.line(surface,(0,0,0),(63,0),(0,63),6)
                images[asset_id] = surface
        sounds = {cue_id: root / spec.path for cue_id, spec in manifest.audio.items()}
        return cls(images, sounds, font_path, developer_mode)

    def image(self, asset_id: str) -> pygame.Surface:
        if asset_id not in self.images:
            raise MissingAssetError(asset_id)
        return self.images[asset_id]

    def sound_path(self, cue_id: str) -> Path:
        if cue_id not in self.sound_paths:
            raise MissingAssetError(cue_id)
        return self.sound_paths[cue_id]

    def font(self, size_px: int, weight: int = 500) -> pygame.font.Font:
        font = pygame.font.Font(self.font_path.as_posix(), size_px)
        font.set_bold(weight >= 700)
        return font
```

- [ ] **Step 6: Generate, check, and test art**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tools/generate_art.py`

Expected: `art: 52 PNGs, 56 player frames, 18 enemies, 18 boss phases, 6 world sets`.

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tools/generate_art.py --check && SDL_VIDEODRIVER=dummy python -m pytest tests/unit/render/test_assets.py -q`

Expected: the generator exits 0 without file writes and pytest reports `2 passed`.

- [ ] **Step 7: Commit original art and provenance**

```powershell
git add tools/generate_art.py windsprig/content/assets.json windsprig/render/assets.py assets/generated/player assets/generated/enemies assets/generated/bosses assets/generated/worlds assets/generated/ui assets/generated/art-provenance.json assets/LICENSES.md tests/unit/render/test_assets.py
git commit -m "feat: generate original Windsprig art atlases"
```

---

### Task 7: Animation, particles, camera, logical display, renderer, and accessible HUD

**Files:**
- Create: `windsprig/render/animation.py`
- Create: `windsprig/render/effects.py`
- Rewrite: `windsprig/render/camera.py`
- Create: `windsprig/render/ui.py`
- Rewrite: `windsprig/render/hud.py`
- Create: `windsprig/render/renderer.py`
- Create: `tests/unit/render/test_animation.py`
- Create: `tests/unit/render/test_effects.py`
- Create: `tests/unit/render/test_camera.py`
- Create: `tests/unit/render/test_hud.py`

**Interfaces:**
- Consumes: `StageSnapshot`, `BossView`, semantic `GameEvent` tuples, `AccessibilitySettings`, `AssetCatalog`, `Localizer`, and 1280×720 canvas.
- Produces: `AnimationClip`, `AnimationCursor`, `AnimationBank`, `Particle`, `EffectFrame`, `EffectsDirector`, `CameraView`, `Letterbox`, `CameraController`, `HudViewModel`, and `StageRenderer.render()`.

- [ ] **Step 1: Write failing animation/effects/camera/HUD tests**

```python
# tests/unit/render/test_animation.py
from windsprig.render.animation import AnimationClip, AnimationCursor


def test_animation_advances_once_per_render_delta_and_emits_markers_once() -> None:
    clip = AnimationClip("attack", (20,21,22), (80,80,120), False, ((1,"swing"),))
    cursor = AnimationCursor.start(clip)
    advanced, markers = cursor.advance(170)
    assert (advanced.frame_id, advanced.elapsed_in_frame_ms, markers) == (22,10,("swing",))


# tests/unit/render/test_effects.py
from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AccessibilitySettings
from windsprig.render.effects import EffectsDirector


def test_reduced_motion_preserves_hit_readability_without_shake_or_afterimages() -> None:
    settings = AccessibilitySettings(screen_shake=False,reduced_motion=True,draw_toggle=False,guard_toggle=False)
    frame = EffectsDirector(seed=19).handle(
        (GameEvent("AttackHit", {"x":320.0,"y":240.0,"facing":-1}),), settings
    )
    assert frame.shake is None
    assert frame.flash is not None
    assert 1 <= len(frame.particles) <= 4
    assert all(particle.kind != "afterimage" for particle in frame.particles)


# tests/unit/render/test_camera.py
from windsprig.gameplay.snapshot import CameraTargetView
from windsprig.render.camera import CameraController, compute_letterbox


def test_camera_clamps_to_bounds_and_reports_distant_coop_catchup() -> None:
    camera = CameraController((1280,720))
    targets = (
        CameraTargetView(1,1,1800,500,1.0,True),
        CameraTargetView(2,2,400,500,1.0,True),
    )
    view = camera.update(targets, bounds_px=(0,0,2400,720), dt_ms=16, reduced_motion=False)
    assert view.catch_up_slots == (2,)
    assert 0 <= view.x <= 1120
    assert view.y == 0


def test_letterbox_is_centered_for_supported_sizes() -> None:
    assert compute_letterbox((1920,1080)).destination == (0,0,1920,1080)
    assert compute_letterbox((1440,900)).destination == (0,45,1440,810)
    assert compute_letterbox((1024,576), integer_scaling=True).destination == (0,0,1024,576)
```

- [ ] **Step 2: Run the render-unit tests and confirm missing modules fail**

Run: `SDL_VIDEODRIVER=dummy python -m pytest tests/unit/render/test_animation.py tests/unit/render/test_effects.py tests/unit/render/test_camera.py tests/unit/render/test_hud.py -q`

Expected: collection fails at the first missing render type.

- [ ] **Step 3: Implement animation and event-derived effects**

```python
# windsprig/render/animation.py
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping


@dataclass(frozen=True, slots=True)
class AnimationClip:
    clip_id: str
    frame_ids: tuple[int, ...]
    frame_ms: tuple[int, ...]
    loop: bool
    markers: tuple[tuple[int, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.frame_ids or len(self.frame_ids) != len(self.frame_ms):
            raise ValueError(f"invalid clip {self.clip_id}")
        if any(value <= 0 for value in self.frame_ms):
            raise ValueError(f"non-positive frame duration in {self.clip_id}")


@dataclass(frozen=True, slots=True)
class AnimationCursor:
    clip: AnimationClip
    frame_index: int
    elapsed_in_frame_ms: int
    finished: bool

    @classmethod
    def start(cls, clip: AnimationClip) -> "AnimationCursor":
        return cls(clip,0,0,False)

    @property
    def frame_id(self) -> int:
        return self.clip.frame_ids[self.frame_index]

    def advance(self, dt_ms: int) -> tuple["AnimationCursor", tuple[str, ...]]:
        index, elapsed, finished = self.frame_index, self.elapsed_in_frame_ms + dt_ms, self.finished
        markers: list[str] = []
        while not finished and elapsed >= self.clip.frame_ms[index]:
            elapsed -= self.clip.frame_ms[index]
            next_index = index + 1
            if next_index == len(self.clip.frame_ids):
                if self.clip.loop:
                    next_index = 0
                else:
                    next_index = index
                    elapsed = 0
                    finished = True
            if next_index != index:
                markers.extend(marker for marker_index, marker in self.clip.markers if marker_index == next_index)
            index = next_index
        return replace(self,frame_index=index,elapsed_in_frame_ms=elapsed,finished=finished), tuple(markers)


@dataclass(frozen=True, slots=True)
class AnimationBank:
    clips: Mapping[str, AnimationClip]

    def clip_for(self, actor_state: str) -> AnimationClip:
        key = actor_state.lower().replace(" ","_")
        return self.clips.get(key, self.clips["idle"])
```

```python
# windsprig/render/effects.py
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Sequence

from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AccessibilitySettings


@dataclass(frozen=True, slots=True)
class Particle:
    kind: str
    x: float
    y: float
    vx: float
    vy: float
    life_ms: int
    color_token: str


@dataclass(frozen=True, slots=True)
class Shake:
    amplitude_px: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class Flash:
    x: float
    y: float
    radius_px: int
    pattern_token: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class EffectFrame:
    particles: tuple[Particle, ...]
    shake: Shake | None
    flash: Flash | None


EVENT_EFFECTS = {
    "PlayerDamaged":("impact",10,8,120,"pattern.damage"),
    "EnemyCaptured":("wind_ribbon",12,0,0,"pattern.capture"),
    "CaptureReleased":("leaf",6,0,0,"pattern.release"),
    "EnemyLaunched":("streak",14,10,150,"pattern.launch"),
    "AbilityEquipped":("spark",16,0,0,"pattern.harmonize"),
    "AbilityDropped":("echo",8,0,0,"pattern.echo"),
    "AttackHit":("impact",12,8,100,"pattern.hit"),
    "ProjectileCut":("shard",8,4,70,"pattern.cut"),
    "MoteCollected":("mote",18,0,0,"pattern.mote"),
    "CheckpointReached":("leaf",20,0,0,"pattern.checkpoint"),
    "PlayerDefeated":("paper",14,4,90,"pattern.defeat"),
    "PlayerRespawned":("wind_ribbon",16,0,0,"pattern.respawn"),
    "GatherCompleted":("spark",20,5,80,"pattern.goal"),
    "StageCompleted":("confetti",28,6,100,"pattern.victory"),
    "StageFailed":("paper",18,3,70,"pattern.defeat"),
    "BossPhaseChanged":("shard",24,7,110,"pattern.boss"),
}


class EffectsDirector:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def handle(self, events: Sequence[GameEvent], settings: AccessibilitySettings) -> EffectFrame:
        particles: list[Particle] = []
        shake: Shake | None = None
        flash: Flash | None = None
        for event in events:
            spec = EVENT_EFFECTS.get(event.topic)
            if spec is None:
                continue
            kind,count,amplitude,duration,pattern = spec
            x = float(event.payload.get("x",640.0))
            y = float(event.payload.get("y",360.0))
            limited = min(count,4) if settings.reduced_motion else count
            for index in range(limited):
                angle = self.rng.random()*6.283185307
                speed = 35 + self.rng.random()*95
                particles.append(Particle(kind,x,y,math.cos(angle)*speed,math.sin(angle)*speed,240+index*18,pattern))
            flash = Flash(x,y,28,pattern,90)
            if settings.screen_shake and not settings.reduced_motion and amplitude:
                shake = Shake(amplitude,duration)
        return EffectFrame(tuple(particles),shake,flash)
```

Add `import math` to `effects.py`. Presentation RNG is intentionally `random.Random` owned by the director and never serialized into the deterministic gameplay world.

- [ ] **Step 4: Implement bounded damped camera and exact letterboxing**

```python
# windsprig/render/camera.py
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from windsprig.gameplay.snapshot import CameraTargetView


@dataclass(frozen=True, slots=True)
class Letterbox:
    destination: tuple[int,int,int,int]
    scale: float


@dataclass(frozen=True, slots=True)
class CameraView:
    x: float
    y: float
    look_ahead_x: float
    shake_x: float
    shake_y: float
    catch_up_slots: tuple[int, ...]


def compute_letterbox(
    window_size: tuple[int,int],
    logical_size: tuple[int,int] = (1280,720),
    integer_scaling: bool = False,
) -> Letterbox:
    ww,wh = window_size
    lw,lh = logical_size
    scale = min(ww/lw, wh/lh)
    if integer_scaling and scale >= 1:
        scale = float(max(1,math.floor(scale)))
    width,height = round(lw*scale),round(lh*scale)
    return Letterbox(((ww-width)//2,(wh-height)//2,width,height),scale)


class CameraController:
    SAFE_WIDTH = 760
    LOOK_AHEAD = 128
    DAMP_MS = 140

    def __init__(self, logical_size: tuple[int,int]) -> None:
        self.width,self.height = logical_size
        self.x = 0.0
        self.y = 0.0
        self.previous_center_x: float | None = None

    def update(
        self,
        targets: tuple[CameraTargetView, ...],
        bounds_px: tuple[int,int,int,int],
        dt_ms: int,
        reduced_motion: bool,
    ) -> CameraView:
        active = tuple(target for target in targets if target.enabled and target.weight > 0)
        if not active:
            return CameraView(self.x,self.y,0.0,0.0,0.0,())
        total = sum(target.weight for target in active)
        center_x = sum(target.x*target.weight for target in active)/total
        center_y = sum(target.y*target.weight for target in active)/total
        velocity_x = 0.0 if self.previous_center_x is None else (center_x-self.previous_center_x)/max(1,dt_ms)
        self.previous_center_x = center_x
        look = max(-self.LOOK_AHEAD,min(self.LOOK_AHEAD,velocity_x*90))
        left_edge,right_edge = center_x-self.SAFE_WIDTH/2,center_x+self.SAFE_WIDTH/2
        catch_up = tuple(sorted(target.slot for target in active if target.x < left_edge or target.x > right_edge))
        desired_x,desired_y = center_x+look-self.width/2,center_y-self.height/2
        bx,by,bw,bh = bounds_px
        desired_x = max(bx,min(desired_x,bx+max(0,bw-self.width)))
        desired_y = max(by,min(desired_y,by+max(0,bh-self.height)))
        damping = 1.0-math.exp(-dt_ms/self.DAMP_MS)
        self.x += (desired_x-self.x)*damping
        self.y += (desired_y-self.y)*damping
        if bh <= self.height:
            self.y = float(by)
        return CameraView(self.x,self.y,look,0.0,0.0,catch_up)
```

Shake offsets are applied after `CameraView` construction by `EffectsDirector`; they never affect the bounded `x`/`y`. Co-op slots outside the 760 px safe frame receive a directional catch-up badge; gameplay owns actual catch-up/respawn decisions.

- [ ] **Step 5: Implement contrast-checked UI and HUD models**

```python
# windsprig/render/hud.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HudPlayerVM:
    slot: int
    label: str
    icon_token: str
    color_token: str
    pattern_token: str
    hp_segments: tuple[bool, ...]
    lives_label: str
    ability_icon: str
    ability_label: str
    ability_meter_ratio: float
    hover_ratio: float
    captured_icon: str | None
    captured_label: str
    guard_active: bool
    dodge_active: bool
    invulnerable_pattern: bool


@dataclass(frozen=True, slots=True)
class HudBossVM:
    name: str
    phase_label: str
    hp_ratio: float
    vulnerability_pattern: str
    telegraph_icon: str | None


@dataclass(frozen=True, slots=True)
class HudViewModel:
    players: tuple[HudPlayerVM, ...]
    mote_icons: tuple[bool,bool,bool]
    gather_label: str | None
    catch_up_slots: tuple[int, ...]
    boss: HudBossVM | None
    muted_indicator: bool
    save_status_key: str
```

`build_hud_view(snapshot, stage, active_players, camera, audio_status, save_status, tr)` sorts panels by slot, uses `ActivePlayer.icon_token`, `color_token`, and `pattern.slot-{slot}`, renders HP as discrete segments plus localized text, displays hover and ability meters, shows the captured echo both as icon and localized label, flashes invulnerability with `pattern.invulnerable`, derives three mote booleans from the current stage IDs, and constructs `HudBossVM` from the single `BossView`.

`windsprig/render/ui.py` implements WCAG relative luminance and `contrast_ratio(foreground, background)`; `draw_text()` raises `ValueError` below 4.5 for body text or 3.0 for text at least 24 px, and `draw_panel()` always combines color, outline, icon, text, and hatch/dot/stripe pattern.

- [ ] **Step 6: Implement the VM-only stage renderer**

```python
# windsprig/render/renderer.py
class StageRenderer:
    def __init__(self, assets: AssetCatalog, animations: AnimationBank, tr: Localizer) -> None:
        self.assets = assets
        self.animations = animations
        self.tr = tr
        self.cursors: dict[tuple[str,int], AnimationCursor] = {}

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
        self._draw_parallax(canvas,stage.world_id,camera)
        self._draw_tiles(canvas,stage,camera)
        self._draw_interactions(canvas,snapshot.interactions,camera)
        self._draw_collectibles(canvas,stage,snapshot.collected_mote_ids,camera)
        self._draw_checkpoints_and_goal(canvas,snapshot,camera)
        self._draw_enemies(canvas,snapshot.enemies,camera,render_dt_ms)
        self._draw_bosses(canvas,snapshot.bosses,camera,render_dt_ms)
        self._draw_players(canvas,snapshot.players,camera,render_dt_ms)
        self._draw_attacks_and_echoes(canvas,snapshot,camera)
        self._draw_effects(canvas,effects,camera)
        self._draw_hud(canvas,hud)
```

Every private draw method consumes only its explicit immutable argument, slices frames by manifest metadata, and maps IDs directly: `player.sprig`, `enemy.{enemy_kind}`, `boss.{boss_id}`, `world.{world_id}.{layer}`, `ability.{ability_id}`, and `ui.icons`. It never imports `World`, component stores, systems, or runtime resources. Animation cursors key by `("player", entity_id)`, `("enemy", entity_id)`, and `("boss", entity_id)`, advance exactly once per rendered frame, and are removed when an entity leaves its snapshot tuple.

- [ ] **Step 7: Run render-unit tests**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/unit/render -q`

Expected: `18 passed`.

- [ ] **Step 8: Commit the presentation renderer**

```powershell
git add windsprig/render tests/unit/render
git commit -m "feat: add accessible animated campaign renderer"
```

---

### Task 8: Original generated music/SFX, provenance, and phase-aware audio direction

**Files:**
- Create: `tools/generate_audio.py`
- Modify: `windsprig/content/assets.json`
- Create: `windsprig/audio/cues.py`
- Create: `windsprig/audio/music.py`
- Create: `assets/generated/audio/music/*.wav` (28 files)
- Create: `assets/generated/audio/sfx/*.wav` (29 files)
- Create: `assets/generated/audio-provenance.json`
- Modify: `assets/LICENSES.md`
- Create: `tests/unit/audio/test_generated_audio.py`
- Create: `tests/unit/audio/test_music_director.py`

**Interfaces:**
- Consumes: foundation `AudioService`/`AudioStatus`, `AudioSettings`, semantic events, and boss phase IDs.
- Produces: 28 loopable music IDs, 29 one-shot SFX IDs, canonical PCM/provenance records, `cue_for_event()`, and `MusicDirector`.

- [ ] **Step 1: Write failing WAV/provenance and director tests**

```python
# tests/unit/audio/test_generated_audio.py
from pathlib import Path
import json
import wave


def test_audio_catalog_has_exact_release_inventory_and_pcm_format() -> None:
    provenance = json.loads(Path("assets/generated/audio-provenance.json").read_text(encoding="utf-8"))
    assert len(provenance["music"]) == 28
    assert len(provenance["sfx"]) == 29
    for item in provenance["music"].values() | provenance["sfx"].values():
        with wave.open(item["path"], "rb") as source:
            assert source.getnchannels() == 1
            assert source.getsampwidth() == 2
            assert source.getframerate() == 22050


def test_music_loop_seams_are_near_silent() -> None:
    provenance = json.loads(Path("assets/generated/audio-provenance.json").read_text(encoding="utf-8"))
    for item in provenance["music"].values():
        with wave.open(item["path"], "rb") as source:
            frames = source.readframes(source.getnframes())
        samples = memoryview(frames).cast("h")
        assert abs(samples[0] - samples[-1]) <= 64


# tests/unit/audio/test_music_director.py
from windsprig.audio.music import MusicDirector
from windsprig.core.events import GameEvent
from tests.helpers.audio import FakeAudioService


def test_boss_phase_event_selects_exact_variation() -> None:
    audio = FakeAudioService()
    director = MusicDirector(audio)
    played = director.handle((GameEvent("BossPhaseChanged", {
        "boss_id":"volt_roc", "phase_id":"volt_roc.chain_sky", "phase_index":2,
    }),))
    assert played == ("music.boss.volt_roc.p2",)
    assert audio.calls[-1] == ("music.boss.volt_roc.p2","music")
```

- [ ] **Step 2: Run audio tests and confirm generated files/modules are missing**

Run: `SDL_AUDIODRIVER=dummy python -m pytest tests/unit/audio -q`

Expected: collection or file setup fails because the generator outputs and audio director are absent.

- [ ] **Step 3: Define the original composition and SFX parameter catalogs**

```python
# tools/generate_audio.py
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import tempfile
import wave

RATE = 22050
REST = -99

THEMES = {
    "world_1":(112,60,(0,2,4,7,9,7,4,2,0,4,7,11,9,7,4,2),(0,7,5,7,0,7,5,4),"triangle"),
    "world_2":(124,50,(0,3,7,8,7,3,0,REST,0,5,8,10,8,5,3,REST),(0,5,3,7,0,8,5,7),"square"),
    "world_3":(88,57,(0,2,5,7,9,7,5,2,0,5,9,12,9,7,5,2),(0,5,2,7,0,5,9,7),"sine"),
    "world_4":(138,62,(0,3,5,10,7,5,3,0,0,7,10,12,10,7,5,3),(0,7,3,10,0,7,5,10),"saw"),
    "world_5":(104,65,(0,2,6,7,11,9,7,6,0,6,9,13,11,9,7,2),(0,6,2,7,0,9,6,7),"triangle"),
    "world_6":(76,48,(0,3,5,7,REST,5,3,0,0,7,8,12,10,8,5,3),(0,5,3,7,0,8,5,10),"sine"),
}

SYSTEM_THEMES = {
    "title":(96,60,(0,4,7,11,9,7,4,2,0,7,12,11,9,7,4,REST),(0,7,5,4,0,7,9,5),"triangle"),
    "map":(108,55,(0,2,4,7,4,2,0,REST,5,7,9,12,9,7,5,REST),(0,5,7,4,0,5,9,7),"sine"),
    "results":(120,67,(0,4,7,12,11,9,7,4,5,9,12,16,14,12,9,7),(0,7,5,9,0,7,5,12),"triangle"),
    "credits":(84,53,(0,5,7,9,7,5,2,0,0,4,7,11,9,7,4,2),(0,5,2,7,0,4,5,7),"sine"),
}

SFX = {
    "ui.confirm":("sine",0.12,520,780,0.00), "ui.cancel":("triangle",0.14,420,220,0.00),
    "save.ok":("sine",0.22,440,660,0.00), "player.jump":("triangle",0.20,260,620,0.00),
    "player.hover":("sine",0.34,360,300,0.08), "draw.start":("sine",0.40,180,520,0.12),
    "draw.release":("triangle",0.25,520,170,0.05), "enemy.launch":("saw",0.32,220,760,0.08),
    "harmonize":("sine",0.55,330,990,0.02), "damage":("square",0.20,170,90,0.25),
    "guard":("triangle",0.18,240,180,0.10), "dodge":("sine",0.22,640,280,0.08),
    "mote":("sine",0.35,660,1320,0.00), "checkpoint":("triangle",0.60,392,784,0.01),
    "goal":("sine",0.75,440,880,0.00), "defeat":("triangle",0.85,330,110,0.06),
    "victory":("sine",0.90,523,1046,0.00),
    "ability.bloomblade":("triangle",0.28,380,620,0.05),
    "ability.cinder":("saw",0.42,210,150,0.18),
    "ability.voltsong":("square",0.35,720,960,0.12),
    "ability.galehook":("sine",0.38,310,690,0.10),
    "ability.stoneheart":("triangle",0.50,130,70,0.16),
    "ability.tempest":("saw",0.90,180,880,0.20),
    "boss.rootjaw":("triangle",0.55,120,70,0.20),
    "boss.crucible_crab":("square",0.52,150,95,0.18),
    "boss.luma_eel":("sine",0.58,420,840,0.06),
    "boss.volt_roc":("square",0.48,760,190,0.22),
    "boss.prism_warden":("triangle",0.62,520,1040,0.08),
    "boss.the_stillness":("sine",0.80,90,720,0.14),
}
```

- [ ] **Step 4: Implement deterministic PCM music/SFX generation and canonical provenance**

```python
# append to tools/generate_audio.py
def oscillator(kind: str, phase: float) -> float:
    cycle = phase / math.tau
    if kind == "sine":
        return math.sin(phase)
    if kind == "triangle":
        return 2.0 * abs(2.0 * (cycle - math.floor(cycle + 0.5))) - 1.0
    if kind == "square":
        return 1.0 if math.sin(phase) >= 0 else -1.0
    return 2.0 * (cycle - math.floor(cycle + 0.5))


def hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def edge_fade(index: int, count: int) -> float:
    fade = max(1,int(RATE*0.025))
    if index < fade:
        return math.sin(index/fade*math.pi/2) ** 2
    if index >= count-fade:
        return math.sin((count-1-index)/fade*math.pi/2) ** 2
    return 1.0


def compose(theme: tuple[int,int,tuple[int,...],tuple[int,...],str], phase: int = 0) -> list[int]:
    tempo,root,melody,bass,kind = theme
    tempo += phase*8
    melody = melody[phase*2:] + melody[:phase*2]
    beats = 16
    count = round(RATE*60/tempo*beats)
    samples: list[int] = []
    for index in range(count):
        time_s = index/RATE
        beat = min(beats-1,int(time_s*tempo/60))
        beat_phase = time_s*tempo/60-beat
        note = melody[beat]
        bass_note = bass[(beat//2)%len(bass)]
        lead = 0.0 if note == REST else oscillator(kind,math.tau*hz(root+note)*time_s)*math.exp(-beat_phase*2.4)
        low = oscillator("sine",math.tau*hz(root-12+bass_note)*time_s)*0.42
        pulse = oscillator("triangle",math.tau*(2+phase)*time_s)*0.08
        value = (lead*0.42+low*0.34+pulse)*edge_fade(index,count)
        samples.append(max(-32767,min(32767,round(value*32767))))
    samples[0] = samples[-1] = 0
    return samples


def synth_sfx(spec: tuple[str,float,int,int,float], seed: int) -> list[int]:
    kind,duration,start_hz,end_hz,noise = spec
    count = round(RATE*duration)
    rng = random.Random(seed)
    phase = 0.0
    output: list[int] = []
    for index in range(count):
        t = index/max(1,count-1)
        frequency = start_hz+(end_hz-start_hz)*t
        phase += math.tau*frequency/RATE
        envelope = math.sin(math.pi*t) ** 1.5
        value = oscillator(kind,phase)*(1-noise)+(rng.random()*2-1)*noise
        output.append(round(max(-1,min(1,value*envelope))*24500))
    output[0] = output[-1] = 0
    return output


def write_wav(path: Path, samples: list[int]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(path.as_posix(),"wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(b"".join(struct.pack("<h",sample) for sample in samples))


def build(root: Path) -> dict[str, object]:
    music_specs: dict[str, tuple[tuple[int,int,tuple[int,...],tuple[int,...],str],int]] = {
        f"music.{cue_id}":(theme,0) for cue_id,theme in SYSTEM_THEMES.items()
    }
    for world_id,theme in THEMES.items():
        music_specs[f"music.world.{world_id}"] = (theme,0)
        boss_id = {
            "world_1":"rootjaw","world_2":"crucible_crab","world_3":"luma_eel",
            "world_4":"volt_roc","world_5":"prism_warden","world_6":"the_stillness",
        }[world_id]
        for phase in (1,2,3):
            music_specs[f"music.boss.{boss_id}.p{phase}"] = (theme,phase)
    provenance: dict[str, object] = {
        "algorithm":"additive-pcm-v1", "sample_rate":RATE,
        "license":"Original project audio distributed under the root MIT license",
        "music":{}, "sfx":{},
    }
    manifest_audio: dict[str, object] = {}
    for cue_id,(theme,phase) in sorted(music_specs.items()):
        path = root/"music"/f"{cue_id.removeprefix('music.').replace('.','-')}.wav"
        write_wav(path,compose(theme,phase))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {"path":path.as_posix(),"sha256":digest,"theme":theme[1],"phase_variant":phase}
        provenance["music"][cue_id] = record
        manifest_audio[cue_id] = {"path":path.as_posix().removeprefix("assets/"),"bus":"music","mandatory":True,"sha256":digest}
    for seed,(cue_id,spec) in enumerate(sorted(SFX.items()),7001):
        full_id = f"sfx.{cue_id}"
        path = root/"sfx"/f"{cue_id.replace('.','-')}.wav"
        write_wav(path,synth_sfx(spec,seed))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {"path":path.as_posix(),"sha256":digest,"seed":seed,"parameters":list(spec)}
        provenance["sfx"][full_id] = record
        manifest_audio[full_id] = {"path":path.as_posix().removeprefix("assets/"),"bus":"sfx","mandatory":True,"sha256":digest}
    Path("assets/generated/audio-provenance.json").write_text(
        json.dumps(provenance,indent=2,sort_keys=True)+"\n",encoding="utf-8"
    )
    manifest_path = Path("windsprig/content/assets.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["audio"] = manifest_audio
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    assert len(provenance["music"]) == 28
    assert len(provenance["sfx"]) == 29
    return provenance
```

`main()` accepts only `--check`; normal mode calls `build(Path("assets/generated/audio"))`, while check mode calls `build(Path(temporary)/"assets/generated/audio")`, compares all 57 decoded PCM streams plus canonical manifest/provenance records, prints stale cue IDs in sorted order, and returns 1 on drift or 0 after printing `audio: 28 music loops, 29 sfx, 22050 Hz mono PCM`.

- [ ] **Step 5: Implement semantic cue mapping and phase-aware director**

```python
# windsprig/audio/cues.py
from windsprig.core.events import GameEvent

STATIC_EVENT_CUES = {
    "PlayerDamaged":"sfx.damage", "EnemyCaptured":"sfx.draw.start",
    "CaptureReleased":"sfx.draw.release", "EnemyLaunched":"sfx.enemy.launch",
    "AbilityEquipped":"sfx.harmonize", "AbilityDropped":"sfx.draw.release",
    "AttackHit":"sfx.damage", "ProjectileCut":"sfx.guard",
    "MoteCollected":"sfx.mote", "CheckpointReached":"sfx.checkpoint",
    "GatherCompleted":"sfx.goal", "PlayerDefeated":"sfx.defeat",
    "PlayerRespawned":"sfx.checkpoint", "StageCompleted":"sfx.victory",
    "StageFailed":"sfx.defeat", "GuardBlocked":"sfx.guard", "DodgeStarted":"sfx.dodge",
}


def cue_for_event(event: GameEvent) -> str | None:
    if event.topic == "AttackSpawned":
        ability_id = str(event.payload.get("ability_id",""))
        return f"sfx.ability.{ability_id}" if ability_id else None
    if event.topic == "BossAttackTelegraphed":
        cue = str(event.payload.get("cue_id",""))
        return cue if cue.startswith("sfx.") else None
    return STATIC_EVENT_CUES.get(event.topic)
```

```python
# windsprig/audio/music.py
from __future__ import annotations

from typing import Sequence

from windsprig.audio.cues import cue_for_event
from windsprig.core.events import GameEvent
from windsprig.meta.save_models import AudioSettings
from windsprig.platform.services import AudioService


class MusicDirector:
    def __init__(self, audio: AudioService) -> None:
        self.audio = audio
        self.current_music: str | None = None

    def start(self, cue_id: str) -> bool:
        if cue_id == self.current_music:
            return True
        played = self.audio.play_cue(cue_id,"music")
        if played:
            self.current_music = cue_id
        return played

    def handle(self, events: Sequence[GameEvent]) -> tuple[str, ...]:
        played: list[str] = []
        for event in events:
            if event.topic == "BossPhaseChanged":
                cue = f"music.boss.{event.payload['boss_id']}.p{int(event.payload['phase_index'])}"
                if self.start(cue):
                    played.append(cue)
                continue
            cue = cue_for_event(event)
            if cue is not None and self.audio.play_cue(cue,"sfx"):
                played.append(cue)
        return tuple(played)

    def apply_settings(self, settings: AudioSettings) -> None:
        master = 0.0 if settings.muted else settings.master_volume
        self.audio.set_bus_volume("music",master*settings.music_volume)
        self.audio.set_bus_volume("sfx",master*settings.sfx_volume)
```

Stage-intro entry calls `start("music.world.{world_id}")`; boss arena entry calls `start("music.boss.{boss_id}.p1")`; title, map, results, and credits screens call `music.title`, `music.map`, `music.results`, and `music.credits`. Foundation lifecycle focus-loss/restore calls `AudioService.pause()`/`resume()`; a non-ready `AudioStatus` becomes the HUD's localized visible mute indicator.

- [ ] **Step 6: Generate, verify, and test audio**

Run: `python tools/generate_audio.py`

Expected: `audio: 28 music loops, 29 sfx, 22050 Hz mono PCM`.

Run: `python tools/generate_audio.py --check && SDL_AUDIODRIVER=dummy python -m pytest tests/unit/audio -q`

Expected: generator exits 0 without writes and pytest reports `6 passed`.

- [ ] **Step 7: Commit original audio and provenance**

```powershell
git add tools/generate_audio.py windsprig/content/assets.json windsprig/audio assets/generated/audio assets/generated/audio-provenance.json assets/LICENSES.md tests/unit/audio
git commit -m "feat: generate original campaign music and sound"
```

---

### Task 9: Profile, world-map, results, settings, controls, and accessibility screens

**Files:**
- Create: `windsprig/bootstrap.py`
- Modify: `windsprig/__main__.py`
- Modify: `web/main.py`
- Create: `windsprig/screens/factory.py`
- Create: `windsprig/screens/title.py`
- Create: `windsprig/screens/profile.py`
- Create: `windsprig/screens/hub.py`
- Rewrite: `windsprig/screens/world_map.py`
- Create: `windsprig/screens/stage.py`
- Create: `windsprig/screens/pause.py`
- Rewrite: `windsprig/screens/results.py`
- Create: `windsprig/screens/defeat.py`
- Rewrite: `windsprig/screens/settings.py`
- Create: `windsprig/screens/controls.py`
- Create: `windsprig/screens/credits.py`
- Create: `windsprig/screens/recovery.py`
- Modify: `windsprig/meta/presentation_models.py`
- Create: `tests/integration/test_presentation_flow.py`
- Create: `tests/unit/meta/test_settings_models.py`

**Interfaces:**
- Consumes: foundation `Screen`/`ScreenTransition`, `SaveService`, `PlatformServices`, `InputFrame`, `SaveData`/`GlobalSettings`, Task 4 VMs, Task 7 UI renderer, and Task 8 `MusicDirector`.
- Produces: concrete screens for every foundation `ScreenId`, `ProductScreenFactory`, `create_product_screen_factory()`, `SettingsViewModel`, `SettingsAction`, and `apply_settings_action()`.

- [ ] **Step 1: Write failing end-to-end presentation-state tests**

```python
# tests/integration/test_presentation_flow.py
from windsprig.screens.base import ScreenTransition
from tests.helpers.presentation import (
    make_profile_screen, make_world_map_screen, make_results_screen,
    confirm_frame, hold_confirm_frames, move_right_frame,
)


def test_profile_create_select_map_results_next_stage_flow() -> None:
    profile = make_profile_screen()
    profile.on_enter({})
    transition = profile.fixed_update(16,confirm_frame())
    assert transition == ScreenTransition("hub",{"profile_id":"profile_1"})

    world_map = make_world_map_screen(profile_id="profile_1")
    world_map.on_enter({"selected_node_id":"world_1_node_1"})
    transition = world_map.fixed_update(16,confirm_frame())
    assert transition == ScreenTransition("stage_intro",{
        "stage_id":"world_1_stage_1",
        "node_id":"world_1_node_1",
    })

    results = make_results_screen(stage_id="world_1_stage_1")
    results.on_enter(results.payload)
    transition = results.fixed_update(16,confirm_frame())
    assert transition == ScreenTransition("stage_intro",{
        "stage_id":"world_1_stage_2",
        "node_id":"world_1_node_2",
    })


def test_profile_delete_requires_1500_ms_hold_and_save_backup() -> None:
    screen = make_profile_screen(existing=True, delete_mode=True)
    for frame in hold_confirm_frames(total_ms=1488):
        assert screen.fixed_update(16,frame) is None
    transition = screen.fixed_update(16,confirm_frame(held=True))
    assert transition is None
    assert screen.view.cards[0].is_empty
    assert screen.save_service.backup_writes == 1


def test_product_factory_covers_every_screen_id(product_screen_factory) -> None:
    required = {
        "boot", "title", "profile", "hub", "world_map", "stage_intro", "playing",
        "paused", "results", "defeat", "settings", "controls", "credits", "recovery",
    }
    assert set(product_screen_factory.registered_ids) == required
    assert all(product_screen_factory.create(screen_id) is not None for screen_id in sorted(required))
```

```python
# tests/unit/meta/test_settings_models.py
from windsprig.meta.presentation_models import SettingsAction, apply_settings_action
from tests.helpers.presentation import default_settings


def test_reduced_motion_disables_shake_and_persists_other_values() -> None:
    settings = default_settings()
    updated = apply_settings_action(settings,SettingsAction("reduced_motion",True))
    assert updated.accessibility.reduced_motion is True
    assert updated.accessibility.screen_shake is False
    assert updated.audio == settings.audio


def test_volume_values_are_clamped_and_master_multiplies_buses() -> None:
    updated = apply_settings_action(default_settings(),SettingsAction("master_volume",1.4))
    assert updated.audio.master_volume == 1.0
```

- [ ] **Step 2: Run screen/settings tests and confirm concrete screens fail**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/unit/meta/test_settings_models.py tests/integration/test_presentation_flow.py -q`

Expected: collection fails because `SettingsAction`, `apply_settings_action`, and concrete presentation screens are absent.

- [ ] **Step 3: Implement exact settings VM and pure action reducer**

```python
# append to windsprig/meta/presentation_models.py
from dataclasses import dataclass, replace
from typing import Literal

SettingKey = Literal[
    "master_volume","music_volume","sfx_volume","muted","fullscreen",
    "integer_scaling","screen_shake","reduced_motion","draw_toggle",
    "guard_toggle","language","keyboard_p1_preset","keyboard_p2_preset",
    "gamepad_mapping",
]


@dataclass(frozen=True, slots=True)
class SettingsAction:
    key: SettingKey
    value: bool | float | str


@dataclass(frozen=True, slots=True)
class SettingRowVM:
    key: SettingKey
    label: str
    value_label: str
    control_kind: Literal["slider","toggle","choice","remap","link"]
    enabled: bool
    icon_token: str


@dataclass(frozen=True, slots=True)
class SettingsViewModel:
    rows: tuple[SettingRowVM, ...]
    language: str
    remap_supported: bool
    browser_mapping_guidance: str | None
    save_status_key: str
    audio_failure_visible: bool


def apply_settings_action(settings: GlobalSettings, action: SettingsAction) -> GlobalSettings:
    key,value = action.key,action.value
    if key in {"master_volume","music_volume","sfx_volume"}:
        audio = replace(settings.audio, **{key:max(0.0,min(1.0,float(value)))})
        return replace(settings, audio=audio)
    if key == "muted":
        return replace(settings, audio=replace(settings.audio, muted=bool(value)))
    if key in {"fullscreen","integer_scaling"}:
        display = replace(settings.display, **{key:bool(value)})
        return replace(settings, display=display)
    if key in {"screen_shake","reduced_motion","draw_toggle","guard_toggle"}:
        changes = {key:bool(value)}
        if key == "reduced_motion" and bool(value):
            changes["screen_shake"] = False
        accessibility = replace(settings.accessibility, **changes)
        return replace(settings, accessibility=accessibility)
    if key == "language":
        language = str(value)
        if language not in {"en","ko"}:
            raise ValueError(f"unsupported language {language}")
        return replace(settings, language=language)
    controls = replace(settings.controls, **{key:str(value)})
    return replace(settings, controls=controls)
```

`build_settings_view()` emits rows in this stable order: master, music, SFX, mute; fullscreen, integer scaling; screen shake, reduced motion, draw behavior, guard behavior; language; P1 preset, P2 preset, gamepad mapping, control reference. It disables fullscreen when `DisplayCapabilities.fullscreen` is false. On native services it enables gamepad remap and stores stable bindings in `ControlSettings.gamepad_mapping` using `custom:ability=button2;dodge=button1;draw=button0;guard=button4;hover=button3;jump=button0;move=axis0`, sorted by command. On web services it offers `preset:xbox`, `preset:playstation`, and localized mapping guidance without claiming durable custom identifiers.

- [ ] **Step 4: Implement profile create/delete and safe naming**

```python
# windsprig/screens/profile.py
from __future__ import annotations

from dataclasses import replace
import re
from typing import Mapping

from windsprig.screens.base import ScreenTransition

DELETE_HOLD_MS = 1500
NAME_PATTERN = re.compile(r"[^\w가-힣 -]",re.UNICODE)


def safe_profile_name(raw: str, slot: int) -> str:
    cleaned = " ".join(NAME_PATTERN.sub("",raw).split())[:12]
    return cleaned or f"Sprig {slot}"


class ProfileScreen:
    def __init__(self, save_service, save_data, catalog, assets, tr) -> None:
        self.save_service = save_service
        self.save_data = save_data
        self.catalog = catalog
        self.assets = assets
        self.tr = tr
        self.selected = 0
        self.delete_mode = False
        self.delete_hold_ms = 0
        self.view = build_profile_cards(save_data,catalog,tr)

    def on_enter(self, payload: Mapping[str,object]) -> None:
        self.selected = int(payload.get("slot_index",0))
        self.delete_mode = False
        self.delete_hold_ms = 0

    def fixed_update(self, dt_ms: int, input_frame: InputFrame) -> ScreenTransition | None:
        if input_frame.menu_back_pressed:
            return ScreenTransition("title")
        if input_frame.menu_left_pressed:
            self.selected = (self.selected-1)%3
        if input_frame.menu_right_pressed:
            self.selected = (self.selected+1)%3
        if self.delete_mode and input_frame.menu_confirm_held:
            self.delete_hold_ms += dt_ms
            if self.delete_hold_ms >= DELETE_HOLD_MS:
                self._delete_selected()
            return None
        self.delete_hold_ms = 0
        if input_frame.menu_confirm_pressed:
            profile = self.save_data.profiles[self.selected]
            if not profile.display_name:
                self._create_selected(safe_profile_name("",self.selected+1))
                profile = self.save_data.profiles[self.selected]
            return ScreenTransition("hub",{"profile_id":profile.profile_id})
        return None

    def _create_selected(self, name: str) -> None:
        profile = new_profile(self.selected,safe_profile_name(name,self.selected+1))
        profiles = list(self.save_data.profiles)
        profiles[self.selected] = profile
        self._persist(tuple(profiles))

    def _delete_selected(self) -> None:
        profiles = list(self.save_data.profiles)
        profiles[self.selected] = empty_profile(self.selected)
        self._persist(tuple(profiles))
        self.delete_mode = False
        self.delete_hold_ms = 0

    def _persist(self, profiles) -> None:
        from dataclasses import replace
        candidate = replace(self.save_data, profiles=profiles)
        result = self.save_service.save(candidate)
        if result.ok:
            self.save_data = candidate
            self.view = build_profile_cards(candidate,self.catalog,self.tr)

    def render(self, canvas, alpha: float) -> None:
        draw_profile_screen(canvas,self.view,self.selected,self.delete_hold_ms/DELETE_HOLD_MS,self.assets,self.tr)

    def on_exit(self) -> None:
        self.delete_hold_ms = 0
```

Foundation `SaveManager.save()` writes the prior valid primary as its one known-good backup before the new primary, so profile deletion creates the required recoverable backup without screen code writing storage keys.

- [ ] **Step 5: Implement map/results/settings transition contracts**

```text
WorldMapScreen(
    profile: SaveProfile,
    catalog: CatalogBundle,
    assets: AssetCatalog,
    tr: Localizer,
)
WorldMapScreen.on_enter({"selected_node_id": str})
WorldMapScreen confirm -> ScreenTransition("stage_intro", {"stage_id": str, "node_id": str})
WorldMapScreen cancel -> ScreenTransition("hub")

ResultsScreen(
    view: ResultsViewModel,
    assets: AssetCatalog,
    tr: Localizer,
    music: MusicDirector,
)
ResultsScreen.on_enter({"result": StageResult, "delta": CompletionDelta, "profile": SaveProfile})
ResultsScreen choices -> next stage | replay | world map

SettingsScreen(
    save_data: SaveData,
    save_service: SaveService,
    services: PlatformServices,
    assets: AssetCatalog,
    tr: Localizer,
    music: MusicDirector,
)
SettingsScreen action order -> reduce frozen settings | apply platform value | save SaveData | rebuild VM
SettingsScreen save failure -> retain prior SaveData | show localized save.failed | offer retry
```

Implement those exact constructors and payloads as concrete `Screen` implementations. Add the remaining transition contracts exactly:

```text
BootScreen ready -> ScreenTransition("title")
TitleScreen Start -> ScreenTransition("profile")
TitleScreen Settings/Controls/Credits -> matching screen; desktop Quit -> app lifecycle stop request
HubScreen Campaign -> ScreenTransition("world_map", {"profile_id": str})
HubScreen Settings/Controls/Credits -> matching screen
StageIntroScreen Confirm -> ScreenTransition("playing", {"stage_id": str, "node_id": str})
PlayingScreen Pause -> ScreenTransition("paused", {"session": GameSession})
PlayingScreen completed -> ScreenTransition("results", {"result": StageResult})
PlayingScreen failed -> ScreenTransition("defeat", {"session": GameSession})
PauseScreen Resume -> ScreenTransition("playing", {"session": GameSession})
PauseScreen Restart/Map -> confirmation substate before stage_intro/world_map transition
DefeatScreen Checkpoint/Stage/Map -> matching GameSession retry or ScreenTransition
ControlsScreen Back -> prior screen; renders active-device bindings and join guidance
CreditsScreen Back -> title or hub; renders committed license/provenance entries
RecoveryScreen Retry/Restore/New -> SaveService operation followed by profile or title
```

`WorldMapScreen` chooses only `AVAILABLE` or `CLEARED` nodes, uses nearest-node directional navigation rather than list order, and renders locked routes with dashed connectors, lock icon, and text. `ResultsScreen` displays time, previous-best comparison, all three stable mote slots, discovered abilities, unlock cards, completion percentage, and explicit Next/Replay/Map choices. `SettingsScreen` calls `DisplayService.set_fullscreen()`, `MusicDirector.apply_settings()`, replaces its `Localizer` after a language change, and rebuilds its VM after each successful setting save.

Create the registry boundary in `windsprig/screens/factory.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping

from windsprig.screens.base import Screen, ScreenFactory, ScreenId


class ProductScreenFactory(ScreenFactory):
    def __init__(
        self,
        builders: Mapping[ScreenId, Callable[[], Screen]],
        context: ProductScreenContext,
    ) -> None:
        required: set[ScreenId] = {
            "boot", "title", "profile", "hub", "world_map", "stage_intro", "playing",
            "paused", "results", "defeat", "settings", "controls", "credits", "recovery",
        }
        missing = required - set(builders)
        extra = set(builders) - required
        if missing or extra:
            raise ValueError(f"screen registry mismatch; missing={sorted(missing)} extra={sorted(extra)}")
        self._builders = dict(builders)
        self.context = context

    @property
    def registered_ids(self) -> tuple[ScreenId, ...]:
        return tuple(sorted(self._builders))

    def create(self, screen_id: ScreenId) -> Screen:
        return self._builders[screen_id]()
```

Create `windsprig/bootstrap.py` with this public composition signature:

```python
def create_product_screen_factory(
    config: GameConfig,
    services: PlatformServices,
    now_utc: Callable[[], datetime],
) -> ProductScreenFactory:
    catalog = load_catalog_bundle(config.content_dir)
    assets = AssetCatalog.load_required(config.asset_dir)
    save_service = SaveManager(services.storage, migration_catalog(catalog), now_utc)
    load_result = save_service.load()
    localizer = Localizer.load(config.locale_dir, load_result.data.settings.language)
    music = MusicDirector(services.audio, load_music_cues(config.audio_dir))
    context = ProductScreenContext(
        config=config,
        services=services,
        catalog=catalog,
        assets=assets,
        save_service=save_service,
        save_data=load_result.data,
        save_notice=load_result.notice,
        localizer=localizer,
        music=music,
    )
    return ProductScreenFactory(build_screen_registry(context), context)
```

`ProductScreenContext` is a frozen dataclass containing exactly the named fields. `build_screen_registry(context)` returns all 14 required builders; each lambda constructs the concrete class named by its screen ID and shares the same context services/save/catalog/assets/localizer/music objects. No builder may construct a second `SaveManager`, `ActiveRoster`, audio service, or catalog.

Replace `create_foundation_screen_factory` with `create_product_screen_factory` in both native and web entry points. Both entries pass the same `GameConfig`, their platform-specific `PlatformServices`, and a UTC clock callback into the product factory before constructing `GameApp`. After this commit, `rg -n "FoundationScreen|create_foundation_screen_factory" windsprig web` must return no matches; delete `windsprig/screens/foundation.py` after its remaining behavior is covered by the concrete screen tests.

- [ ] **Step 6: Verify settings persistence and presentation flow**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/unit/meta/test_settings_models.py tests/integration/test_presentation_flow.py -q`

Expected: `8 passed`.

Run: `python -m pytest tests/unit/meta tests/integration/test_progression_flow.py tests/integration/test_presentation_flow.py -q`

Expected: all selected tests pass with zero warnings.

- [ ] **Step 7: Commit concrete campaign screens and settings**

```powershell
git add windsprig/bootstrap.py windsprig/__main__.py web/main.py windsprig/screens windsprig/meta/presentation_models.py tests/unit/meta/test_settings_models.py tests/integration/test_presentation_flow.py
git add -u windsprig/screens/foundation.py
git commit -m "feat: add campaign progression and settings screens"
```

---

### Task 10: Full-catalog, visual, accessibility, provenance, and release-gate evidence

**Files:**
- Extend: `tools/validate_content.py`
- Create: `tools/update_visual_baselines.py`
- Create: `tests/visual/conftest.py`
- Create: `tests/visual/test_screens.py`
- Create: `tests/visual/test_worlds.py`
- Create: `tests/visual/test_bosses.py`
- Create: `tests/visual/baselines/*.json` (39 approved cases)
- Extend: `tests/integration/test_campaign_catalog.py`
- Create: `tests/integration/test_full_catalog_render.py`

**Interfaces:**
- Consumes: every generated content/art/audio/font artifact and every VM/renderer from Tasks 1–9.
- Produces: stable `VisualFingerprint`, `fingerprint()`, `assert_perceptually_equal()`, 39 reviewed baseline JSON records, a 30-stage smoke-render test, and the authoritative validation summary consumed by distribution/release automation.

- [ ] **Step 1: Write failing full-catalog and visual-manifest tests**

```python
# append to tests/integration/test_campaign_catalog.py
def test_every_authored_reference_resolves_and_every_stage_has_safe_metadata() -> None:
    bundle = load_catalog_bundle(Path("windsprig/content"))
    for stage in bundle.campaign.stages.values():
        assert len(stage.player_spawns) == 4
        assert all(0 <= x < stage.width_tiles and 0 <= y < stage.height_tiles for x,y in stage.solids)
        assert all(mote.route in {"main","optional","mastery"} for mote in stage.motes)
        assert stage.navigation.start == "start"
        assert stage.navigation.goal == "goal"
        assert stage.target_time_ms in range(120000,360001)


# tests/integration/test_full_catalog_render.py
from pathlib import Path
import pygame

from windsprig.content.loader import load_asset_manifest, load_catalog_bundle
from windsprig.render.assets import AssetCatalog
from tests.helpers.presentation import build_catalog_snapshot, build_renderer


def test_all_thirty_stages_render_three_frames_without_missing_assets() -> None:
    pygame.init()
    canvas = pygame.Surface((1280,720))
    content = Path("windsprig/content")
    bundle = load_catalog_bundle(content)
    assets = AssetCatalog.load(Path("assets"),load_asset_manifest(content/"assets.json"))
    renderer = build_renderer(assets)
    for stage in bundle.campaign.stages.values():
        snapshot,camera,hud = build_catalog_snapshot(stage,bundle)
        for _ in range(3):
            renderer.render(canvas,stage,snapshot,camera,hud,empty_effect_frame(),16)
        assert canvas.get_bounding_rect().width == 1280
```

```python
# tests/visual/test_screens.py
from tests.visual.conftest import assert_case

SCREEN_CASES = (
    "title.en","profile.en","profile.ko","map.sunleaf","results.en",
    "results.ko","settings.en","settings.ko","hud.solo","hud.coop4",
    "hud.reduced_motion","hud.muted","letterbox.1280x720",
    "letterbox.1440x900","letterbox.1920x1080",
)


def test_screen_fingerprints(visual_harness) -> None:
    for case_id in SCREEN_CASES:
        assert_case(visual_harness,case_id)
```

```python
# tests/visual/test_worlds.py
from tests.visual.conftest import assert_case

WORLD_CASES = tuple(
    f"world.{world_id}"
    for world_id in ("world_1","world_2","world_3","world_4","world_5","world_6")
)


def test_world_fingerprints(visual_harness) -> None:
    for case_id in WORLD_CASES:
        assert_case(visual_harness,case_id)


# tests/visual/test_bosses.py
from tests.visual.conftest import assert_case

BOSS_CASES = tuple(
    f"boss.{boss_id}.p{phase}"
    for boss_id in ("rootjaw","crucible_crab","luma_eel","volt_roc","prism_warden","the_stillness")
    for phase in (1,2,3)
)


def test_boss_fingerprints(visual_harness) -> None:
    for case_id in BOSS_CASES:
        assert_case(visual_harness,case_id)
```

- [ ] **Step 2: Run the new gates and confirm absent baselines fail**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/integration/test_full_catalog_render.py tests/visual -q`

Expected: the 30-stage render test passes after Tasks 1–9, while visual tests fail with `missing approved baseline` for 39 case IDs.

- [ ] **Step 3: Implement deterministic perceptual fingerprints**

```python
# tests/visual/conftest.py
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import pygame
import pytest


@dataclass(frozen=True, slots=True)
class VisualFingerprint:
    width: int
    height: int
    sample_width: int
    sample_height: int
    rgb: tuple[int, ...]


def fingerprint(surface: pygame.Surface) -> VisualFingerprint:
    sample = pygame.transform.smoothscale(surface,(64,36))
    rgb = tuple(pygame.image.tobytes(sample,"RGB"))
    return VisualFingerprint(surface.get_width(),surface.get_height(),64,36,rgb)


def assert_perceptually_equal(actual: VisualFingerprint, expected: VisualFingerprint) -> None:
    assert (actual.width,actual.height,actual.sample_width,actual.sample_height) == (
        expected.width,expected.height,expected.sample_width,expected.sample_height
    )
    differences = [abs(left-right) for left,right in zip(actual.rgb,expected.rgb,strict=True)]
    mean = sum(differences)/len(differences)
    assert mean <= 2.0, f"mean RGB delta {mean:.3f} exceeds 2.0"
    assert max(differences) <= 18, f"peak RGB delta {max(differences)} exceeds 18"


@pytest.fixture(scope="session")
def visual_harness():
    pygame.init()
    return build_visual_harness(seed=20260711,logical_size=(1280,720))


def assert_case(harness, case_id: str) -> None:
    surface = harness.render_case(case_id)
    actual = fingerprint(surface)
    path = Path("tests/visual/baselines")/f"{case_id}.json"
    if not path.is_file():
        raise AssertionError(f"missing approved baseline: {case_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = VisualFingerprint(
        payload["width"],payload["height"],payload["sample_width"],
        payload["sample_height"],tuple(payload["rgb"]),
    )
    assert_perceptually_equal(actual,expected)
```

`build_visual_harness()` uses the release catalog, `AssetCatalog`, fixed presentation seed 20260711, Noto Sans KR, and frozen factory snapshots. World cases use each world's stage 3 at frame 180 and camera x equal to 35% of stage width. Boss cases use the boss stage, centered arena camera, phase HP ratios 0.90/0.55/0.20, and `BossAttackTelegraphed` at half its authored telegraph duration. Screen/HUD cases use their complete English/Korean VMs, four distinct slot icon/pattern/color tokens, and the exact accessibility/audio states named by each case ID.

- [ ] **Step 4: Implement explicit baseline approval**

```python
# tools/update_visual_baselines.py
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from tests.visual.conftest import fingerprint
from tests.helpers.presentation import build_visual_harness
from tests.visual.test_screens import SCREEN_CASES
from tests.visual.test_worlds import WORLD_CASES
from tests.visual.test_bosses import BOSS_CASES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    if not args.approve:
        print("Refusing to change reviewed baselines without --approve")
        return 2
    harness = build_visual_harness(seed=20260711,logical_size=(1280,720))
    cases = SCREEN_CASES+WORLD_CASES+BOSS_CASES
    root = Path("tests/visual/baselines")
    root.mkdir(parents=True,exist_ok=True)
    for case_id in cases:
        result = asdict(fingerprint(harness.render_case(case_id)))
        result["rgb"] = list(result["rgb"])
        (root/f"{case_id}.json").write_text(
            json.dumps(result,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8"
        )
    print(f"approved {len(cases)} visual baselines at seed 20260711")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Review rendered cases and approve all 39 baselines**

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tools/update_visual_baselines.py --approve`

Expected: `approved 39 visual baselines at seed 20260711`.

Inspect the rendered PNG review sheet emitted by the harness at `artifacts/visual-review/contact-sheet.png`; verify original silhouettes, no clipping, English/Korean fit, 4.5:1 body/HUD and 3:1 decorative contrast, icon/pattern redundancy, all boss telegraphs, four-player HUD identity, muted indicator, and reduced-motion readability. Delete the ignored `artifacts/visual-review` directory after review; commit only fingerprint JSON.

- [ ] **Step 6: Extend authoritative validation with exact release counts and policy scans**

`validate_bundle()` and `tools/validate_content.py --all` must now enforce:

```python
EXPECTED = {
    "worlds":6, "stages":30, "bosses":6, "motes":90, "locales":2,
    "music":28, "sfx":29, "duplicate_layouts":0,
}
FORBIDDEN_PUBLIC_TOKENS = (
    "kirby","nintendo","return to dream land","energy sphere",
    "copy ability","inhale","ultra sword",
)
REQUIRED_ART = {
    "player_states":14, "player_frames":56, "enemy_atlases":18,
    "boss_atlases":6, "world_sets":6, "png_files":52,
}
```

The all-mode scan compares the exact counts, verifies 90 mote IDs match `mote.<world>.<01-05>.<a-c>`, confirms 30 distinct full-layout signatures, checks all six abilities have enemy sources, proves navigation metadata reaches goal/checkpoints/motes, requires every boss attack telegraph to be at least 600 ms with marker and cue, verifies 52 art and 57 audio hashes/provenance entries, checks both locale key/placeholder sets, renders the Hangul release sample, scans player-facing JSON/Markdown/asset IDs for forbidden public tokens, and reports each failure with a stable code/path.

- [ ] **Step 7: Run the complete subproject evidence gate**

Run: `python tools/generate_campaign.py --check && python tools/generate_locales.py --check && python tools/fetch_font.py --check && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tools/generate_art.py --check && python tools/generate_audio.py --check`

Expected: every generator reports its exact current inventory and exits 0 with no file changes.

Run: `python tools/validate_content.py --all`

Expected: `OK: 6 worlds, 30 stages, 6 bosses, 90 motes, 2 locales, 28 music cues, 29 sfx cues, 0 duplicate layouts`.

Run: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/unit/content tests/unit/meta tests/unit/render tests/unit/audio tests/integration/test_campaign_catalog.py tests/integration/test_boss_catalog.py tests/integration/test_progression_flow.py tests/integration/test_presentation_flow.py tests/integration/test_full_catalog_render.py tests/visual -q`

Expected: all selected tests pass with no missing baselines, missing mandatory assets, unhandled warnings, or skipped release cases.

Run: `python -m ruff check windsprig tools tests && python -m mypy windsprig`

Expected: both commands exit 0 with no diagnostics.

Run: `python -m pytest -q --cov=windsprig --cov-branch --cov-report=term-missing --cov-fail-under=85`

Expected: the full suite passes and total production branch coverage is at least 85%.

- [ ] **Step 8: Commit full-catalog and visual evidence**

```powershell
git add tools/validate_content.py tools/update_visual_baselines.py tests/integration/test_campaign_catalog.py tests/integration/test_full_catalog_render.py tests/visual
git commit -m "test: verify complete campaign presentation catalog"
```

---

## Plan-Wide Acceptance Matrix

| Requirement | Implementation task | Current evidence command |
|---|---:|---|
| 30 distinct stages / six worlds / 90 motes | 2 | `python tools/validate_content.py --all` |
| Six unique multi-phase bosses | 3 | `python -m pytest tests/unit/content/test_bosses.py tests/integration/test_boss_catalog.py -q` |
| Stable, non-inflating progression and completion | 4 | `python -m pytest tests/unit/meta/test_completion.py tests/integration/test_progression_flow.py -q` |
| Profile/world-map/results view models | 4, 9 | `python -m pytest tests/unit/meta tests/integration/test_presentation_flow.py -q` |
| English/Korean and OFL font | 5 | `python -m pytest tests/unit/content/test_localization.py -q` |
| Original procedural/vector art and provenance | 6 | `python tools/generate_art.py --check` |
| Animation, particles, camera, logical display, HUD | 7 | `python -m pytest tests/unit/render -q` |
| Original music/SFX and provenance | 8 | `python tools/generate_audio.py --check` |
| Settings, controls, and accessibility | 9 | `python -m pytest tests/unit/meta/test_settings_models.py -q` |
| Visual and full-catalog coverage | 10 | `python -m pytest tests/integration/test_full_catalog_render.py tests/visual -q` |

## Execution Handoff

Implement Tasks 1–10 in order. Use `superpowers:subagent-driven-development` for a fresh implementation agent and two-stage review per task, or `superpowers:executing-plans` for checkpointed inline batches. Do not start Task 2 before Task 1's schema/validator tests pass, and do not approve Task 10 baselines until a human has inspected the 39-case contact sheet.
