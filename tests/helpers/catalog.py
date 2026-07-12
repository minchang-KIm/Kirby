"""Factories for compact, strictly valid campaign catalog fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path


def minimal_documents() -> dict[str, dict[str, object]]:
    """Return independent JSON-shaped documents for one valid catalog bundle."""

    campaign: dict[str, object] = {
        "version": "1.0.0",
        "worlds": [
            {
                "world_id": "demo",
                "order": 1,
                "name_key": "world.demo.name",
                "identity_key": "world.demo.identity",
                "mechanic_keys": ["mechanic.gust"],
                "palette_id": "demo",
                "nodes": [
                    {
                        "node_id": "demo_node_1",
                        "stage_id": "demo_01",
                        "requires": [],
                        "rewards": [],
                        "position": [100, 120],
                        "is_boss": True,
                    }
                ],
            }
        ],
        "stages": [
            {
                "stage_id": "demo_01",
                "world_id": "demo",
                "node_id": "demo_node_1",
                "width_tiles": 12,
                "height_tiles": 8,
                "tile_size": 32,
                "ground_y_tile": 6,
                "player_spawns": [[32.0, 160.0]],
                "enemy_spawns": [
                    {
                        "x": 192.0,
                        "y": 160.0,
                        "kind": "grunt",
                        "ability_id": "cinder",
                        "patrol_left": 160.0,
                        "patrol_right": 224.0,
                        "spawn_id": "demo_01.enemy.1",
                        "elite": False,
                    }
                ],
                "motes": [
                    {"mote_id": "demo_01:mote:1", "tile_x": 3, "tile_y": 4, "route": "main"},
                    {"mote_id": "demo_01:mote:2", "tile_x": 6, "tile_y": 3, "route": "optional"},
                    {"mote_id": "demo_01:mote:3", "tile_x": 9, "tile_y": 4, "route": "mastery"},
                ],
                "checkpoints": [{"checkpoint_id": "demo_01.start", "tile_x": 1, "tile_y": 5}],
                "interactions": [
                    {
                        "interaction_id": "demo_01.gust",
                        "kind": "gust_lift",
                        "tile_x": 4,
                        "tile_y": 4,
                        "width_tiles": 1,
                        "height_tiles": 2,
                        "params": {"strength": 1.5, "enabled": True},
                    }
                ],
                "goal_tile": [10, 5],
                "hazards": [[7, 5]],
                "one_way_tiles": [[5, 4]],
                "solids": [[0, 6], [1, 6], [2, 6], [3, 6]],
                "order": 1,
                "name_key": "stage.demo_01.name",
                "intro_key": "stage.demo_01.intro",
                "target_time_ms": 120000,
                "navigation": {
                    "start": "start",
                    "goal": "goal",
                    "nodes": [
                        {"nav_id": "start", "tile_x": 1, "tile_y": 5, "route": "main"},
                        {"nav_id": "mote_1", "tile_x": 3, "tile_y": 4, "route": "main"},
                        {"nav_id": "mote_2", "tile_x": 6, "tile_y": 3, "route": "optional"},
                        {"nav_id": "mote_3", "tile_x": 9, "tile_y": 4, "route": "mastery"},
                        {"nav_id": "goal", "tile_x": 10, "tile_y": 5, "route": "main"},
                    ],
                    "edges": [
                        ["start", "mote_1"],
                        ["mote_1", "mote_2"],
                        ["mote_2", "mote_3"],
                        ["mote_3", "goal"],
                    ],
                },
                "boss_id": "demo_boss",
            }
        ],
    }
    bosses: dict[str, object] = {
        "bosses": [
            {
                "boss_id": "demo_boss",
                "name_key": "boss.demo.name",
                "max_hp": 30,
                "visual_id": "boss.demo",
                "phases": [
                    {
                        "phase_id": "demo_boss.p1",
                        "enter_at_hp_ratio": 1.0,
                        "vulnerability": "vulnerable",
                        "arena_rule": "open",
                        "attacks": [
                            {
                                "attack_id": "demo_boss.gust",
                                "telegraph_ms": 700,
                                "active_ms": 400,
                                "recovery_ms": 500,
                                "marker": "lane",
                                "cue_id": "sfx.boss.demo",
                                "parameters": {"lanes": 2, "speed": 180.0},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    rewards: dict[str, object] = {
        "mote_thresholds": [
            {
                "threshold": 3,
                "reward_id": "gallery.demo",
                "kind": "gallery",
                "name_key": "reward.gallery.demo",
            }
        ]
    }
    return copy.deepcopy({"campaign": campaign, "bosses": bosses, "rewards": rewards})


def write_minimal_bundle(
    root: Path,
    documents: dict[str, dict[str, object]] | None = None,
) -> Path:
    """Write one minimal catalog bundle and return its content directory."""

    root.mkdir(parents=True, exist_ok=True)
    payloads = minimal_documents() if documents is None else copy.deepcopy(documents)
    for name, payload in payloads.items():
        (root / f"{name}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return root


_PUBLIC_ABILITY_IDS = (
    "bloomblade",
    "cinder",
    "voltsong",
    "galehook",
    "stoneheart",
    "tempest",
)
_PHASE_RATIOS = (1.0, 0.66, 0.33)


def release_documents() -> dict[str, dict[str, object]]:
    """Return a deterministic complete catalog that satisfies every Task 1 invariant."""

    worlds: list[object] = []
    stages: list[object] = []
    bosses: list[object] = []
    previous_node_id: str | None = None
    ordinal = 0
    for world_index in range(1, 7):
        world_id = f"world_{world_index}"
        boss_id = f"boss_{world_index}"
        world_nodes: list[object] = []
        for stage_index in range(1, 6):
            ordinal += 1
            stage_id = f"{world_id}_stage_{stage_index}"
            node_id = f"{world_id}_node_{stage_index}"
            width_tiles = 16 + ordinal
            is_boss = stage_index == 5
            world_nodes.append(
                {
                    "node_id": node_id,
                    "stage_id": stage_id,
                    "requires": [] if previous_node_id is None else [previous_node_id],
                    "rewards": ([f"unlock:world_{world_index + 1}"] if is_boss and world_index < 6 else []),
                    "position": [100 + stage_index * 120, 100 + world_index * 30],
                    "is_boss": is_boss,
                }
            )
            previous_node_id = node_id
            ability_id = _PUBLIC_ABILITY_IDS[(ordinal - 1) % len(_PUBLIC_ABILITY_IDS)]
            goal_tile = [width_tiles - 2, 7]
            stages.append(
                {
                    "stage_id": stage_id,
                    "world_id": world_id,
                    "node_id": node_id,
                    "width_tiles": width_tiles,
                    "height_tiles": 10,
                    "tile_size": 32,
                    "ground_y_tile": 8,
                    "player_spawns": [[32.0, 224.0]],
                    "enemy_spawns": [
                        {
                            "x": 160.0,
                            "y": 224.0,
                            "kind": f"enemy_{ordinal:02d}",
                            "ability_id": ability_id,
                            "patrol_left": 128.0,
                            "patrol_right": 192.0,
                            "spawn_id": f"{stage_id}.enemy.1",
                            "elite": stage_index == 4,
                        }
                    ],
                    "motes": [
                        {"mote_id": f"{stage_id}:mote:1", "tile_x": 3, "tile_y": 6, "route": "main"},
                        {"mote_id": f"{stage_id}:mote:2", "tile_x": 6, "tile_y": 5, "route": "optional"},
                        {"mote_id": f"{stage_id}:mote:3", "tile_x": 9, "tile_y": 6, "route": "mastery"},
                    ],
                    "checkpoints": [{"checkpoint_id": f"{stage_id}.start", "tile_x": 1, "tile_y": 7}],
                    "interactions": [
                        {
                            "interaction_id": f"{stage_id}.gust",
                            "kind": "gust_lift",
                            "tile_x": 4,
                            "tile_y": 6,
                            "width_tiles": 1,
                            "height_tiles": 1,
                            "params": {"strength": 1.0 + stage_index / 10},
                        }
                    ],
                    "goal_tile": goal_tile,
                    "hazards": [],
                    "one_way_tiles": [],
                    "solids": [[tile_x, 8] for tile_x in range(width_tiles)],
                    "order": stage_index,
                    "name_key": f"stage.{stage_id}.name",
                    "intro_key": f"stage.{stage_id}.intro",
                    "target_time_ms": 120_000 + ordinal * 1_000,
                    "navigation": {
                        "start": "start",
                        "goal": "goal",
                        "nodes": [
                            {"nav_id": "start", "tile_x": 1, "tile_y": 7, "route": "main"},
                            {"nav_id": "mote_1", "tile_x": 3, "tile_y": 6, "route": "main"},
                            {"nav_id": "mote_2", "tile_x": 6, "tile_y": 5, "route": "optional"},
                            {"nav_id": "mote_3", "tile_x": 9, "tile_y": 6, "route": "mastery"},
                            {
                                "nav_id": "goal",
                                "tile_x": goal_tile[0],
                                "tile_y": goal_tile[1],
                                "route": "main",
                            },
                        ],
                        "edges": [
                            ["start", "mote_1"],
                            ["mote_1", "mote_2"],
                            ["mote_2", "mote_3"],
                            ["mote_3", "goal"],
                        ],
                    },
                    "boss_id": boss_id if is_boss else None,
                }
            )
        worlds.append(
            {
                "world_id": world_id,
                "order": world_index,
                "name_key": f"world.{world_id}.name",
                "identity_key": f"world.{world_id}.identity",
                "mechanic_keys": [f"mechanic.{world_id}"],
                "palette_id": f"palette.{world_id}",
                "nodes": world_nodes,
            }
        )
        bosses.append(
            {
                "boss_id": boss_id,
                "name_key": f"boss.{boss_id}.name",
                "max_hp": 90 + world_index * 10,
                "visual_id": f"boss.{boss_id}",
                "phases": [
                    {
                        "phase_id": f"{boss_id}.phase_{phase_index}",
                        "enter_at_hp_ratio": ratio,
                        "vulnerability": "vulnerable" if phase_index != 2 else "armored",
                        "arena_rule": f"arena_{phase_index}",
                        "attacks": [
                            {
                                "attack_id": f"{boss_id}.attack_{phase_index}",
                                "telegraph_ms": 600 + phase_index * 100,
                                "active_ms": 400,
                                "recovery_ms": 500,
                                "marker": "lane",
                                "cue_id": f"sfx.{boss_id}.phase_{phase_index}",
                                "parameters": {"lanes": phase_index + 1},
                            }
                        ],
                    }
                    for phase_index, ratio in enumerate(_PHASE_RATIOS, start=1)
                ],
            }
        )

    rewards = [
        {
            "threshold": reward_index * 5,
            "reward_id": f"reward.release.{reward_index:02d}",
            "kind": ("challenge", "gallery", "palette")[(reward_index - 1) % 3],
            "name_key": f"reward.release.{reward_index:02d}.name",
        }
        for reward_index in range(1, 19)
    ]
    return copy.deepcopy(
        {
            "campaign": {"version": "1.0.0", "worlds": worlds, "stages": stages},
            "bosses": {"bosses": bosses},
            "rewards": {"mote_thresholds": rewards},
        }
    )


def write_release_bundle(root: Path) -> tuple[Path, Path]:
    """Write one complete strict catalog, locale set, manifest, and asset tree."""

    content = write_minimal_bundle(root / "content", release_documents())
    asset_root = root / "assets"
    art: dict[str, object] = {}
    audio: dict[str, object] = {}
    asset_paths: list[str] = []
    for world_index in range(1, 7):
        boss_id = f"boss_{world_index}"
        relative = f"generated/bosses/{boss_id}.png"
        asset_paths.append(relative)
        art[f"boss.{boss_id}"] = {
            "path": relative,
            "width": 192,
            "height": 64,
            "frames": 3,
            "pixel_sha256": f"{world_index:x}" * 64,
            "mandatory": True,
            "provenance": "deterministic-test-fixture",
        }

    boss_cues = [
        f"sfx.boss_{world_index}.phase_{phase_index}" for world_index in range(1, 7) for phase_index in range(1, 4)
    ]
    sfx_cues = boss_cues + [f"sfx.fixture.{index:02d}" for index in range(1, 12)]
    music_cues = [f"music.fixture.{index:02d}" for index in range(1, 29)]
    for index, cue_id in enumerate(music_cues, start=1):
        relative = f"generated/audio/music-{index:02d}.wav"
        asset_paths.append(relative)
        audio[cue_id] = {
            "path": relative,
            "bus": "music",
            "mandatory": True,
            "sha256": f"{index % 16:x}" * 64,
        }
    for index, cue_id in enumerate(sfx_cues, start=1):
        relative = f"generated/audio/sfx-{index:02d}.wav"
        asset_paths.append(relative)
        audio[cue_id] = {
            "path": relative,
            "bus": "sfx",
            "mandatory": True,
            "sha256": f"{(index + 7) % 16:x}" * 64,
        }

    manifest: dict[str, object] = {
        "art": art,
        "audio": audio,
        "font": {
            "path": "fonts/NotoSansKR.ttf",
            "license": "fonts/OFL-NotoSansKR.txt",
            "mandatory": True,
        },
        "provenance_files": [
            "generated/art-provenance.json",
            "generated/audio-provenance.json",
        ],
    }
    (content / "assets.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    strings_en: dict[str, str] = {}
    strings_ko: dict[str, str] = {}
    for world_index in range(1, 7):
        world_id = f"world_{world_index}"
        boss_id = f"boss_{world_index}"
        strings_en[f"world.{world_id}.name"] = f"World {world_index}"
        strings_en[f"world.{world_id}.identity"] = f"World {world_index} identity"
        strings_en[f"mechanic.{world_id}"] = f"World {world_index} mechanic"
        strings_en[f"boss.{boss_id}.name"] = f"Boss {world_index}"
        strings_ko[f"world.{world_id}.name"] = f"세계 {world_index}"
        strings_ko[f"world.{world_id}.identity"] = f"세계 {world_index} 정체성"
        strings_ko[f"mechanic.{world_id}"] = f"세계 {world_index} 기믹"
        strings_ko[f"boss.{boss_id}.name"] = f"보스 {world_index}"
        for stage_index in range(1, 6):
            stage_id = f"{world_id}_stage_{stage_index}"
            strings_en[f"stage.{stage_id}.name"] = f"Stage {world_index}-{stage_index}"
            strings_en[f"stage.{stage_id}.intro"] = f"Begin stage {world_index}-{stage_index}"
            strings_ko[f"stage.{stage_id}.name"] = f"스테이지 {world_index}-{stage_index}"
            strings_ko[f"stage.{stage_id}.intro"] = f"스테이지 {world_index}-{stage_index} 시작"
    for reward_index in range(1, 19):
        key = f"reward.release.{reward_index:02d}.name"
        strings_en[key] = f"Reward {reward_index}"
        strings_ko[key] = f"보상 {reward_index}"
    for language, strings in (("en", strings_en), ("ko", strings_ko)):
        (content / f"strings.{language}.json").write_text(
            json.dumps(strings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    for relative in asset_paths:
        path = asset_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"deterministic fixture\n")
    font = asset_root / "fonts" / "NotoSansKR.ttf"
    font.parent.mkdir(parents=True, exist_ok=True)
    font.write_bytes(b"deterministic font fixture\n")
    (font.parent / "OFL-NotoSansKR.txt").write_text(
        "SIL OPEN FONT LICENSE Version 1.1\n",
        encoding="utf-8",
    )
    for relative in ("generated/art-provenance.json", "generated/audio-provenance.json"):
        path = asset_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    return content, asset_root
