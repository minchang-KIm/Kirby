from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from tools import generate_campaign
from windsprig.content.loader import load_campaign_catalog, load_reward_catalog
from windsprig.content.models import StageSpec

CONTENT_DIR = Path("windsprig/content")
EXPECTED_WORLD_IDS = tuple(f"world_{number}" for number in range(1, 7))
EXPECTED_ABILITY_IDS = {
    "bloomblade",
    "cinder",
    "voltsong",
    "galehook",
    "stoneheart",
    "tempest",
}
EXPECTED_ENEMY_KINDS = {
    "breezeling",
    "bramblekin",
    "millmite",
    "cinderling",
    "slagroller",
    "shutterimp",
    "bubblefin",
    "shellskiff",
    "moonjelly",
    "coilbird",
    "railrunner",
    "stormlens",
    "petalisk",
    "mirrormite",
    "gravitybud",
    "hushshade",
    "lockwarden",
    "riftling",
}
EXPECTED_BOSS_IDS = {
    "rootjaw",
    "crucible_crab",
    "luma_eel",
    "volt_roc",
    "prism_warden",
    "the_stillness",
}
EXPECTED_REWARDS = (
    (6, "gallery.sunleaf", "gallery"),
    (12, "palette.mint", "palette"),
    (18, "challenge.sunleaf", "challenge"),
    (24, "gallery.emberglass", "gallery"),
    (30, "palette.ember", "palette"),
    (36, "challenge.emberglass", "challenge"),
    (42, "gallery.tidemoon", "gallery"),
    (48, "palette.moon", "palette"),
    (54, "challenge.tidemoon", "challenge"),
    (60, "gallery.thunderrail", "gallery"),
    (66, "palette.storm", "palette"),
    (72, "challenge.thunderrail", "challenge"),
    (78, "gallery.prismbloom", "gallery"),
    (82, "palette.prism", "palette"),
    (84, "challenge.prismbloom", "challenge"),
    (86, "gallery.stillstar", "gallery"),
    (88, "palette.stillstar", "palette"),
    (90, "challenge.stillstar", "challenge"),
)


def _reachable_navigation_ids(stage: StageSpec) -> set[str]:
    navigation = stage.navigation
    adjacent: dict[str, list[str]] = {}
    for source, target in navigation.edges:
        adjacent.setdefault(source, []).append(target)
    pending = [navigation.start]
    reached: set[str] = set()
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(adjacent.get(current, ()))
    return reached


def test_campaign_has_exact_release_catalog_and_stable_ids() -> None:
    campaign = load_campaign_catalog(CONTENT_DIR)
    worlds = tuple(campaign.world_specs.values())
    stages = tuple(sorted(campaign.stages.values(), key=lambda stage: stage.order))
    mote_ids = [mote.mote_id for stage in stages for mote in stage.motes]

    assert tuple(world.world_id for world in worlds) == EXPECTED_WORLD_IDS
    assert tuple(world.order for world in worlds) == tuple(range(1, 7))
    assert tuple(stage.order for stage in stages) == tuple(range(1, 31))
    assert len(stages) == 30
    assert {stage.boss_id for stage in stages if stage.boss_id is not None} == EXPECTED_BOSS_IDS
    assert len(mote_ids) == len(set(mote_ids)) == 90
    assert all(
        tuple(mote.mote_id for mote in stage.motes)
        == tuple(f"{stage.stage_id}:mote:{number}" for number in range(1, 4))
        for stage in stages
    )
    assert len({stage.layout_signature() for stage in stages}) == 30
    assert {enemy.ability_id for stage in stages for enemy in stage.enemy_spawns} == EXPECTED_ABILITY_IDS
    assert {enemy.kind for stage in stages for enemy in stage.enemy_spawns} == EXPECTED_ENEMY_KINDS
    assert all(world.nodes is campaign.worlds[world.world_id] for world in worlds)


