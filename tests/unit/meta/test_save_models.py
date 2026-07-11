from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from windsprig.meta.save_models import (
    AccessibilitySettings,
    AudioSettings,
    ControlSettings,
    DisplaySettings,
    GlobalSettings,
    SaveData,
    SaveProfile,
    save_data_from_dict,
    save_data_from_json,
    save_data_to_dict,
    save_data_to_json,
)


def _profile(profile_id: str, display_name: str) -> dict[str, object]:
    return {
        "profile_id": profile_id,
        "display_name": display_name,
        "unlocked_nodes": ["world_1_node_1"],
        "unlocked_worlds": ["world_1"],
        "collected_mote_ids": [],
        "best_times_ms": {},
        "clear_counts": {},
        "discovered_abilities": [],
        "challenge_rewards": [],
        "play_time_ms": 0,
        "last_played_stage": None,
    }


def _payload() -> dict[str, object]:
    return {
        "save_version": 2,
        "campaign_version": "1.0",
        "profiles": [
            _profile("profile_1", "Sprig 1"),
            _profile("profile_2", "Sprig 2"),
            _profile("profile_3", "Sprig 3"),
        ],
        "settings": {
            "display": {"fullscreen": False, "integer_scaling": False},
            "audio": {
                "master_volume": 1.0,
                "music_volume": 0.8,
                "sfx_volume": 0.9,
                "muted": False,
            },
            "accessibility": {
                "screen_shake": True,
                "reduced_motion": False,
                "draw_toggle": False,
                "guard_toggle": False,
            },
            "language": "en",
            "controls": {
                "keyboard_p1_preset": "wasd",
                "keyboard_p2_preset": "arrows",
                "gamepad_mapping": "standard",
            },
        },
        "prototype_imported": False,
    }


def test_default_save_has_exactly_three_safe_profiles() -> None:
    data = SaveData()

    assert data.save_version == 2
    assert data.campaign_version == "1.0"
    assert tuple(profile.profile_id for profile in data.profiles) == (
        "profile_1",
        "profile_2",
        "profile_3",
    )
    assert all(profile.unlocked_worlds == frozenset({"world_1"}) for profile in data.profiles)
    assert all(profile.unlocked_nodes == frozenset({"world_1_node_1"}) for profile in data.profiles)


def test_save_models_and_nested_mappings_are_immutable_copies() -> None:
    best_times = {"world_1_stage_1": 1000}
    profile = SaveProfile("profile_1", "Breeze", best_times_ms=best_times)
    best_times["world_1_stage_1"] = 1

    assert profile.best_times_ms == {"world_1_stage_1": 1000}
    with pytest.raises(TypeError):
        profile.best_times_ms["world_1_stage_1"] = 2  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        profile.display_name = "Gust"  # type: ignore[misc]


@pytest.mark.parametrize("value", [-0.01, 1.01, math.nan, math.inf, -math.inf, True, "0.5"])
def test_audio_ranges_require_finite_real_numbers(value: object) -> None:
    with pytest.raises(ValueError, match="master_volume"):
        AudioSettings(master_volume=value)  # type: ignore[arg-type]


def test_settings_require_exact_boolean_and_string_types() -> None:
    with pytest.raises(ValueError, match="fullscreen"):
        DisplaySettings(fullscreen=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="screen_shake"):
        AccessibilitySettings(screen_shake="yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="keyboard_p1_preset"):
        ControlSettings(keyboard_p1_preset=" ")
    with pytest.raises(ValueError, match="language"):
        GlobalSettings(language="jp")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update(unknown=True), "unknown save fields"),
        (lambda payload: payload["profiles"][0].update(unknown=True), "unknown profile fields"),  # type: ignore[index,union-attr]
        (lambda payload: payload["settings"].update(unknown=True), "unknown settings fields"),  # type: ignore[union-attr]
        (
            lambda payload: payload["settings"]["display"].update(unknown=True),  # type: ignore[index,union-attr]
            "unknown display settings fields",
        ),
        (
            lambda payload: payload["settings"]["audio"].update(unknown=True),  # type: ignore[index,union-attr]
            "unknown audio settings fields",
        ),
        (
            lambda payload: payload["settings"]["accessibility"].update(unknown=True),  # type: ignore[index,union-attr]
            "unknown accessibility settings fields",
        ),
        (
            lambda payload: payload["settings"]["controls"].update(unknown=True),  # type: ignore[index,union-attr]
            "unknown control settings fields",
        ),
    ],
)
def test_save_rejects_unknown_fields_at_every_schema_level(
    mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        save_data_from_dict(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("save_version"),
        lambda payload: payload.pop("campaign_version"),
        lambda payload: payload.pop("profiles"),
        lambda payload: payload["profiles"][0].pop("profile_id"),  # type: ignore[index,union-attr]
        lambda payload: payload["profiles"][0].pop("display_name"),  # type: ignore[index,union-attr]
    ],
)
def test_save_rejects_missing_identity_fields(mutate: Callable[[dict[str, object]], object]) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(ValueError, match="required"):
        save_data_from_dict(payload)


