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
