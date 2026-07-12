"""Deterministically validate whole-catalog semantic and release invariants."""

from __future__ import annotations

import math
import string
from collections.abc import Iterable
from pathlib import Path

from .loader import PUBLIC_ABILITY_IDS
from .models import (
    AssetManifest,
    CatalogBundle,
    LocaleCatalog,
    StageSpec,
    ValidationIssue,
    ValidationReport,
)

_EXPECTED_WORLDS = 6
_EXPECTED_STAGES = 30
_EXPECTED_BOSSES = 6
_EXPECTED_MOTES = 90
_EXPECTED_MUSIC = 28
_EXPECTED_SFX = 29


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message)


def _stable(issues: Iterable[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(issues, key=lambda item: (item.path, item.code, item.message)))


def _reference_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    campaign = bundle.campaign
    issues: list[ValidationIssue] = []
    node_ids = set(campaign.nodes)
    stage_references: dict[str, list[str]] = {}
    for world_id, nodes in campaign.worlds.items():
        for node in nodes:
            path = f"campaign.worlds.{world_id}.nodes.{node.node_id}"
            if node.world_id != world_id:
                issues.append(
                    _issue(
                        "world_mismatch",
                        f"{path}.world_id",
                        f"expected {world_id}, received {node.world_id}",
                    )
                )
            stage = campaign.stages.get(node.stage_id)
            if stage is None:
                issues.append(
                    _issue(
                        "missing_stage",
                        f"{path}.stage_id",
                        f"referenced stage does not exist: {node.stage_id}",
                    )
                )
            else:
                stage_references.setdefault(node.stage_id, []).append(node.node_id)
                if stage.node_id != node.node_id:
                    issues.append(
                        _issue(
                            "node_mismatch",
                            f"campaign.stages.{stage.stage_id}.node_id",
                            f"expected {node.node_id}, received {stage.node_id}",
                        )
                    )
                if stage.world_id != world_id:
                    issues.append(
                        _issue(
                            "world_mismatch",
                            f"campaign.stages.{stage.stage_id}.world_id",
                            f"expected {world_id}, received {stage.world_id}",
                        )
                    )
            for index, required_id in enumerate(node.requires):
                if required_id not in node_ids:
                    issues.append(
                        _issue(
                            "missing_required_node",
                            f"{path}.requires[{index}]",
                            f"required node does not exist: {required_id}",
                        )
                    )

    for stage_id, stage in campaign.stages.items():
        path = f"campaign.stages.{stage_id}"
        if stage.stage_id != stage_id:
            issues.append(
                _issue(
                    "stage_key_mismatch",
                    f"{path}.stage_id",
                    f"mapping key does not match {stage.stage_id}",
                )
            )
        references = stage_references.get(stage_id, [])
        if not references:
            issues.append(_issue("orphan_stage", path, "stage is not referenced by a world node"))
        elif len(references) > 1:
            issues.append(
                _issue(
                    "duplicate_stage_reference",
                    path,
                    f"stage is referenced by {len(references)} nodes",
                )
            )
    return issues


def _count_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    campaign = bundle.campaign
    issues: list[ValidationIssue] = []
    actual = {
        "world_count": (len(campaign.worlds), _EXPECTED_WORLDS, "campaign.worlds"),
        "stage_count": (len(campaign.stages), _EXPECTED_STAGES, "campaign.stages"),
        "boss_count": (len(bundle.bosses), _EXPECTED_BOSSES, "bosses"),
        "mote_count": (
            sum(len(stage.motes) for stage in campaign.stages.values()),
            _EXPECTED_MOTES,
            "campaign.motes",
        ),
    }
    for code, (received, expected, path) in actual.items():
        if received != expected:
            issues.append(_issue(code, path, f"expected {expected}, received {received}"))
    for world_id, nodes in campaign.worlds.items():
        if len(nodes) != 5:
            issues.append(
                _issue(
                    "world_stage_count",
                    f"campaign.worlds.{world_id}.nodes",
                    f"expected 5, received {len(nodes)}",
                )
            )
        boss_nodes = sum(node.is_boss for node in nodes)
        if boss_nodes != 1:
            issues.append(
                _issue(
                    "world_boss_count",
                    f"campaign.worlds.{world_id}.nodes",
                    f"expected 1 boss node, received {boss_nodes}",
                )
            )
    return issues


def _record_duplicate(
    seen: dict[str, str],
    stable_id: str,
    path: str,
    code: str,
    issues: list[ValidationIssue],
) -> None:
    previous = seen.get(stable_id)
    if previous is None:
        seen[stable_id] = path
        return
    issues.append(_issue(code, path, f"duplicates {stable_id!r} first declared at {previous}"))


def _identity_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    mote_ids: dict[str, str] = {}
    checkpoint_ids: dict[str, str] = {}
    interaction_ids: dict[str, str] = {}
    spawn_ids: dict[str, str] = {}
    for stage_id, stage in bundle.campaign.stages.items():
        base = f"campaign.stages.{stage_id}"
        for index, mote in enumerate(stage.motes):
            _record_duplicate(
                mote_ids,
                mote.mote_id,
                f"{base}.motes[{index}]",
                "duplicate_mote_id",
                issues,
            )
        for index, checkpoint in enumerate(stage.checkpoints):
            _record_duplicate(
                checkpoint_ids,
                checkpoint.checkpoint_id,
                f"{base}.checkpoints[{index}]",
                "duplicate_checkpoint_id",
                issues,
            )
        for index, interaction in enumerate(stage.interactions):
            _record_duplicate(
                interaction_ids,
                interaction.interaction_id,
                f"{base}.interactions[{index}]",
                "duplicate_interaction_id",
                issues,
            )
        for index, enemy in enumerate(stage.enemy_spawns):
            if enemy.spawn_id:
                _record_duplicate(
                    spawn_ids,
                    enemy.spawn_id,
                    f"{base}.enemy_spawns[{index}]",
                    "duplicate_spawn_id",
                    issues,
                )

    phase_ids: dict[str, str] = {}
    attack_ids: dict[str, str] = {}
    for boss_id, boss in bundle.bosses.items():
        for phase_index, phase in enumerate(boss.phases):
            phase_path = f"bosses.{boss_id}.phases[{phase_index}]"
            _record_duplicate(
                phase_ids,
                phase.phase_id,
                phase_path,
                "duplicate_phase_id",
                issues,
            )
            for attack_index, attack in enumerate(phase.attacks):
                _record_duplicate(
                    attack_ids,
                    attack.attack_id,
                    f"{phase_path}.attacks[{attack_index}]",
                    "duplicate_attack_id",
                    issues,
                )
    return issues


def _tile_in_bounds(stage: StageSpec, tile_x: int, tile_y: int) -> bool:
    return 0 <= tile_x < stage.width_tiles and 0 <= tile_y < stage.height_tiles


def _bounds_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for stage_id, stage in bundle.campaign.stages.items():
        base = f"campaign.stages.{stage_id}"
        for name, value in (
            ("width_tiles", stage.width_tiles),
            ("height_tiles", stage.height_tiles),
            ("tile_size", stage.tile_size),
        ):
            if value <= 0:
                issues.append(_issue("invalid_dimension", f"{base}.{name}", "must be positive"))
        if not 0 <= stage.ground_y_tile < stage.height_tiles:
            issues.append(
                _issue(
                    "out_of_bounds",
                    f"{base}.ground_y_tile",
                    f"tile row {stage.ground_y_tile} is outside stage bounds",
                )
            )
        tile_values: list[tuple[str, int, int]] = [("goal_tile", *stage.goal_tile)]
        tile_values.extend((f"hazards[{index}]", *tile) for index, tile in enumerate(stage.hazards))
        tile_values.extend((f"one_way_tiles[{index}]", *tile) for index, tile in enumerate(stage.one_way_tiles))
        tile_values.extend((f"solids[{index}]", *tile) for index, tile in enumerate(stage.solids))
        tile_values.extend((f"motes[{index}]", mote.tile_x, mote.tile_y) for index, mote in enumerate(stage.motes))
        tile_values.extend(
            (f"checkpoints[{index}]", checkpoint.tile_x, checkpoint.tile_y)
            for index, checkpoint in enumerate(stage.checkpoints)
        )
        tile_values.extend(
            (f"navigation.nodes[{index}]", node.tile_x, node.tile_y)
            for index, node in enumerate(stage.navigation.nodes)
        )
        for path, tile_x, tile_y in tile_values:
            if not _tile_in_bounds(stage, tile_x, tile_y):
                issues.append(
                    _issue(
                        "out_of_bounds",
                        f"{base}.{path}",
                        f"tile ({tile_x}, {tile_y}) is outside stage bounds",
                    )
                )
        for index, interaction in enumerate(stage.interactions):
            if interaction.width_tiles <= 0 or interaction.height_tiles <= 0:
                issues.append(
                    _issue(
                        "invalid_interaction_bounds",
                        f"{base}.interactions[{index}]",
                        "interaction dimensions must be positive",
                    )
                )
            end_x = interaction.tile_x + interaction.width_tiles - 1
            end_y = interaction.tile_y + interaction.height_tiles - 1
            if not _tile_in_bounds(stage, interaction.tile_x, interaction.tile_y) or not _tile_in_bounds(
                stage, end_x, end_y
            ):
                issues.append(
                    _issue(
                        "out_of_bounds",
                        f"{base}.interactions[{index}]",
                        "interaction bounds extend outside the stage",
                    )
                )
        for index, (x, y) in enumerate(stage.player_spawns):
            if not (
                math.isfinite(x) and math.isfinite(y) and 0 <= x < stage.pixel_width and 0 <= y < stage.pixel_height
            ):
                issues.append(
                    _issue(
                        "out_of_bounds",
                        f"{base}.player_spawns[{index}]",
                        f"pixel position ({x}, {y}) is outside stage bounds",
                    )
                )
        for index, enemy in enumerate(stage.enemy_spawns):
            if not (
                math.isfinite(enemy.x)
                and math.isfinite(enemy.y)
                and 0 <= enemy.x < stage.pixel_width
                and 0 <= enemy.y < stage.pixel_height
            ):
                issues.append(
                    _issue(
                        "out_of_bounds",
                        f"{base}.enemy_spawns[{index}]",
                        f"pixel position ({enemy.x}, {enemy.y}) is outside stage bounds",
                    )
                )
    return issues


def _safe_spawn_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for stage_id, stage in bundle.campaign.stages.items():
        if stage.tile_size <= 0:
            continue
        blocked = set(stage.solids) | set(stage.hazards)
        base = f"campaign.stages.{stage_id}"
        for index, (x, y) in enumerate(stage.player_spawns):
            if math.isfinite(x) and math.isfinite(y):
                tile = (int(x // stage.tile_size), int(y // stage.tile_size))
                if tile in blocked:
                    issues.append(
                        _issue(
                            "unsafe_player_spawn",
                            f"{base}.player_spawns[{index}]",
                            f"spawn occupies blocked tile {tile}",
                        )
                    )
        for index, enemy in enumerate(stage.enemy_spawns):
            if math.isfinite(enemy.x) and math.isfinite(enemy.y):
                tile = (
                    int(enemy.x // stage.tile_size),
                    int(enemy.y // stage.tile_size),
                )
                if tile in blocked:
                    issues.append(
                        _issue(
                            "unsafe_enemy_spawn",
                            f"{base}.enemy_spawns[{index}]",
                            f"spawn occupies blocked tile {tile}",
                        )
                    )
    return issues


def _mote_count_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    return [
        _issue(
            "stage_mote_count",
            f"campaign.stages.{stage_id}.motes",
            f"expected 3, received {len(stage.motes)}",
        )
        for stage_id, stage in bundle.campaign.stages.items()
        if len(stage.motes) != 3
    ]


def _navigation_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for stage_id, stage in bundle.campaign.stages.items():
        graph = stage.navigation
        base = f"campaign.stages.{stage_id}"
        nav_path = f"{base}.navigation"
        if not graph.nodes:
            issues.append(_issue("missing_navigation", nav_path, "navigation graph is empty"))
            continue
        nodes: dict[str, tuple[int, int]] = {}
        for index, node in enumerate(graph.nodes):
            if node.nav_id in nodes:
                issues.append(
                    _issue(
                        "duplicate_navigation_node",
                        f"{nav_path}.nodes[{index}].nav_id",
                        f"duplicate navigation node: {node.nav_id}",
                    )
                )
            else:
                nodes[node.nav_id] = (node.tile_x, node.tile_y)

        adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
        for index, edge in enumerate(graph.edges):
            source, target = edge
            valid = True
            if source not in nodes:
                issues.append(
                    _issue(
                        "missing_navigation_node",
                        f"{nav_path}.edges[{index}][0]",
                        f"edge source does not exist: {source}",
                    )
                )
                valid = False
            if target not in nodes:
                issues.append(
                    _issue(
                        "missing_navigation_node",
                        f"{nav_path}.edges[{index}][1]",
                        f"edge target does not exist: {target}",
                    )
                )
                valid = False
            if valid:
                adjacency[source].add(target)

        if graph.start not in nodes:
            issues.append(
                _issue(
                    "missing_navigation_node",
                    f"{nav_path}.start",
                    f"start node does not exist: {graph.start}",
                )
            )
            reachable: set[str] = set()
        else:
            reachable = {graph.start}
            pending = [graph.start]
            while pending:
                current = pending.pop()
                for target in sorted(adjacency[current]):
                    if target not in reachable:
                        reachable.add(target)
                        pending.append(target)

        if graph.goal not in nodes:
            issues.append(
                _issue(
                    "missing_navigation_node",
                    f"{nav_path}.goal",
                    f"goal node does not exist: {graph.goal}",
                )
            )
        elif graph.goal not in reachable:
            issues.append(
                _issue(
                    "unreachable_goal",
                    f"{nav_path}.goal",
                    f"goal node is not reachable from {graph.start}",
                )
            )

        reachable_tiles = {nodes[node_id] for node_id in reachable}
        for index, checkpoint in enumerate(stage.checkpoints):
            if (checkpoint.tile_x, checkpoint.tile_y) not in reachable_tiles:
                issues.append(
                    _issue(
                        "unreachable_checkpoint",
                        f"{base}.checkpoints[{index}]",
                        "checkpoint has no reachable navigation node",
                    )
                )
        for index, mote in enumerate(stage.motes):
            if (mote.tile_x, mote.tile_y) not in reachable_tiles:
                issues.append(
                    _issue(
                        "unreachable_mote",
                        f"{base}.motes[{index}]",
                        "mote has no reachable navigation node",
                    )
                )
    return issues


def _ability_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    authored = {
        enemy.ability_id
        for stage in bundle.campaign.stages.values()
        for enemy in stage.enemy_spawns
        if enemy.ability_id is not None
    }
    return [
        _issue(
            "missing_ability_source",
            f"campaign.abilities.{ability_id}",
            "no campaign enemy supplies this public ability",
        )
        for ability_id in sorted(PUBLIC_ABILITY_IDS - authored)
    ]


def _boss_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    referenced: set[str] = set()
    for nodes in bundle.campaign.worlds.values():
        for node in nodes:
            stage = bundle.campaign.stages.get(node.stage_id)
            if stage is None:
                continue
            path = f"campaign.stages.{stage.stage_id}.boss_id"
            if node.is_boss:
                if stage.boss_id is None:
                    issues.append(_issue("missing_boss", path, "boss stage has no boss_id"))
                elif stage.boss_id not in bundle.bosses:
                    issues.append(
                        _issue(
                            "missing_boss",
                            path,
                            f"boss does not exist: {stage.boss_id}",
                        )
                    )
                else:
                    referenced.add(stage.boss_id)
            elif stage.boss_id is not None:
                issues.append(
                    _issue(
                        "unexpected_boss",
                        path,
                        f"non-boss node references {stage.boss_id}",
                    )
                )

    for boss_id, boss in bundle.bosses.items():
        base = f"bosses.{boss_id}"
        if boss.max_hp <= 0:
            issues.append(_issue("invalid_boss_hp", f"{base}.max_hp", "must be positive"))
        if not boss.phases:
            issues.append(_issue("missing_boss_phase", f"{base}.phases", "boss has no phases"))
        previous_ratio = math.inf
        for phase_index, phase in enumerate(boss.phases):
            phase_path = f"{base}.phases[{phase_index}]"
            ratio = phase.enter_at_hp_ratio
            if not math.isfinite(ratio) or not 0 < ratio <= 1:
                issues.append(
                    _issue(
                        "invalid_phase_ratio",
                        f"{phase_path}.enter_at_hp_ratio",
                        "ratio must be finite and in (0, 1]",
                    )
                )
            if phase_index == 0 and ratio != 1.0:
                issues.append(
                    _issue(
                        "invalid_phase_order",
                        f"{phase_path}.enter_at_hp_ratio",
                        "first phase must enter at 1.0",
                    )
                )
            if ratio >= previous_ratio:
                issues.append(
                    _issue(
                        "invalid_phase_order",
                        f"{phase_path}.enter_at_hp_ratio",
                        "phase ratios must strictly decrease",
                    )
                )
            previous_ratio = ratio
            if not phase.attacks:
                issues.append(_issue("missing_boss_attack", f"{phase_path}.attacks", "phase has no attacks"))
            for attack_index, attack in enumerate(phase.attacks):
                attack_path = f"{phase_path}.attacks[{attack_index}]"
                for name, duration in (
                    ("telegraph_ms", attack.telegraph_ms),
                    ("active_ms", attack.active_ms),
                    ("recovery_ms", attack.recovery_ms),
                ):
                    if duration <= 0:
                        issues.append(
                            _issue(
                                "invalid_attack_timing",
                                f"{attack_path}.{name}",
                                "duration must be positive",
                            )
                        )
        if boss_id not in referenced:
            issues.append(_issue("orphan_boss", base, "boss is not referenced by a boss stage"))
    return issues


def _layout_issues(bundle: CatalogBundle) -> tuple[list[ValidationIssue], int]:
    issues: list[ValidationIssue] = []
    signatures: dict[str, str] = {}
    for stage_id, stage in bundle.campaign.stages.items():
        signature = stage.layout_signature()
        first = signatures.get(signature)
        if first is None:
            signatures[signature] = stage_id
        else:
            issues.append(
                _issue(
                    "duplicate_layout",
                    f"campaign.stages.{stage_id}",
                    f"layout duplicates {first}",
                )
            )
    return issues, len(issues)


def _reward_issues(bundle: CatalogBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    previous = 0
    seen_ids: set[str] = set()
    for index, reward in enumerate(bundle.rewards.mote_thresholds):
        base = f"rewards.mote_thresholds[{index}]"
        if reward.threshold <= previous:
            issues.append(
                _issue(
                    "reward_threshold_order",
                    f"{base}.threshold",
                    "thresholds must be positive and strictly increasing",
                )
            )
        previous = reward.threshold
        if reward.reward_id in seen_ids:
            issues.append(
                _issue(
                    "duplicate_reward_id",
                    f"{base}.reward_id",
                    f"duplicate reward ID: {reward.reward_id}",
                )
            )
        seen_ids.add(reward.reward_id)
    return issues


def _format_fields(value: str, path: str, issues: list[ValidationIssue]) -> tuple[str, ...]:
    try:
        return tuple(
            sorted(field_name for _, field_name, _, _ in string.Formatter().parse(value) if field_name is not None)
        )
    except ValueError as error:
        issues.append(_issue("invalid_locale_format", path, str(error)))
        return ()


def _locale_issues(bundle: CatalogBundle, locales: LocaleCatalog) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    tables = locales.strings
    if "en" not in tables:
        return [_issue("missing_locale", "locales.en", "English source locale is missing")]
    source = tables["en"]
    required_keys = {
        key for stage in bundle.campaign.stages.values() for key in (stage.name_key, stage.intro_key) if key
    }
    required_keys.update(
        key
        for world in bundle.campaign.world_specs.values()
        for key in (world.name_key, world.identity_key, *world.mechanic_keys)
        if key
    )
    required_keys.update(boss.name_key for boss in bundle.bosses.values())
    required_keys.update(reward.name_key for reward in bundle.rewards.mote_thresholds)
    for key in sorted(required_keys - source.keys()):
        issues.append(_issue("missing_locale_key", f"locales.en.{key}", "required key is missing"))

    source_fields = {key: _format_fields(text, f"locales.en.{key}", issues) for key, text in source.items()}
    for language, table in tables.items():
        if language == "en":
            continue
        for key in sorted(source.keys() - table.keys()):
            issues.append(
                _issue(
                    "missing_locale_key",
                    f"locales.{language}.{key}",
                    "source-locale key is missing",
                )
            )
        for key in sorted(table.keys() - source.keys()):
            issues.append(
                _issue(
                    "extra_locale_key",
                    f"locales.{language}.{key}",
                    "key is absent from the source locale",
                )
            )
        for key in sorted(source.keys() & table.keys()):
            fields = _format_fields(table[key], f"locales.{language}.{key}", issues)
            if fields != source_fields[key]:
                issues.append(
                    _issue(
                        "locale_placeholder_mismatch",
                        f"locales.{language}.{key}",
                        f"expected {sorted(source_fields[key])}, received {sorted(fields)}",
                    )
                )
    return issues


def _safe_asset_path(asset_root: Path, relative: str) -> Path | None:
    path = Path(relative)
    if path.is_absolute() or path.drive or ".." in path.parts:
        return None
    candidate = asset_root / path
    try:
        candidate.resolve(strict=False).relative_to(asset_root.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        return None
    return candidate


def _manifest_issues(
    bundle: CatalogBundle,
    assets: AssetManifest,
    asset_root: Path | None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for boss_id, boss in bundle.bosses.items():
        if boss.visual_id not in assets.art:
            issues.append(
                _issue(
                    "missing_asset_id",
                    f"bosses.{boss_id}.visual_id",
                    f"art asset does not exist: {boss.visual_id}",
                )
            )
        for phase_index, phase in enumerate(boss.phases):
            for attack_index, attack in enumerate(phase.attacks):
                if attack.cue_id not in assets.audio:
                    issues.append(
                        _issue(
                            "missing_asset_id",
                            f"bosses.{boss_id}.phases[{phase_index}].attacks[{attack_index}].cue_id",
                            f"audio cue does not exist: {attack.cue_id}",
                        )
                    )
    if asset_root is None:
        return issues
    records = [(f"assets.art.{asset_id}", record.path) for asset_id, record in assets.art.items()]
    records.extend((f"assets.audio.{asset_id}", record.path) for asset_id, record in assets.audio.items())
    records.append(("assets.font", assets.font.path))
    for path, relative in records:
        candidate = _safe_asset_path(asset_root, relative)
        if candidate is None:
            issues.append(_issue("unsafe_asset_path", f"{path}.path", relative))
        elif not candidate.is_file():
            issues.append(_issue("missing_asset_file", f"{path}.path", f"file does not exist: {relative}"))
    return issues


def _font_issues(assets: AssetManifest, asset_root: Path | None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not assets.font.mandatory:
        issues.append(_issue("font_not_mandatory", "assets.font.mandatory", "must be true"))
    if not assets.font.license:
        issues.append(_issue("missing_font_license", "assets.font.license", "license path is empty"))
    elif asset_root is not None:
        license_path = _safe_asset_path(asset_root, assets.font.license)
        if license_path is None or not license_path.is_file():
            issues.append(
                _issue(
                    "missing_font_license",
                    "assets.font.license",
                    f"license file does not exist: {assets.font.license}",
                )
            )
    return issues


def _provenance_issues(
    assets: AssetManifest,
    asset_root: Path | None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for asset_id, record in assets.art.items():
        if not record.provenance:
            issues.append(
                _issue(
                    "missing_provenance",
                    f"assets.art.{asset_id}.provenance",
                    "art provenance is required",
                )
            )
    if not assets.provenance_files:
        issues.append(
            _issue(
                "missing_provenance",
                "assets.provenance_files",
                "at least one provenance record is required",
            )
        )
    elif asset_root is not None:
        for index, relative in enumerate(assets.provenance_files):
            candidate = _safe_asset_path(asset_root, relative)
            if candidate is None or not candidate.is_file():
                issues.append(
                    _issue(
                        "missing_provenance",
                        f"assets.provenance_files[{index}]",
                        f"provenance file does not exist: {relative}",
                    )
                )
    return issues


def _audio_coverage_issues(assets: AssetManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    music = sum(record.bus == "music" for record in assets.audio.values())
    sfx = sum(record.bus == "sfx" for record in assets.audio.values())
    if music != _EXPECTED_MUSIC:
        issues.append(
            _issue(
                "music_cue_count",
                "assets.audio.music",
                f"expected {_EXPECTED_MUSIC}, received {music}",
            )
        )
    if sfx != _EXPECTED_SFX:
        issues.append(
            _issue(
                "sfx_cue_count",
                "assets.audio.sfx",
                f"expected {_EXPECTED_SFX}, received {sfx}",
            )
        )
    return issues


def validate_bundle(
    bundle: CatalogBundle,
    assets: AssetManifest,
    locales: LocaleCatalog,
    *,
    asset_root: Path | None = None,
) -> ValidationReport:
    """Return all semantic issues in fixed category and stable path order."""

    if not isinstance(bundle, CatalogBundle):
        raise TypeError("bundle must be a CatalogBundle")
    if not isinstance(assets, AssetManifest):
        raise TypeError("assets must be an AssetManifest")
    if not isinstance(locales, LocaleCatalog):
        raise TypeError("locales must be a LocaleCatalog")
    if asset_root is not None and not isinstance(asset_root, Path):
        raise TypeError("asset_root must be a pathlib.Path or None")

    layout_issues, duplicate_layouts = _layout_issues(bundle)
    categories = (
        _reference_issues(bundle),
        _count_issues(bundle),
        _identity_issues(bundle),
        _bounds_issues(bundle),
        _safe_spawn_issues(bundle),
        _mote_count_issues(bundle),
        _navigation_issues(bundle),
        _ability_issues(bundle),
        _boss_issues(bundle),
        layout_issues,
        _reward_issues(bundle),
        _locale_issues(bundle, locales),
        _manifest_issues(bundle, assets, asset_root),
        _font_issues(assets, asset_root),
        _provenance_issues(assets, asset_root),
        _audio_coverage_issues(assets),
    )
    errors = tuple(issue for category in categories for issue in _stable(category))
    music = sum(record.bus == "music" for record in assets.audio.values())
    sfx = sum(record.bus == "sfx" for record in assets.audio.values())
    counts = {
        "worlds": len(bundle.campaign.worlds),
        "stages": len(bundle.campaign.stages),
        "bosses": len(bundle.bosses),
        "motes": sum(len(stage.motes) for stage in bundle.campaign.stages.values()),
        "locales": len(locales.strings),
        "music": music,
        "sfx": sfx,
        "duplicate_layouts": duplicate_layouts,
    }
    return ValidationReport(errors=errors, counts=counts)
