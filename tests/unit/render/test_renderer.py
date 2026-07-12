"""Snapshot-only campaign renderer coverage across the complete release catalog."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from pathlib import Path

import pygame
import pytest

import windsprig.render as render_package
from windsprig.content import load_catalog_bundle
from windsprig.content.loader import load_asset_manifest
from windsprig.content.models import CatalogBundle, StageSpec
from windsprig.core.events import GameEvent
from windsprig.gameplay.snapshot import (
    AttackView,
    BossView,
    CameraTargetView,
    CheckpointView,
    EchoPickupView,
    EnemyView,
    GoalGatherView,
    InteractionView,
    PlayerView,
    StageOutcome,
    StageSnapshot,
)
from windsprig.input.roster import SLOT_VISUALS, ActivePlayer, DeviceRef
from windsprig.localization import Localizer
from windsprig.meta.save_models import AccessibilitySettings
from windsprig.platform.services import AudioStatus
from windsprig.render.animation import AnimationCursor, build_default_animation_bank
from windsprig.render.assets import AssetCatalog, MissingAssetError
from windsprig.render.camera import CameraView
from windsprig.render.effects import EffectFrame, EffectsDirector, Flash, Particle, Shake, empty_effect_frame
from windsprig.render.hud import HudViewModel, build_hud_view
from windsprig.render.renderer import RENDER_LAYER_ORDER, StageRenderer

ROOT = Path(__file__).resolve().parents[3]
CONTENT = ROOT / "windsprig/content"
PLAYER_STATES = (
    "Idle",
    "Run",
    "Jump",
    "Fall",
    "Hover",
    "Draw",
    "Captured",
    "Harmonize",
    "Attack",
    "Guard",
    "Dodge",
    "Hurt",
    "Dead",
    "Victory",
)
ABILITY_ATTACKS = (
    ("melee_arc", "bloomblade_arc_1"),
    ("melee_arc", "bloomblade_arc_2"),
    ("melee_arc", "bloomblade_arc_3"),
    ("charged_ember", "cinder_ember"),
    ("charged_ember", "cinder_ember_charged"),
    ("burn_zone", "cinder_burn_zone"),
    ("chain_pulse", "voltsong_chain_pulse"),
    ("boomerang", "galehook_boomerang"),
    ("ground_slam", "stoneheart_ground_slam"),
    ("screen_tempest", "tempest_screen"),
    ("launched_enemy", "wind_launch"),
)


@pytest.fixture(scope="module")
def bundle() -> CatalogBundle:
    return load_catalog_bundle(CONTENT)


@pytest.fixture(scope="module")
def assets() -> AssetCatalog:
    return AssetCatalog.load(ROOT / "assets", load_asset_manifest(CONTENT / "assets.json"))


def _active_player(slot: int = 1) -> ActivePlayer:
    color, icon = SLOT_VISUALS[slot]
    return ActivePlayer(
        slot,
        DeviceRef("keyboard", f"render-kb-{slot}", f"Renderer Keyboard {slot}"),
        color,
        icon,
        slot == 1,
    )


def _player(state: str = "Idle", *, entity_id: int = 101, slot: int = 1) -> PlayerView:
    return PlayerView(
        entity_id=entity_id,
        slot=slot,
        x=360.0,
        y=500.0,
        width=42,
        height=58,
        facing=1,
        actor_state=state,
        hp=4,
        maximum_hp=5,
        lives_remaining=3,
        ability_id="bloomblade",
        ability_meter=60,
        ability_charge_ms=0,
        guard_active=state == "Guard",
        dodge_active=state == "Dodge",
        invulnerable=state in {"Dodge", "Hurt"},
        hover_remaining_ms=640,
        hover_max_ms=850,
        captured_ability_id="cinder" if state == "Captured" else None,
        captured_visual_id="cinderling" if state == "Captured" else None,
    )


def _snapshot(
    stage: StageSpec,
    *,
    players: tuple[PlayerView, ...] = (),
    enemies: tuple[EnemyView, ...] = (),
    bosses: tuple[BossView, ...] = (),
    attacks: tuple[AttackView, ...] = (),
    echo_pickups: tuple[EchoPickupView, ...] = (),
    interactions: tuple[InteractionView, ...] = (),
) -> StageSnapshot:
    actual_players = players or (_player(),)
    slots = tuple(sorted(player.slot for player in actual_players))
    checkpoints = tuple(
        CheckpointView(
            checkpoint.checkpoint_id,
            checkpoint.tile_x * stage.tile_size,
            checkpoint.tile_y * stage.tile_size,
            index == 0,
        )
        for index, checkpoint in enumerate(stage.checkpoints[:2])
    )
    return StageSnapshot(
        frame_index=120,
        elapsed_ms=1_920,
        stage_id=stage.stage_id,
        world_id=stage.world_id,
        node_id=stage.node_id,
        outcome=StageOutcome.RUNNING,
        players=actual_players,
        enemies=enemies,
        attacks=attacks,
        echo_pickups=echo_pickups,
        interactions=interactions,
        checkpoints=checkpoints,
        goal_gather=GoalGatherView(
            stage.goal_tile[0] * stage.tile_size,
            stage.goal_tile[1] * stage.tile_size,
            (),
            slots,
            1,
            False,
            0,
        ),
        camera_targets=tuple(
            CameraTargetView(player.entity_id, player.slot, player.x, player.y, 1.0, True) for player in actual_players
        ),
        bosses=bosses,
        collected_mote_ids=(),
    )


def _hud(snapshot: StageSnapshot, stage: StageSpec, language: str = "en") -> HudViewModel:
    active = tuple(_active_player(player.slot) for player in snapshot.players)
    return build_hud_view(
        snapshot,
        stage,
        active,
        CameraView(0, 0, 0, 0, 0, ()),
        AudioStatus(True, False),
        "saved",
        Localizer.load(CONTENT, language),  # type: ignore[arg-type]
    )


def _renderer(assets: AssetCatalog, language: str = "en") -> StageRenderer:
    return StageRenderer(
        assets,
        build_default_animation_bank(),
        Localizer.load(CONTENT, language),  # type: ignore[arg-type]
    )


def _render(
    renderer: StageRenderer,
    stage: StageSpec,
    snapshot: StageSnapshot,
    *,
    hud: HudViewModel | None = None,
    effects: EffectFrame | None = None,
    dt_ms: int = 16,
) -> pygame.Surface:
    canvas = pygame.Surface((1280, 720), pygame.SRCALPHA)
    renderer.render(
        canvas,
        stage,
        snapshot,
        CameraView(0, 0, 0, 0, 0, ()),
        hud or _hud(snapshot, stage),
        effects or empty_effect_frame(),
        dt_ms,
    )
    return canvas


def _hash(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA", False)).hexdigest()


def test_renderer_uses_the_exact_owned_layer_order(
    assets: AssetCatalog,
    bundle: CatalogBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert RENDER_LAYER_ORDER == (
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
    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    renderer = _renderer(assets)
    called: list[str] = []
    for layer in RENDER_LAYER_ORDER:

        def record(*_arguments: object, owned_layer: str = layer) -> None:
            called.append(owned_layer)

        monkeypatch.setattr(renderer, f"_draw_{layer}", record)

    _render(renderer, stage, snapshot)

    assert tuple(called) == RENDER_LAYER_ORDER


def test_render_package_exports_the_public_presentation_contracts() -> None:
    expected = {
        "AnimationBank",
        "AnimationClip",
        "AnimationCursor",
        "AssetCatalog",
        "CameraController",
        "CameraView",
        "EffectFrame",
        "EffectsDirector",
        "HudViewModel",
        "Letterbox",
        "MissingAssetError",
        "StageRenderer",
        "build_default_animation_bank",
        "build_hud_view",
        "compute_letterbox",
        "contrast_ratio",
    }

    assert expected <= set(render_package.__all__)
    assert all(hasattr(render_package, name) for name in expected)


def test_renderer_advances_each_entity_once_and_removes_stale_cursors(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_5"]
    boss_spec = bundle.bosses["rootjaw"]
    player = _player("Run")
    enemy = EnemyView(201, "breezeling", 520, 500, 48, 48, -1, "Run", 3, 3, "galehook", None)
    boss = BossView(
        301,
        "rootjaw",
        boss_spec.phases[0].phase_id,
        760,
        450,
        128,
        128,
        -1,
        "Attack",
        boss_spec.max_hp,
        boss_spec.max_hp,
        boss_spec.phases[0].attacks[0].attack_id,
        400,
        boss_spec.phases[0].vulnerability,
    )
    snapshot = _snapshot(stage, players=(player,), enemies=(enemy,), bosses=(boss,))
    renderer = _renderer(assets)
    before = snapshot

    _render(renderer, stage, snapshot, dt_ms=100)

    assert snapshot == before
    assert set(renderer.cursors) == {("player", 101), ("enemy", 201), ("boss", 301)}
    run = build_default_animation_bank().clip_for("Run")
    attack = build_default_animation_bank().clip_for("Attack")
    assert renderer.cursors[("player", 101)] == AnimationCursor.start(run).advance(100)[0]
    assert renderer.cursors[("enemy", 201)] == AnimationCursor.start(run).advance(100)[0]
    assert renderer.cursors[("boss", 301)] == AnimationCursor.start(attack).advance(100)[0]

    without_stale = replace(snapshot, enemies=(), bosses=())
    _render(renderer, stage, without_stale, hud=_hud(without_stale, stage), dt_ms=0)
    assert set(renderer.cursors) == {("player", 101)}


def test_all_player_states_render_to_distinct_release_frames(assets: AssetCatalog, bundle: CatalogBundle) -> None:
    stage = bundle.campaign.stages["world_1_stage_1"]
    hashes: set[str] = set()
    for state in PLAYER_STATES:
        snapshot = _snapshot(stage, players=(_player(state),))
        hashes.add(_hash(_render(_renderer(assets), stage, snapshot)))

    assert len(hashes) == len(PLAYER_STATES)


def test_all_six_worlds_and_eighteen_enemy_assets_render_without_fallback(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    world_hashes: set[str] = set()
    for world_index in range(1, 7):
        stage = bundle.campaign.stages[f"world_{world_index}_stage_1"]
        snapshot = _snapshot(stage)
        world_hashes.add(_hash(_render(_renderer(assets), stage, snapshot)))
    assert len(world_hashes) == 6

    enemy_kinds = sorted({spawn.kind for stage in bundle.campaign.stages.values() for spawn in stage.enemy_spawns})
    assert len(enemy_kinds) == 18
    stage = bundle.campaign.stages["world_1_stage_1"]
    enemy_hashes: set[str] = set()
    for index, enemy_kind in enumerate(enemy_kinds, start=1):
        enemy = EnemyView(index + 200, enemy_kind, 520, 500, 48, 48, -1, "Run", 3, 3, None, None)
        snapshot = _snapshot(stage, enemies=(enemy,))
        enemy_hashes.add(_hash(_render(_renderer(assets), stage, snapshot)))
    assert len(enemy_hashes) == 18


def test_all_six_bosses_and_eighteen_phase_rows_render_with_telegraphs(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    hashes: set[str] = set()
    for boss_spec in bundle.bosses.values():
        stage = next(stage for stage in bundle.campaign.stages.values() if stage.boss_id == boss_spec.boss_id)
        for phase_index, phase in enumerate(boss_spec.phases):
            boss = BossView(
                entity_id=500 + phase_index,
                boss_id=boss_spec.boss_id,
                phase_id=phase.phase_id,
                x=700,
                y=430,
                width=128,
                height=128,
                facing=-1,
                actor_state="Attack",
                hp=max(1, round(boss_spec.max_hp * phase.enter_at_hp_ratio)),
                maximum_hp=boss_spec.max_hp,
                telegraph_id=phase.attacks[0].attack_id,
                telegraph_remaining_ms=phase.attacks[0].telegraph_ms // 2,
                vulnerability_state=phase.vulnerability,
            )
            snapshot = _snapshot(stage, bosses=(boss,))
            hashes.add(_hash(_render(_renderer(assets), stage, snapshot, hud=_hud(snapshot, stage))))

    assert len(hashes) == 18


def test_every_interaction_attack_and_echo_mapping_renders(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    interactions = {
        interaction.kind: stage for stage in bundle.campaign.stages.values() for interaction in stage.interactions
    }
    # Stoneheart can expose this runtime state even though no authored stage starts broken.
    interactions.setdefault("breakable_floor", bundle.campaign.stages["world_6_stage_1"])
    assert set(interactions) == {
        "gust_lift",
        "breakable",
        "conveyor",
        "heat_vent",
        "timed_shutter",
        "current",
        "buoyant_pod",
        "falling_water",
        "rail",
        "conductor",
        "rotating_tower",
        "mirror",
        "color_beam",
        "gravity_bloom",
        "silence_field",
        "ability_lock",
        "breakable_floor",
        "switch",
    }
    for index, (kind, stage) in enumerate(sorted(interactions.items()), start=1):
        interaction = InteractionView(index, f"qa.{kind}", kind, "energized", 520, 450, 64, 96)
        snapshot = _snapshot(stage, interactions=(interaction,))
        _render(_renderer(assets), stage, snapshot)

    stage = bundle.campaign.stages["world_1_stage_1"]
    boss_attacks = tuple(
        (attack.attack_id, attack.attack_id)
        for boss in bundle.bosses.values()
        for phase in boss.phases
        for attack in phase.attacks
    )
    assert len(boss_attacks) == 36
    for index, (attack_kind, visual_id) in enumerate((*ABILITY_ATTACKS, *boss_attacks), start=1):
        attack = AttackView(index + 800, 101, attack_kind, visual_id, 520, 460, 80, 48, 1, 500)
        snapshot = _snapshot(stage, attacks=(attack,))
        _render(_renderer(assets), stage, snapshot)

    for index, ability_id in enumerate(("bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest")):
        echo = EchoPickupView(900 + index, ability_id, 520, 460)
        snapshot = _snapshot(stage, echo_pickups=(echo,))
        _render(_renderer(assets), stage, snapshot)


def test_release_renderer_rejects_unknown_assets_and_visual_tokens(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_1"]
    unknown_enemy = EnemyView(201, "unknown_enemy", 520, 500, 48, 48, 1, "Idle", 3, 3, None, None)
    unknown_attack = AttackView(301, 101, "mystery", "mystery_visual", 520, 460, 40, 40, 1, 100)
    invalid_owner = AttackView(302, True, "melee_arc", "bloomblade_arc_1", 520, 460, 40, 40, 1, 100)

    with pytest.raises(MissingAssetError, match="enemy.unknown_enemy"):
        snapshot = _snapshot(stage, enemies=(unknown_enemy,))
        _render(_renderer(assets), stage, snapshot)
    with pytest.raises(ValueError, match="attack visual"):
        snapshot = _snapshot(stage, attacks=(unknown_attack,))
        _render(_renderer(assets), stage, snapshot)
    with pytest.raises(TypeError, match="owner"):
        snapshot = _snapshot(stage, attacks=(invalid_owner,))
        _render(_renderer(assets), stage, snapshot)


def test_renderer_rejects_nonlogical_canvas_and_invalid_delta(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    renderer = _renderer(assets)
    arguments = (
        stage,
        snapshot,
        CameraView(0, 0, 0, 0, 0, ()),
        _hud(snapshot, stage),
        empty_effect_frame(),
    )

    with pytest.raises(ValueError, match="1280x720"):
        renderer.render(pygame.Surface((640, 360)), *arguments, 16)
    with pytest.raises(TypeError, match="render delta"):
        renderer.render(pygame.Surface((1280, 720)), *arguments, True)


def test_render_modules_have_no_ecs_runtime_or_system_imports() -> None:
    forbidden = (
        "windsprig.core.ecs",
        "windsprig.gameplay.components",
        "windsprig.gameplay.runtime",
        "windsprig.gameplay.systems",
    )
    for path in sorted((ROOT / "windsprig/render").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = tuple(
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        assert not any(module.startswith(forbidden) for module in imported), (path.name, imported)


def test_renderer_validates_constructor_and_public_render_boundary(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    animations = build_default_animation_bank()
    tr = Localizer.load(CONTENT, "en")
    with pytest.raises(TypeError, match="assets"):
        StageRenderer(object(), animations, tr)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="animations"):
        StageRenderer(assets, object(), tr)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Localizer"):
        StageRenderer(assets, animations, object())  # type: ignore[arg-type]

    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    hud = _hud(snapshot, stage)
    renderer = _renderer(assets)
    valid: list[object] = [
        pygame.Surface((1280, 720)),
        stage,
        snapshot,
        CameraView(0, 0, 0, 0, 0, ()),
        hud,
        empty_effect_frame(),
        16,
    ]
    for index in range(6):
        invalid = list(valid)
        invalid[index] = object()
        with pytest.raises(TypeError):
            renderer.render(*invalid)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="identity"):
        renderer.render(
            valid[0],  # type: ignore[arg-type]
            stage,
            replace(snapshot, stage_id="other"),
            *valid[3:],  # type: ignore[arg-type]
        )
    unsupported_stage = replace(stage, world_id="world_7")
    with pytest.raises(ValueError, match="world ID"):
        renderer.render(
            valid[0],  # type: ignore[arg-type]
            unsupported_stage,
            replace(snapshot, world_id="world_7"),
            *valid[3:],  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="tile size"):
        renderer.render(
            valid[0],  # type: ignore[arg-type]
            replace(stage, tile_size=True),  # type: ignore[arg-type]
            snapshot,
            *valid[3:],  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "field",
    ["players", "enemies", "attacks", "echo_pickups", "interactions", "checkpoints", "camera_targets", "bosses"],
)
def test_renderer_rejects_malformed_snapshot_collections(
    assets: AssetCatalog,
    bundle: CatalogBundle,
    field: str,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    malformed = replace(snapshot, **{field: [*getattr(snapshot, field)]})

    with pytest.raises((TypeError, ValueError), match=field.replace("_", " ")):
        _renderer(assets).render(
            pygame.Surface((1280, 720)),
            stage,
            malformed,
            CameraView(0, 0, 0, 0, 0, ()),
            _hud(snapshot, stage),
            empty_effect_frame(),
            16,
        )


def test_renderer_rejects_duplicate_invalid_entity_and_hud_slot_facts(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    renderer = _renderer(assets)
    common = (
        CameraView(0, 0, 0, 0, 0, ()),
        _hud(snapshot, stage),
        empty_effect_frame(),
        16,
    )
    with pytest.raises(ValueError, match="positive"):
        renderer.render(
            pygame.Surface((1280, 720)),
            stage,
            replace(snapshot, players=(replace(snapshot.players[0], entity_id=0),)),
            *common,
        )
    duplicate_enemy = EnemyView(101, "breezeling", 500, 500, 48, 48, 1, "Idle", 2, 2, None, None)
    with pytest.raises(ValueError, match="globally unique"):
        renderer.render(
            pygame.Surface((1280, 720)),
            stage,
            replace(snapshot, enemies=(duplicate_enemy,)),
            *common,
        )
    two_player_snapshot = _snapshot(stage, players=(_player(slot=1), _player(entity_id=102, slot=2)))
    with pytest.raises(ValueError, match="HUD player slots"):
        renderer.render(
            pygame.Surface((1280, 720)),
            stage,
            snapshot,
            CameraView(0, 0, 0, 0, 0, ()),
            _hud(two_player_snapshot, stage),
            empty_effect_frame(),
            16,
        )


def test_renderer_draws_every_effect_family_and_complete_accessible_hud_state(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_3_stage_3"]
    players = tuple(
        replace(
            _player(("Guard", "Dodge", "Captured", "Hurt")[slot - 1], entity_id=100 + slot, slot=slot),
            x=220.0 + slot * 120,
            ability_id=("bloomblade", "cinder", "voltsong", "galehook")[slot - 1],
            ability_meter=0 if slot == 1 else 60,
            captured_ability_id="stoneheart" if slot == 3 else None,
            captured_visual_id="moonjelly" if slot == 3 else None,
        )
        for slot in range(1, 5)
    )
    snapshot = _snapshot(stage, players=players)
    snapshot = replace(
        snapshot,
        goal_gather=replace(
            snapshot.goal_gather,
            at_goal_slots=(1,),
            required_slots=(1, 2, 3, 4),
            leader_slot=1,
            leader_confirmed=True,
            countdown_remaining_ms=1_500,
        ),
    )
    camera = CameraView(0, 0, 0, 0, 0, (4,))
    hud = build_hud_view(
        snapshot,
        stage,
        tuple(_active_player(slot) for slot in range(1, 5)),
        camera,
        AudioStatus(False, True, "audio_init_failed"),
        "retry_required",
        Localizer.load(CONTENT, "en"),
    )
    kinds = (
        "impact",
        "afterimage",
        "wind_ribbon",
        "leaf",
        "streak",
        "spark",
        "echo",
        "shard",
        "mote",
        "paper",
        "confetti",
    )
    particles = tuple(
        Particle(kind, 500 + index * 12, 450, 20, -10, 200, f"pattern.{kind}") for index, kind in enumerate(kinds)
    )
    effects = EffectFrame(particles, Shake(4, 80), Flash(640, 420, 28, "pattern.hit", 90))

    rendered = _render(_renderer(assets), stage, snapshot, hud=hud, effects=effects)

    assert rendered.get_bounding_rect().size == (1280, 720)
    unknown = EffectFrame((Particle("unknown", 20, 20, 0, 0, 100, "pattern.unknown"),), None, None)
    with pytest.raises(ValueError, match="particle kind"):
        _render(_renderer(assets), stage, snapshot, hud=hud, effects=unknown)


def test_renderer_consumes_ability_icons_effect_color_life_and_flash_pattern(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    renderer = _renderer(assets)
    hud = _hud(snapshot, stage)
    base_player = replace(hud.players[0], ability_label="Echo")

    bloom = pygame.Surface((310, 130), pygame.SRCALPHA)
    cinder = pygame.Surface((310, 130), pygame.SRCALPHA)
    renderer._draw_player_hud(bloom, replace(base_player, ability_icon="bloomblade"), bloom.get_rect())
    renderer._draw_player_hud(cinder, replace(base_player, ability_icon="cinder"), cinder.get_rect())
    assert _hash(bloom.subsurface((44, 36, 34, 34))) != _hash(cinder.subsurface((44, 36, 34, 34)))

    camera = CameraView(0, 0, 0, 0, 0, ())
    short = pygame.Surface((220, 180), pygame.SRCALPHA)
    long = pygame.Surface((220, 180), pygame.SRCALPHA)
    alternate = pygame.Surface((220, 180), pygame.SRCALPHA)
    renderer._draw_effects(
        short,
        EffectFrame(
            (Particle("mote", 80, 90, 0, 0, 30, "pattern.mote"),), None, Flash(140, 90, 28, "pattern.mote", 30)
        ),
        camera,
    )
    renderer._draw_effects(
        long,
        EffectFrame(
            (Particle("mote", 80, 90, 0, 0, 240, "pattern.mote"),), None, Flash(140, 90, 28, "pattern.mote", 90)
        ),
        camera,
    )
    renderer._draw_effects(
        alternate,
        EffectFrame(
            (Particle("mote", 80, 90, 0, 0, 240, "pattern.harmonize"),),
            None,
            Flash(140, 90, 28, "pattern.harmonize", 90),
        ),
        camera,
    )

    assert _hash(short) != _hash(long)
    assert _hash(long) != _hash(alternate)


def test_reduced_motion_mote_and_harmonize_render_pixel_distinct(
    assets: AssetCatalog,
) -> None:
    settings = AccessibilitySettings(screen_shake=False, reduced_motion=True)
    event_payload = {"x": 100.0, "y": 100.0, "facing": 1}
    mote = EffectsDirector(seed=12).handle((GameEvent("MoteCollected", event_payload),), settings)
    equipped = EffectsDirector(seed=12).handle((GameEvent("AbilityEquipped", event_payload),), settings)
    renderer = _renderer(assets)
    camera = CameraView(0, 0, 0, 0, 0, ())
    mote_canvas = pygame.Surface((220, 220), pygame.SRCALPHA)
    equipped_canvas = pygame.Surface((220, 220), pygame.SRCALPHA)

    renderer._draw_effects(mote_canvas, mote, camera)
    renderer._draw_effects(equipped_canvas, equipped, camera)

    assert _hash(mote_canvas) != _hash(equipped_canvas)


def test_renderer_covers_interaction_states_captured_enemy_and_offscreen_entities(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_4_stage_2"]
    interactions = tuple(
        InteractionView(
            300 + index,
            f"qa.interaction.{index}",
            "conductor",
            state,
            240 + index * 100,
            480,
            72,
            88,
        )
        for index, state in enumerate(("idle", "energized", "activated", "broken"), start=1)
    ) + (InteractionView(399, "qa.offscreen", "rail", "idle", 9_000, 480, 72, 88),)
    enemies = (
        EnemyView(410, "coilbird", 760, 500, 48, 48, -1, "Run", 2, 3, None, 101),
        EnemyView(411, "railrunner", 9_000, 500, 48, 48, 1, "Run", 3, 3, None, None),
    )
    snapshot = _snapshot(
        stage,
        enemies=enemies,
        interactions=interactions,
        attacks=(AttackView(420, 101, "melee_arc", "bloomblade_arc_1", 9_000, 500, 60, 60, 1, 100),),
        echo_pickups=(EchoPickupView(430, "cinder", 9_000, 500),),
    )
    snapshot = replace(
        snapshot,
        checkpoints=(
            CheckpointView("qa.active", 200, 520, True),
            CheckpointView("qa.inactive", 300, 520, False),
        ),
        goal_gather=replace(snapshot.goal_gather, goal_x=1_000, goal_y=530),
    )

    _render(_renderer(assets), stage, snapshot)

    for field, value, message in (
        ("interactions", (replace(interactions[0], interaction_kind="unknown"),), "interaction kind"),
        ("interactions", (replace(interactions[0], interaction_state="unknown"),), "interaction state"),
        ("echo_pickups", (EchoPickupView(500, "unknown", 500, 500),), "echo ability"),
    ):
        invalid = replace(snapshot, **{field: value})
        with pytest.raises(ValueError, match=message):
            _render(_renderer(assets), stage, invalid, hud=_hud(invalid, stage))


def test_renderer_rejects_unknown_boss_phase_telegraph_and_vulnerability(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    stage = bundle.campaign.stages["world_1_stage_5"]
    spec = bundle.bosses["rootjaw"]
    base = BossView(
        800,
        "rootjaw",
        spec.phases[0].phase_id,
        700,
        420,
        128,
        128,
        1,
        "Idle",
        100,
        spec.max_hp,
        spec.phases[0].attacks[0].attack_id,
        300,
        spec.phases[0].vulnerability,
    )
    without_boss = _snapshot(stage)
    hud = _hud(without_boss, stage)
    for boss, message in (
        (replace(base, phase_id="rootjaw.unknown"), "phase ID"),
        (replace(base, telegraph_id="rootjaw.unknown"), "telegraph ID"),
        (replace(base, vulnerability_state="unknown"), "vulnerability"),  # type: ignore[arg-type]
    ):
        snapshot = replace(without_boss, bosses=(boss,))
        with pytest.raises(ValueError, match=message):
            _render(_renderer(assets), stage, snapshot, hud=hud)


def test_renderer_bounds_transformed_frame_cache_and_rejects_bad_hud_tokens(
    assets: AssetCatalog,
    bundle: CatalogBundle,
) -> None:
    renderer = _renderer(assets)
    first = renderer._scaled_frame("ui.icons", 0, (12, 12))
    assert renderer._scaled_frame("ui.icons", 0, (12, 12)) is first
    for size in range(13, 13 + renderer.MAX_SCALED_CACHE + 4):
        renderer._scaled_frame("ui.icons", 0, (size, size))
    assert len(renderer._scaled_frames) == renderer.MAX_SCALED_CACHE
    with pytest.raises(ValueError, match="width"):
        renderer._scaled_frame("ui.icons", 0, (0, 12))
    with pytest.raises(TypeError, match="flip"):
        renderer._scaled_frame("ui.icons", 0, (12, 12), flip_x=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="icon ID"):
        renderer._icon("unknown")

    stage = bundle.campaign.stages["world_1_stage_1"]
    snapshot = _snapshot(stage)
    hud = _hud(snapshot, stage)
    for player, message in (
        (replace(hud.players[0], color_token="unknown"), "color token"),
        (replace(hud.players[0], icon_token="unknown"), "icon token"),
        (replace(hud.players[0], pattern_token="unknown"), "pattern token"),
    ):
        invalid_hud = replace(hud, players=(player,))
        with pytest.raises(ValueError, match=message):
            _render(_renderer(assets), stage, snapshot, hud=invalid_hud)
    with pytest.raises(ValueError, match="meter ratio"):
        renderer._draw_meter(
            pygame.Surface((20, 20)), pygame.Rect(1, 1, 10, 4), float("nan"), (255, 255, 255), pattern="dots"
        )


def test_effects_input_sequence_remains_independent_of_renderer_state() -> None:
    settings = AccessibilitySettings(screen_shake=False, reduced_motion=True)
    event = GameEvent("AttackHit", {"x": 10.0, "y": 20.0, "facing": 1})
    assert EffectsDirector(seed=4).handle((event,), settings) == EffectsDirector(seed=4).handle((event,), settings)
