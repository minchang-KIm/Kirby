"""Immutable save-v2 values with strict, canonical JSON conversion."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, NoReturn, cast

Language = Literal["en", "ko"]


def _strict_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _strict_int(name: str, value: object, *, non_negative: bool = True) -> int:
    # bool is an int subclass, but accepting it would let malformed JSON alter counters or versions.
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    number = value
    if non_negative and number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _volume(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between zero and one")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be a finite number between zero and one")
    return number


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a non-blank trimmed string")
    return value


def _profile_name(name: str, value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 16 or value != value.strip():
        raise ValueError(f"{name} must contain 1 to 16 trimmed characters")
    return value


def _object(payload: object, allowed: frozenset[str], name: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    if any(not isinstance(key, str) for key in payload):
        raise ValueError(f"{name} field names must be strings")
    raw = cast(dict[str, object], payload)
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"unknown {name} fields: {unknown}")
    return dict(raw)


def _require_fields(raw: Mapping[str, object], required: frozenset[str], name: str) -> None:
    missing = sorted(required - set(raw))
    if len(missing) == 1:
        raise ValueError(f"{name} {missing[0]} is required")
    if missing:
        raise ValueError(f"{name} required fields are missing: {missing}")


def _id_frozenset(payload: object, name: str) -> frozenset[str]:
    if isinstance(payload, (str, bytes)) or not isinstance(payload, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection of IDs")
    values = tuple(_identifier(f"{name} ID", value) for value in payload)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicate IDs")
    return frozenset(values)


def _id_list(payload: object, name: str) -> frozenset[str]:
    if not isinstance(payload, list):
        raise ValueError(f"{name} must be a list of IDs")
    return _id_frozenset(payload, name)


def _immutable_int_map(payload: object, name: str) -> Mapping[str, int]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be an object")
    values: dict[str, int] = {}
    for raw_key, raw_value in payload.items():
        key = _identifier(f"{name} key", raw_key)
        values[key] = _strict_int(f"{name}[{key}]", raw_value)
    return MappingProxyType(dict(sorted(values.items())))


@dataclass(frozen=True, slots=True)
class DisplaySettings:
    """Display preferences shared by all three local profiles."""

    fullscreen: bool = False
    integer_scaling: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "fullscreen", _strict_bool("fullscreen", self.fullscreen))
        object.__setattr__(self, "integer_scaling", _strict_bool("integer_scaling", self.integer_scaling))


@dataclass(frozen=True, slots=True)
class AudioSettings:
    """Finite normalized volume and mute preferences."""

    master_volume: float = 1.0
    music_volume: float = 0.8
    sfx_volume: float = 0.9
    muted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "master_volume", _volume("master_volume", self.master_volume))
        object.__setattr__(self, "music_volume", _volume("music_volume", self.music_volume))
        object.__setattr__(self, "sfx_volume", _volume("sfx_volume", self.sfx_volume))
        object.__setattr__(self, "muted", _strict_bool("muted", self.muted))


@dataclass(frozen=True, slots=True)
class AccessibilitySettings:
    """Accessibility preferences that must survive platform changes."""

    screen_shake: bool = True
    reduced_motion: bool = False
    draw_toggle: bool = False
    guard_toggle: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "screen_shake", _strict_bool("screen_shake", self.screen_shake))
        object.__setattr__(self, "reduced_motion", _strict_bool("reduced_motion", self.reduced_motion))
        object.__setattr__(self, "draw_toggle", _strict_bool("draw_toggle", self.draw_toggle))
        object.__setattr__(self, "guard_toggle", _strict_bool("guard_toggle", self.guard_toggle))


@dataclass(frozen=True, slots=True)
class ControlSettings:
    """Stable preset identifiers for keyboard and gamepad controls."""

    keyboard_p1_preset: str = "wasd"
    keyboard_p2_preset: str = "arrows"
    gamepad_mapping: str = "standard"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "keyboard_p1_preset",
            _identifier("keyboard_p1_preset", self.keyboard_p1_preset),
        )
        object.__setattr__(
            self,
            "keyboard_p2_preset",
            _identifier("keyboard_p2_preset", self.keyboard_p2_preset),
        )
        object.__setattr__(self, "gamepad_mapping", _identifier("gamepad_mapping", self.gamepad_mapping))


@dataclass(frozen=True, slots=True)
class GlobalSettings:
    """Settings shared by every save profile."""

    display: DisplaySettings = field(default_factory=DisplaySettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    accessibility: AccessibilitySettings = field(default_factory=AccessibilitySettings)
    language: Language = "en"
    controls: ControlSettings = field(default_factory=ControlSettings)

    def __post_init__(self) -> None:
        if not isinstance(self.display, DisplaySettings):
            raise ValueError("display must be DisplaySettings")
        if not isinstance(self.audio, AudioSettings):
            raise ValueError("audio must be AudioSettings")
        if not isinstance(self.accessibility, AccessibilitySettings):
            raise ValueError("accessibility must be AccessibilitySettings")
        if self.language not in ("en", "ko"):
            raise ValueError("language must be en or ko")
        if not isinstance(self.controls, ControlSettings):
            raise ValueError("controls must be ControlSettings")


@dataclass(frozen=True, slots=True)
class SaveProfile:
    """One immutable progression slot identified independently of its display name."""

    profile_id: str
    display_name: str
    unlocked_nodes: frozenset[str] = frozenset({"world_1_node_1"})
    unlocked_worlds: frozenset[str] = frozenset({"world_1"})
    collected_mote_ids: frozenset[str] = frozenset()
    best_times_ms: Mapping[str, int] = field(default_factory=dict)
    clear_counts: Mapping[str, int] = field(default_factory=dict)
    discovered_abilities: frozenset[str] = frozenset()
    challenge_rewards: frozenset[str] = frozenset()
    play_time_ms: int = 0
    last_played_stage: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _identifier("profile_id", self.profile_id))
        object.__setattr__(self, "display_name", _profile_name("display_name", self.display_name))
        object.__setattr__(self, "unlocked_nodes", _id_frozenset(self.unlocked_nodes, "unlocked_nodes"))
        object.__setattr__(self, "unlocked_worlds", _id_frozenset(self.unlocked_worlds, "unlocked_worlds"))
        object.__setattr__(
            self,
            "collected_mote_ids",
            _id_frozenset(self.collected_mote_ids, "collected_mote_ids"),
        )
        object.__setattr__(self, "best_times_ms", _immutable_int_map(self.best_times_ms, "best_times_ms"))
        object.__setattr__(self, "clear_counts", _immutable_int_map(self.clear_counts, "clear_counts"))
        object.__setattr__(
            self,
            "discovered_abilities",
            _id_frozenset(self.discovered_abilities, "discovered_abilities"),
        )
        object.__setattr__(
            self,
            "challenge_rewards",
            _id_frozenset(self.challenge_rewards, "challenge_rewards"),
        )
        object.__setattr__(self, "play_time_ms", _strict_int("play_time_ms", self.play_time_ms))
        if self.last_played_stage is not None:
            object.__setattr__(
                self,
                "last_played_stage",
                _identifier("last_played_stage", self.last_played_stage),
            )


def default_profiles() -> tuple[SaveProfile, SaveProfile, SaveProfile]:
    """Return the three safe progression slots required by save v2."""

    return (
        SaveProfile(profile_id="profile_1", display_name="Sprig 1"),
        SaveProfile(profile_id="profile_2", display_name="Sprig 2"),
        SaveProfile(profile_id="profile_3", display_name="Sprig 3"),
    )


@dataclass(frozen=True, slots=True)
class SaveData:
    """The complete immutable save-v2 document."""

    save_version: int = 2
    campaign_version: str = "1.0"
    profiles: tuple[SaveProfile, SaveProfile, SaveProfile] = field(default_factory=default_profiles)
    settings: GlobalSettings = field(default_factory=GlobalSettings)
    prototype_imported: bool = False

    def __post_init__(self) -> None:
        version = _strict_int("save_version", self.save_version)
        if version != 2:
            raise ValueError("save_version must be 2")
        object.__setattr__(self, "campaign_version", _identifier("campaign_version", self.campaign_version))
        if not isinstance(self.profiles, tuple) or len(self.profiles) != 3:
            raise ValueError("profiles must be a tuple containing exactly three SaveProfile values")
        if any(not isinstance(profile, SaveProfile) for profile in self.profiles):
            raise ValueError("profiles must contain only SaveProfile values")
        ids = tuple(profile.profile_id for profile in self.profiles)
        if ids != ("profile_1", "profile_2", "profile_3"):
            raise ValueError("profiles must use profile_1, profile_2, profile_3 in slot order")
        if not isinstance(self.settings, GlobalSettings):
            raise ValueError("settings must be GlobalSettings")
        object.__setattr__(
            self,
            "prototype_imported",
            _strict_bool("prototype_imported", self.prototype_imported),
        )


def save_data_to_dict(data: SaveData) -> dict[str, object]:
    """Return a deterministic JSON-compatible representation of validated save data."""

    if not isinstance(data, SaveData):
        raise ValueError("data must be SaveData")
    return {
        "save_version": data.save_version,
        "campaign_version": data.campaign_version,
        "profiles": [
            {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "unlocked_nodes": sorted(profile.unlocked_nodes),
                "unlocked_worlds": sorted(profile.unlocked_worlds),
                "collected_mote_ids": sorted(profile.collected_mote_ids),
                "best_times_ms": dict(profile.best_times_ms),
                "clear_counts": dict(profile.clear_counts),
                "discovered_abilities": sorted(profile.discovered_abilities),
                "challenge_rewards": sorted(profile.challenge_rewards),
                "play_time_ms": profile.play_time_ms,
                "last_played_stage": profile.last_played_stage,
            }
            for profile in data.profiles
        ],
        "settings": {
            "display": {
                "fullscreen": data.settings.display.fullscreen,
                "integer_scaling": data.settings.display.integer_scaling,
            },
            "audio": {
                "master_volume": data.settings.audio.master_volume,
                "music_volume": data.settings.audio.music_volume,
                "sfx_volume": data.settings.audio.sfx_volume,
                "muted": data.settings.audio.muted,
            },
            "accessibility": {
                "screen_shake": data.settings.accessibility.screen_shake,
                "reduced_motion": data.settings.accessibility.reduced_motion,
                "draw_toggle": data.settings.accessibility.draw_toggle,
                "guard_toggle": data.settings.accessibility.guard_toggle,
            },
            "language": data.settings.language,
            "controls": {
                "keyboard_p1_preset": data.settings.controls.keyboard_p1_preset,
                "keyboard_p2_preset": data.settings.controls.keyboard_p2_preset,
                "gamepad_mapping": data.settings.controls.gamepad_mapping,
            },
        },
        "prototype_imported": data.prototype_imported,
    }


_DISPLAY_FIELDS = frozenset({"fullscreen", "integer_scaling"})
_AUDIO_FIELDS = frozenset({"master_volume", "music_volume", "sfx_volume", "muted"})
_ACCESSIBILITY_FIELDS = frozenset({"screen_shake", "reduced_motion", "draw_toggle", "guard_toggle"})
_CONTROL_FIELDS = frozenset({"keyboard_p1_preset", "keyboard_p2_preset", "gamepad_mapping"})
_SETTINGS_FIELDS = frozenset({"display", "audio", "accessibility", "language", "controls"})
_PROFILE_FIELDS = frozenset(
    {
        "profile_id",
        "display_name",
        "unlocked_nodes",
        "unlocked_worlds",
        "collected_mote_ids",
        "best_times_ms",
        "clear_counts",
        "discovered_abilities",
        "challenge_rewards",
        "play_time_ms",
        "last_played_stage",
    }
)
_SAVE_FIELDS = frozenset({"save_version", "campaign_version", "profiles", "settings", "prototype_imported"})


def _settings_from_dict(payload: object) -> GlobalSettings:
    raw = _object(payload, _SETTINGS_FIELDS, "settings")
    display = _object(raw.get("display", {}), _DISPLAY_FIELDS, "display settings")
    audio = _object(raw.get("audio", {}), _AUDIO_FIELDS, "audio settings")
    accessibility = _object(
        raw.get("accessibility", {}),
        _ACCESSIBILITY_FIELDS,
        "accessibility settings",
    )
    controls = _object(raw.get("controls", {}), _CONTROL_FIELDS, "control settings")
    language = raw.get("language", "en")
    if language not in ("en", "ko"):
        raise ValueError("language must be en or ko")
    return GlobalSettings(
        display=DisplaySettings(
            fullscreen=_strict_bool("fullscreen", display.get("fullscreen", False)),
            integer_scaling=_strict_bool("integer_scaling", display.get("integer_scaling", False)),
        ),
        audio=AudioSettings(
            master_volume=_volume("master_volume", audio.get("master_volume", 1.0)),
            music_volume=_volume("music_volume", audio.get("music_volume", 0.8)),
            sfx_volume=_volume("sfx_volume", audio.get("sfx_volume", 0.9)),
            muted=_strict_bool("muted", audio.get("muted", False)),
        ),
        accessibility=AccessibilitySettings(
            screen_shake=_strict_bool("screen_shake", accessibility.get("screen_shake", True)),
            reduced_motion=_strict_bool("reduced_motion", accessibility.get("reduced_motion", False)),
            draw_toggle=_strict_bool("draw_toggle", accessibility.get("draw_toggle", False)),
            guard_toggle=_strict_bool("guard_toggle", accessibility.get("guard_toggle", False)),
        ),
        language=language,
        controls=ControlSettings(
            keyboard_p1_preset=_identifier(
                "keyboard_p1_preset",
                controls.get("keyboard_p1_preset", "wasd"),
            ),
            keyboard_p2_preset=_identifier(
                "keyboard_p2_preset",
                controls.get("keyboard_p2_preset", "arrows"),
            ),
            gamepad_mapping=_identifier("gamepad_mapping", controls.get("gamepad_mapping", "standard")),
        ),
    )


def _profile_from_dict(payload: object) -> SaveProfile:
    raw = _object(payload, _PROFILE_FIELDS, "profile")
    _require_fields(raw, frozenset({"profile_id", "display_name"}), "profile")
    last_played_stage = raw.get("last_played_stage")
    if last_played_stage is not None:
        last_played_stage = _identifier("last_played_stage", last_played_stage)
    return SaveProfile(
        profile_id=_identifier("profile_id", raw["profile_id"]),
        display_name=_profile_name("display_name", raw["display_name"]),
        unlocked_nodes=_id_list(raw.get("unlocked_nodes", ["world_1_node_1"]), "unlocked_nodes"),
        unlocked_worlds=_id_list(raw.get("unlocked_worlds", ["world_1"]), "unlocked_worlds"),
        collected_mote_ids=_id_list(raw.get("collected_mote_ids", []), "collected_mote_ids"),
        best_times_ms=_immutable_int_map(raw.get("best_times_ms", {}), "best_times_ms"),
        clear_counts=_immutable_int_map(raw.get("clear_counts", {}), "clear_counts"),
        discovered_abilities=_id_list(
            raw.get("discovered_abilities", []),
            "discovered_abilities",
        ),
        challenge_rewards=_id_list(raw.get("challenge_rewards", []), "challenge_rewards"),
        play_time_ms=_strict_int("play_time_ms", raw.get("play_time_ms", 0)),
        last_played_stage=last_played_stage,
    )


def save_data_from_dict(payload: object) -> SaveData:
    """Validate an untrusted JSON-compatible object as save v2 or raise ``ValueError``."""

    raw = _object(payload, _SAVE_FIELDS, "save")
    _require_fields(raw, frozenset({"save_version", "campaign_version", "profiles"}), "save")
    profiles_raw = raw["profiles"]
    if not isinstance(profiles_raw, list) or len(profiles_raw) != 3:
        raise ValueError("profiles must be a list containing exactly three profile objects")
    profiles = tuple(_profile_from_dict(profile) for profile in profiles_raw)
    version = _strict_int("save_version", raw["save_version"])
    campaign_version = _identifier("campaign_version", raw["campaign_version"])
    return SaveData(
        save_version=version,
        campaign_version=campaign_version,
        profiles=(profiles[0], profiles[1], profiles[2]),
        settings=_settings_from_dict(raw.get("settings", {})),
        prototype_imported=_strict_bool("prototype_imported", raw.get("prototype_imported", False)),
    )


def save_data_to_json(data: SaveData, *, indent: int | None = None) -> str:
    """Serialize save v2 with stable key and collection ordering."""

    payload = save_data_to_dict(data)
    if indent is None:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def save_data_from_json(raw: str) -> SaveData:
    """Decode and validate untrusted save JSON with duplicate-key rejection."""

    if not isinstance(raw, str):
        raise ValueError("save JSON must be text")
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"save JSON is invalid at line {exc.lineno}, column {exc.colno}") from None
    except TypeError as exc:
        raise ValueError("save JSON could not be decoded") from exc
    return save_data_from_dict(payload)