@pytest.mark.parametrize(
    "profiles",
    [None, {}, [], [_profile("profile_1", "Sprig 1")], ["one", "two", "three"]],
)
def test_save_rejects_wrong_profile_shapes(profiles: object) -> None:
    payload = _payload()
    payload["profiles"] = profiles

    with pytest.raises(ValueError, match="profiles|profile"):
        save_data_from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("save_version", True),
        ("prototype_imported", 1),
    ],
)
def test_save_rejects_root_type_confusion(field: str, value: object) -> None:
    payload = _payload()
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        save_data_from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("play_time_ms", True),
        ("play_time_ms", -1),
        ("best_times_ms", {"world_1_stage_1": True}),
        ("best_times_ms", {"world_1_stage_1": -1}),
        ("clear_counts", {"world_1_node_1": True}),
        ("clear_counts", {"world_1_node_1": -1}),
    ],
)
def test_profile_rejects_boolean_and_negative_counters_or_times(field: str, value: object) -> None:
    payload = _payload()
    payload["profiles"][0][field] = value  # type: ignore[index]

    with pytest.raises(ValueError, match=field):
        save_data_from_dict(payload)


@pytest.mark.parametrize("display_name", ["", " ", " Breeze", "Breeze ", "x" * 17, 7])
def test_profile_names_must_be_trimmed_strings_of_at_most_sixteen_characters(display_name: object) -> None:
    payload = _payload()
    payload["profiles"][0]["display_name"] = display_name  # type: ignore[index]

    with pytest.raises(ValueError, match="display_name"):
        save_data_from_dict(payload)


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("unlocked_nodes", ["world_1_node_1", "world_1_node_1"]),
        ("unlocked_worlds", [""]),
        ("collected_mote_ids", ["world_1_stage_1:mote:1", "world_1_stage_1:mote:1"]),
        ("discovered_abilities", [" "]),
        ("challenge_rewards", [1]),
    ],
)
def test_profile_rejects_duplicate_blank_or_non_string_ids(field: str, values: object) -> None:
    payload = _payload()
    payload["profiles"][0][field] = values  # type: ignore[index]

    with pytest.raises(ValueError, match=field):
        save_data_from_dict(payload)


def test_profile_ids_must_be_unique_and_in_slot_order() -> None:
    payload = _payload()
    payload["profiles"][1]["profile_id"] = "profile_1"  # type: ignore[index]

    with pytest.raises(ValueError, match="profile_1, profile_2, profile_3"):
        save_data_from_dict(payload)


@pytest.mark.parametrize("value", [None, [], "settings", {"display": []}])
def test_save_rejects_wrong_settings_shapes(value: object) -> None:
    payload = _payload()
    payload["settings"] = value

    with pytest.raises(ValueError, match="settings"):
        save_data_from_dict(payload)


@pytest.mark.parametrize("raw", ["[]", "null", "true", "2", '"save"'])
def test_non_object_json_is_rejected_with_an_actionable_value_error(raw: str) -> None:
    with pytest.raises(ValueError, match="save must be an object"):
        save_data_from_json(raw)


def test_invalid_json_and_duplicate_json_fields_are_value_errors() -> None:
    with pytest.raises(ValueError, match="save JSON is invalid"):
        save_data_from_json("{broken")
    with pytest.raises(ValueError, match="duplicate JSON field: save_version"):
        save_data_from_json('{"save_version":2,"save_version":2}')


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_constants_are_rejected_before_model_construction(constant: str) -> None:
    raw = save_data_to_json(SaveData()).replace('"master_volume":1.0', f'"master_volume":{constant}')

    with pytest.raises(ValueError, match="non-finite JSON number"):
        save_data_from_json(raw)


def test_roundtrip_preserves_all_settings_and_emits_canonical_order() -> None:
    data = SaveData(
        settings=GlobalSettings(
            display=DisplaySettings(fullscreen=True, integer_scaling=True),
            audio=AudioSettings(master_volume=0.25, music_volume=0.5, sfx_volume=0.75, muted=True),
            accessibility=AccessibilitySettings(
                screen_shake=False,
                reduced_motion=True,
                draw_toggle=True,
                guard_toggle=True,
            ),
            language="ko",
            controls=ControlSettings("ijkl", "arrows", "southpaw"),
        ),
        profiles=(
            SaveProfile(
                "profile_1",
                "Breeze",
                collected_mote_ids=frozenset(
                    {"world_1_stage_1:mote:2", "world_1_stage_1:mote:1"}
                ),
                best_times_ms={"world_1_stage_2": 9000, "world_1_stage_1": 10000},
            ),
            SaveProfile("profile_2", "Gust"),
            SaveProfile("profile_3", "Gale"),
        ),
        prototype_imported=True,
    )

    raw = save_data_to_json(data)

    assert raw == save_data_to_json(data)
    assert json.loads(raw)["profiles"][0]["collected_mote_ids"] == [
        "world_1_stage_1:mote:1",
        "world_1_stage_1:mote:2",
    ]
    assert save_data_from_json(raw) == data
    assert save_data_to_dict(save_data_from_dict(save_data_to_dict(data))) == save_data_to_dict(data)