def test_progression_is_one_connected_30_node_chain_with_preserved_rewards() -> None:
    campaign = load_campaign_catalog(CONTENT_DIR)
    nodes = [node for world in campaign.world_specs.values() for node in world.nodes]

    assert nodes[0].requires == ()
    assert all(nodes[index].requires == (nodes[index - 1].node_id,) for index in range(1, 30))
    assert [node.is_boss for node in nodes].count(True) == 6
    assert tuple(node.rewards for node in nodes if node.is_boss) == (
        ("unlock:world_2",),
        ("unlock:world_3",),
        ("unlock:world_4",),
        ("unlock:world_5",),
        ("unlock:world_6",),
        (),
    )
    assert all(node.rewards == () for node in nodes if not node.is_boss)


def test_every_authored_target_is_reachable_from_the_stage_start() -> None:
    campaign = load_campaign_catalog(CONTENT_DIR)

    for stage in campaign.stages.values():
        reached = _reachable_navigation_ids(stage)
        target_ids = {
            stage.navigation.start,
            stage.navigation.goal,
            *(checkpoint.checkpoint_id for checkpoint in stage.checkpoints),
            *(f"nav.{mote.mote_id}" for mote in stage.motes),
        }
        nodes = {node.nav_id: node for node in stage.navigation.nodes}
        assert target_ids <= reached, stage.stage_id
        assert (nodes[stage.navigation.goal].tile_x, nodes[stage.navigation.goal].tile_y) == stage.goal_tile


def test_reward_projection_loads_the_exact_strictly_increasing_recipe() -> None:
    rewards = load_reward_catalog(CONTENT_DIR)
    assert (
        tuple((reward.threshold, reward.reward_id, reward.kind) for reward in rewards.mote_thresholds)
        == EXPECTED_REWARDS
    )
    assert tuple(reward.threshold for reward in rewards.mote_thresholds) == tuple(
        sorted({threshold for threshold, _, _ in EXPECTED_REWARDS})
    )


def test_reward_projection_rejects_non_path_content_directory() -> None:
    with pytest.raises(TypeError, match="content_dir must be a pathlib.Path"):
        load_reward_catalog("windsprig/content")  # type: ignore[arg-type]


def test_generator_embeds_every_normative_recipe_row_exactly() -> None:
    recipe_digest = sha256(
        repr(
            (
                generate_campaign.WORLDS,
                generate_campaign.STAGES,
                generate_campaign.BOSSES,
                generate_campaign.REWARDS,
            )
        ).encode()
    ).hexdigest()
    assert recipe_digest == "06c176067a49fbbf8fd7db52769920fb8b6dfe80ae172622bf21ec04b3d87d4f"
    assert (
        len(generate_campaign.WORLDS),
        len(generate_campaign.STAGES),
        len(generate_campaign.BOSSES),
        len(generate_campaign.REWARDS),
    ) == (6, 30, 6, 18)


def test_representative_stage_converts_tiles_to_canonical_runtime_schema() -> None:
    stage = generate_campaign.stage_payload(generate_campaign.STAGES[0], world_index=1, stage_index=1)

    assert stage["stage_id"] == "world_1_stage_1"
    assert stage["ground_y_tile"] == 20
    assert stage["player_spawns"] == [[64.0, 580.0], [94.0, 580.0], [124.0, 580.0], [154.0, 580.0]]
    assert stage["enemy_spawns"][0] == {
        "spawn_id": "enemy.world_1.01.1",
        "kind": "breezeling",
        "ability_id": "galehook",
        "x": 704.0,
        "y": 608.0,
        "patrol_left": 576.0,
        "patrol_right": 832.0,
        "elite": False,
    }
    assert "tile_x" not in stage["enemy_spawns"][0]
    assert "tile_y" not in stage["enemy_spawns"][0]
    assert stage["interactions"][0]["params"] == {}
    assert len(stage["solids"]) == 336
    assert [0, 20] in stage["solids"] and [0, 23] in stage["solids"]
    assert [31, 20] not in stage["solids"]
    assert stage["hazards"] == [[31, 20], [32, 20], [33, 20], [34, 20], [68, 20], [69, 20], [70, 20], [71, 20]]
    assert stage["goal_tile"] == [88, 19]
    assert stage["navigation"]["edges"] == [
        ["start", "world_1_stage_1:checkpoint:1"],
        ["world_1_stage_1:checkpoint:1", "world_1_stage_1:checkpoint:2"],
        ["world_1_stage_1:checkpoint:2", "goal"],
        ["start", "nav.world_1_stage_1:mote:1"],
        ["nav.world_1_stage_1:mote:1", "start"],
        ["world_1_stage_1:checkpoint:1", "nav.world_1_stage_1:mote:2"],
        ["nav.world_1_stage_1:mote:2", "world_1_stage_1:checkpoint:1"],
        ["goal", "nav.world_1_stage_1:mote:3"],
        ["nav.world_1_stage_1:mote:3", "goal"],
    ]


def test_canonical_output_is_repeatable_and_matches_tracked_bytes() -> None:
    first = generate_campaign.canonical_outputs()
    second = generate_campaign.canonical_outputs()

    assert first == second
    assert tuple(first) == (
        Path("windsprig/content/campaign.json"),
        Path("windsprig/content/rewards.json"),
        Path("windsprig/content/bosses.json"),
    )
    for relative_path, canonical in first.items():
        assert relative_path.read_bytes() == canonical.encode("utf-8")
        assert canonical.endswith("\n") and not canonical.endswith("\n\n")
        assert json.loads(canonical)


def test_generated_catalogs_are_checked_out_with_canonical_lf_bytes() -> None:
    attributes_path = Path(".gitattributes")
    assert attributes_path.exists(), "generated byte checks require explicit Git EOL policy"
    attributes = set(attributes_path.read_text(encoding="utf-8").splitlines())
    assert "windsprig/content/campaign.json text eol=lf" in attributes
    assert "windsprig/content/rewards.json text eol=lf" in attributes
    assert "windsprig/content/bosses.json text eol=lf" in attributes


def test_check_mode_reports_all_stale_paths_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    campaign_path = tmp_path / "windsprig/content/campaign.json"
    reward_path = tmp_path / "windsprig/content/rewards.json"
    boss_path = tmp_path / "windsprig/content/bosses.json"
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_text("campaign sentinel\n", encoding="utf-8")
    reward_path.write_text("reward sentinel\n", encoding="utf-8")
    boss_path.write_text("boss sentinel\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (campaign_path, reward_path, boss_path)}

    assert generate_campaign.main(["--check"], root=tmp_path) == 1
    assert capsys.readouterr().out == (
        "STALE: windsprig/content/bosses.json, windsprig/content/campaign.json, windsprig/content/rewards.json\n"
    )
    assert {path: path.read_bytes() for path in before} == before


def test_generation_writes_canonical_outputs_and_then_checks_clean(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert generate_campaign.main([], root=tmp_path) == 0
    assert capsys.readouterr().out == ("campaign: 6 worlds, 30 stages, 6 bosses, 90 motes, 18 rewards\n")
    for relative_path, canonical in generate_campaign.canonical_outputs().items():
        assert (tmp_path / relative_path).read_bytes() == canonical.encode("utf-8")
    assert not tuple(tmp_path.rglob("*.tmp"))

    assert generate_campaign.main(["--check"], root=tmp_path) == 0
    assert capsys.readouterr().out == ("campaign: 6 worlds, 30 stages, 6 bosses, 90 motes, 18 rewards\n")


def test_generation_serializes_every_output_before_replacing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_path = tmp_path / "windsprig/content/campaign.json"
    reward_path = tmp_path / "windsprig/content/rewards.json"
    boss_path = tmp_path / "windsprig/content/bosses.json"
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_text("campaign sentinel\n", encoding="utf-8")
    reward_path.write_text("reward sentinel\n", encoding="utf-8")
    boss_path.write_text("boss sentinel\n", encoding="utf-8")
    original_dumps = generate_campaign.json.dumps
    serialization_calls = 0

    def fail_second_serialization(*args: object, **kwargs: object) -> str:
        nonlocal serialization_calls
        serialization_calls += 1
        if serialization_calls == 2:
            raise TypeError("serialization failed")
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(generate_campaign.json, "dumps", fail_second_serialization)
    with pytest.raises(TypeError, match="serialization failed"):
        generate_campaign.main([], root=tmp_path)

    assert serialization_calls == 2
    assert campaign_path.read_text(encoding="utf-8") == "campaign sentinel\n"
    assert reward_path.read_text(encoding="utf-8") == "reward sentinel\n"
    assert boss_path.read_text(encoding="utf-8") == "boss sentinel\n"
