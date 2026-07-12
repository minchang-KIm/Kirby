"""Build immutable localized HUD facts from presentation-safe snapshots."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from windsprig.content.models import StageSpec
from windsprig.gameplay.snapshot import BossView, CameraTargetView, PlayerView, StageSnapshot
from windsprig.input.roster import ActivePlayer
from windsprig.localization import Localizer
from windsprig.platform.services import AudioStatus
from windsprig.render.camera import CameraView

_ABILITY_IDS: Final = frozenset({"bloomblade", "cinder", "voltsong", "galehook", "stoneheart", "tempest"})
_VULNERABILITIES: Final = frozenset({"vulnerable", "armored", "hidden", "invulnerable"})
BOSS_PHASE_NUMBER: Final = MappingProxyType(
    {
        "rootjaw.buried_hunger": 1,
        "rootjaw.tangled_fury": 2,
        "rootjaw.heartwood_quake": 3,
        "crucible_crab.forged_shell": 1,
        "crucible_crab.molten_lanes": 2,
        "crucible_crab.overheat": 3,
        "luma_eel.moonlit_current": 1,
        "luma_eel.decoy_tide": 2,
        "luma_eel.eclipse_spiral": 3,
        "volt_roc.storm_perch": 1,
        "volt_roc.chain_sky": 2,
        "volt_roc.tempest_dive": 3,
        "prism_warden.reflection": 1,
        "prism_warden.clone_garden": 2,
        "prism_warden.gravity_refraction": 3,
        "the_stillness.silenced_motion": 1,
        "the_stillness.stolen_systems": 2,
        "the_stillness.motion_returns": 3,
    }
)
_SAVE_STATUS_KEY: Final = {
    "ready": "save.saved",
    "saved": "save.saved",
    "saving": "save.saving",
    "failed": "save.failed",
    "retry_required": "save.failed",
    "reset_required": "save.failed",
}


def _non_empty(name: str, value: object) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


def _label(name: str, value: object, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{name} must be non-empty")
    return value


def _strict_int(name: str, value: object, *, minimum: int = 0) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _ratio(name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise TypeError(f"{name} must be a number")
    result = float(cast(int | float, value))
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return result


def _strict_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class HudPlayerVM:
    """Localized redundant identity, health, ability, and status for one slot."""

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
    hp_label: str
    hover_label: str
    status_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        slot = _strict_int("HUD player slot", self.slot, minimum=1)
        if slot > 4:
            raise ValueError("HUD player slot must be in [1, 4]")
        for name in ("label", "icon_token", "color_token", "pattern_token", "lives_label", "ability_icon"):
            object.__setattr__(self, name, _non_empty(f"HUD player {name}", getattr(self, name)))
        for name in ("ability_label", "hp_label", "hover_label"):
            object.__setattr__(self, name, _label(f"HUD player {name}", getattr(self, name)))
        if type(self.hp_segments) is not tuple or not self.hp_segments:
            raise ValueError("HUD player HP segments must be a non-empty tuple")
        if any(type(segment) is not bool for segment in self.hp_segments):
            raise TypeError("HUD player HP segments must be booleans")
        object.__setattr__(self, "ability_meter_ratio", _ratio("ability meter ratio", self.ability_meter_ratio))
        object.__setattr__(self, "hover_ratio", _ratio("hover ratio", self.hover_ratio))
        if self.captured_icon is not None:
            object.__setattr__(self, "captured_icon", _non_empty("captured icon", self.captured_icon))
        object.__setattr__(self, "captured_label", _label("captured label", self.captured_label, allow_empty=True))
        for name in ("guard_active", "dodge_active", "invulnerable_pattern"):
            object.__setattr__(self, name, _strict_bool(name, getattr(self, name)))
        if type(self.status_labels) is not tuple:
            raise TypeError("HUD status labels must be a tuple")
        for status in self.status_labels:
            _label("HUD status label", status)


@dataclass(frozen=True, slots=True)
class HudBossVM:
    """Localized boss health, phase, vulnerability pattern, and telegraph icon."""

    name: str
    phase_label: str
    hp_ratio: float
    vulnerability_pattern: str
    telegraph_icon: str | None
    telegraph_label: str | None = None
    telegraph_pattern: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _label("boss name", self.name))
        object.__setattr__(self, "phase_label", _label("boss phase label", self.phase_label))
        object.__setattr__(self, "hp_ratio", _ratio("boss HP ratio", self.hp_ratio))
        object.__setattr__(
            self,
            "vulnerability_pattern",
            _non_empty("boss vulnerability pattern", self.vulnerability_pattern),
        )
        if self.telegraph_icon is not None:
            object.__setattr__(self, "telegraph_icon", _non_empty("boss telegraph icon", self.telegraph_icon))
        for name in ("telegraph_label", "telegraph_pattern"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_empty(f"boss {name}", value))
        states = (self.telegraph_icon, self.telegraph_label, self.telegraph_pattern)
        if any(value is None for value in states) and any(value is not None for value in states):
            raise ValueError("boss telegraph icon, label, and pattern must appear together")


@dataclass(frozen=True, slots=True)
class HudCatchUpVM:
    """One edge-clamped direction cue for an outlying active player."""

    slot: int
    edge: str
    arrow: str
    edge_y: int

    def __post_init__(self) -> None:
        slot = _strict_int("catch-up cue slot", self.slot, minimum=1)
        if slot > 4:
            raise ValueError("catch-up cue slot must be in [1, 4]")
        if self.edge not in {"left", "right"}:
            raise ValueError("catch-up cue edge must be left or right")
        expected_arrow = "->" if self.edge == "left" else "<-"
        if self.arrow != expected_arrow:
            raise ValueError("catch-up cue arrow must point from the edge toward the group")
        edge_y = _strict_int("catch-up cue edge y", self.edge_y, minimum=150)
        if edge_y > 600:
            raise ValueError("catch-up cue edge y must be in [150, 600]")


@dataclass(frozen=True, slots=True)
class HudViewModel:
    """Complete canonical stage HUD with no gameplay or localization authority."""

    players: tuple[HudPlayerVM, ...]
    mote_icons: tuple[bool, bool, bool]
    gather_label: str | None
    catch_up_slots: tuple[int, ...]
    boss: HudBossVM | None
    muted_indicator: bool
    save_status_key: str
    motes_label: str
    muted_label: str
    save_status_label: str
    catch_up_cues: tuple[HudCatchUpVM, ...] = ()

    def __post_init__(self) -> None:
        if type(self.players) is not tuple or any(not isinstance(player, HudPlayerVM) for player in self.players):
            raise TypeError("HUD players must be a tuple of HudPlayerVM values")
        if not 1 <= len(self.players) <= 4:
            raise ValueError("HUD must contain one through four players")
        slots = tuple(player.slot for player in self.players)
        if slots != tuple(sorted(set(slots))):
            raise ValueError("HUD players must be unique canonical slot order")
        if type(self.mote_icons) is not tuple or len(self.mote_icons) != 3:
            raise ValueError("HUD mote icons must contain exactly three values")
        if any(type(value) is not bool for value in self.mote_icons):
            raise TypeError("HUD mote icons must be booleans")
        if self.gather_label is not None:
            object.__setattr__(self, "gather_label", _label("gather label", self.gather_label))
        if type(self.catch_up_slots) is not tuple:
            raise TypeError("HUD catch-up slots must be a tuple")
        if self.catch_up_slots != tuple(sorted(set(self.catch_up_slots))):
            raise ValueError("HUD catch-up slots must be unique canonical order")
        if any(slot not in slots for slot in self.catch_up_slots):
            raise ValueError("HUD catch-up slots must identify visible players")
        if type(self.catch_up_cues) is not tuple or any(
            not isinstance(cue, HudCatchUpVM) for cue in self.catch_up_cues
        ):
            raise TypeError("HUD catch-up cues must be a tuple of HudCatchUpVM values")
        cue_slots = tuple(cue.slot for cue in self.catch_up_cues)
        if cue_slots != self.catch_up_slots:
            raise ValueError("HUD catch-up cues must match canonical catch-up slots")
        if self.boss is not None and not isinstance(self.boss, HudBossVM):
            raise TypeError("HUD boss must be HudBossVM or None")
        object.__setattr__(self, "muted_indicator", _strict_bool("muted indicator", self.muted_indicator))
        for name in ("save_status_key", "motes_label", "save_status_label"):
            object.__setattr__(self, name, _label(name, getattr(self, name)))
        object.__setattr__(self, "muted_label", _label("muted label", self.muted_label, allow_empty=True))


def _validate_active_players(active_players: tuple[ActivePlayer, ...] | list[ActivePlayer]) -> dict[int, ActivePlayer]:
    if type(active_players) not in {tuple, list}:
        raise TypeError("active players must be a tuple or list")
    by_slot: dict[int, ActivePlayer] = {}
    for active in active_players:
        if not isinstance(active, ActivePlayer):
            raise TypeError("active players must contain ActivePlayer values")
        slot = _strict_int("active player slot", active.slot, minimum=1)
        if slot > 4 or slot in by_slot:
            raise ValueError("active player slots must be unique values in [1, 4]")
        _non_empty("active player color token", active.color_token)
        _non_empty("active player icon token", active.icon_token)
        if type(active.is_leader) is not bool:
            raise TypeError("active player leader state must be a boolean")
        by_slot[slot] = active
    if not by_slot:
        raise ValueError("active players must not be empty")
    return by_slot


def _validate_player(player: PlayerView) -> None:
    if not isinstance(player, PlayerView):
        raise TypeError("snapshot players must contain PlayerView values")
    _strict_int("player entity ID", player.entity_id, minimum=1)
    slot = _strict_int("snapshot player slot", player.slot, minimum=1)
    if slot > 4:
        raise ValueError("snapshot player slot must be in [1, 4]")
    maximum_hp = _strict_int("player maximum HP", player.maximum_hp, minimum=1)
    hp = _strict_int("player HP", player.hp)
    if hp > maximum_hp:
        raise ValueError("player HP cannot exceed maximum HP")
    _strict_int("player lives", player.lives_remaining)
    ability_meter = _strict_int("player ability meter", player.ability_meter)
    if ability_meter > 100:
        raise ValueError("player ability meter must be in [0, 100]")
    _strict_int("player ability charge", player.ability_charge_ms)
    hover_maximum = _strict_int("player maximum hover", player.hover_max_ms, minimum=1)
    hover_remaining = _strict_int("player remaining hover", player.hover_remaining_ms)
    if hover_remaining > hover_maximum:
        raise ValueError("player remaining hover cannot exceed maximum hover")
    if player.ability_id != "none" and player.ability_id not in _ABILITY_IDS:
        raise ValueError(f"unsupported player ability ID: {player.ability_id}")
    for name in ("guard_active", "dodge_active", "invulnerable"):
        _strict_bool(name, getattr(player, name))
    if player.captured_ability_id is not None and player.captured_ability_id not in _ABILITY_IDS:
        raise ValueError(f"unsupported captured ability ID: {player.captured_ability_id}")
    if player.captured_visual_id is not None:
        _non_empty("captured visual ID", player.captured_visual_id)


def _player_vm(player: PlayerView, active: ActivePlayer, tr: Localizer) -> HudPlayerVM:
    ability_label = tr.text("hud.none") if player.ability_id == "none" else tr.text(f"ability.{player.ability_id}.name")
    captured_label = ""
    captured_icon: str | None = None
    if player.captured_visual_id is not None:
        captured_ability_label = (
            tr.text(f"enemy.{player.captured_visual_id}.name")
            if player.captured_ability_id is None
            else tr.text(f"ability.{player.captured_ability_id}.name")
        )
        captured_label = tr.text("hud.captured", ability=captured_ability_label)
        captured_icon = player.captured_ability_id or "draw"
    statuses: list[str] = []
    if player.guard_active:
        statuses.append(tr.text("status.guard"))
    if player.invulnerable:
        statuses.append(tr.text("status.invulnerable"))
    return HudPlayerVM(
        slot=player.slot,
        # A slot numeral is language-neutral while icon, color, and pattern preserve identity redundantly.
        label=str(player.slot),
        icon_token=active.icon_token,
        color_token=active.color_token,
        pattern_token=f"pattern.slot-{player.slot}",
        hp_segments=tuple(index < player.hp for index in range(player.maximum_hp)),
        lives_label=tr.text("hud.lives", count=player.lives_remaining),
        ability_icon=player.ability_id if player.ability_id != "none" else "draw",
        ability_label=ability_label,
        ability_meter_ratio=player.ability_meter / 100.0,
        hover_ratio=player.hover_remaining_ms / player.hover_max_ms,
        captured_icon=captured_icon,
        captured_label=captured_label,
        guard_active=player.guard_active,
        dodge_active=player.dodge_active,
        invulnerable_pattern=player.invulnerable,
        hp_label=tr.text("hud.hp", current=player.hp, maximum=player.maximum_hp),
        hover_label=tr.text("hud.hover"),
        status_labels=tuple(statuses),
    )


def _boss_vm(boss: BossView, stage: StageSpec, tr: Localizer) -> HudBossVM:
    if stage.boss_id != boss.boss_id:
        raise ValueError("snapshot boss does not match the stage boss ID")
    _strict_int("boss entity ID", boss.entity_id, minimum=1)
    maximum_hp = _strict_int("boss maximum HP", boss.maximum_hp, minimum=1)
    hp = _strict_int("boss HP", boss.hp)
    if hp > maximum_hp:
        raise ValueError("boss HP cannot exceed maximum HP")
    phase_number = BOSS_PHASE_NUMBER.get(boss.phase_id)
    if phase_number is None:
        raise ValueError(f"unsupported boss phase ID: {boss.phase_id}")
    if boss.vulnerability_state not in _VULNERABILITIES:
        raise ValueError(f"unsupported boss vulnerability: {boss.vulnerability_state}")
    _strict_int("boss telegraph remaining time", boss.telegraph_remaining_ms)
    if boss.telegraph_id is not None:
        _non_empty("boss telegraph ID", boss.telegraph_id)
    return HudBossVM(
        name=tr.text(f"boss.{boss.boss_id}.name"),
        phase_label=tr.text("status.boss_phase", phase=phase_number),
        hp_ratio=hp / maximum_hp,
        vulnerability_pattern=f"pattern.boss.{boss.vulnerability_state}",
        telegraph_icon="attack" if boss.telegraph_id is not None else None,
        telegraph_label=tr.text("hud.boss_incoming") if boss.telegraph_id is not None else None,
        telegraph_pattern="stripes" if boss.telegraph_id is not None else None,
    )


def _catch_up_cues(snapshot: StageSnapshot, camera: CameraView) -> tuple[HudCatchUpVM, ...]:
    """Project camera outliers to stable, readable logical-canvas edges."""

    if type(snapshot.camera_targets) is not tuple or any(
        not isinstance(target, CameraTargetView) for target in snapshot.camera_targets
    ):
        raise TypeError("snapshot camera targets must be a tuple of CameraTargetView values")
    active = tuple(target for target in snapshot.camera_targets if target.enabled and target.weight > 0)
    by_slot = {target.slot: target for target in active}
    if len(by_slot) != len(active):
        raise ValueError("active camera target slots must be unique")
    total_weight = sum(target.weight for target in active)
    if not active or not math.isfinite(total_weight) or total_weight <= 0:
        if camera.catch_up_slots:
            raise ValueError("camera catch-up slots require active weighted targets")
        return ()
    center_x = sum(target.x * target.weight for target in active) / total_weight
    occupied: dict[str, list[int]] = {"left": [], "right": []}
    cues: list[HudCatchUpVM] = []
    for slot in camera.catch_up_slots:
        target = by_slot.get(slot)
        if target is None:
            raise ValueError("camera catch-up slots must identify active weighted targets")
        if target.x == center_x:
            raise ValueError("camera catch-up target must have a direction toward the group")
        edge = "left" if target.x < center_x else "right"
        desired_y = max(150, min(600, round(target.y - camera.y - 25)))
        edge_y: int | None = None
        # Search a finite logical-canvas grid instead of bouncing between two
        # occupied edge positions when three players share one direction.
        for distance in range(10):
            candidates = (desired_y,) if distance == 0 else (desired_y - distance * 54, desired_y + distance * 54)
            for candidate in candidates:
                if 150 <= candidate <= 600 and all(abs(candidate - used) >= 54 for used in occupied[edge]):
                    edge_y = candidate
                    break
            if edge_y is not None:
                break
        if edge_y is None:
            raise ValueError("catch-up cues cannot fit on the logical-canvas edge")
        occupied[edge].append(edge_y)
        cues.append(HudCatchUpVM(slot, edge, "->" if edge == "left" else "<-", edge_y))
    return tuple(cues)


def _gather_label(snapshot: StageSnapshot, active_slots: tuple[int, ...], tr: Localizer) -> str | None:
    gather = snapshot.goal_gather
    required = gather.required_slots
    if type(required) is not tuple or required != tuple(sorted(set(required))):
        raise ValueError("goal required slots must be unique canonical order")
    if any(slot not in active_slots for slot in required):
        raise ValueError("goal required slots must identify active players")
    if type(gather.at_goal_slots) is not tuple or gather.at_goal_slots != tuple(sorted(set(gather.at_goal_slots))):
        raise ValueError("goal at-goal slots must be unique canonical order")
    if any(slot not in required for slot in gather.at_goal_slots):
        raise ValueError("goal at-goal slots must identify required players")
    countdown = _strict_int("goal countdown", gather.countdown_remaining_ms)
    if gather.leader_slot is not None and gather.leader_slot not in active_slots:
        raise ValueError("goal leader slot must identify an active player")
    if type(gather.leader_confirmed) is not bool:
        raise TypeError("goal leader confirmation must be a boolean")
    if countdown == 0:
        return None
    seconds = max(1, math.ceil(countdown / 1_000))
    return tr.text("hud.gather", seconds=seconds)


def build_hud_view(
    snapshot: StageSnapshot,
    stage: StageSpec,
    active_players: tuple[ActivePlayer, ...] | list[ActivePlayer],
    camera: CameraView,
    audio_status: AudioStatus,
    save_status: str,
    tr: Localizer,
) -> HudViewModel:
    """Derive localized HUD facts without retaining or mutating caller-owned values."""

    if not isinstance(snapshot, StageSnapshot):
        raise TypeError("snapshot must be a StageSnapshot")
    if not isinstance(stage, StageSpec):
        raise TypeError("stage must be a StageSpec")
    if not isinstance(camera, CameraView):
        raise TypeError("camera must be a CameraView")
    if not isinstance(audio_status, AudioStatus):
        raise TypeError("audio status must be AudioStatus")
    if not isinstance(tr, Localizer):
        raise TypeError("tr must be a Localizer")
    if (snapshot.stage_id, snapshot.world_id, snapshot.node_id) != (stage.stage_id, stage.world_id, stage.node_id):
        raise ValueError("snapshot identity does not match stage identity")

    expected_mote_ids = tuple(f"{stage.stage_id}:mote:{index}" for index in range(1, 4))
    actual_mote_ids = tuple(mote.mote_id for mote in stage.motes)
    if actual_mote_ids != expected_mote_ids:
        raise ValueError("stage must expose exactly three stable mote IDs in numeric order")
    if type(snapshot.collected_mote_ids) is not tuple or len(snapshot.collected_mote_ids) != len(
        set(snapshot.collected_mote_ids)
    ):
        raise ValueError("snapshot collected mote IDs must be a unique tuple")
    unknown_motes = set(snapshot.collected_mote_ids) - set(expected_mote_ids)
    if unknown_motes:
        raise ValueError(f"snapshot collected mote IDs are outside this stage: {','.join(sorted(unknown_motes))}")

    active_by_slot = _validate_active_players(active_players)
    if type(snapshot.players) is not tuple:
        raise TypeError("snapshot players must be a tuple")
    players_by_slot: dict[int, PlayerView] = {}
    for player in snapshot.players:
        _validate_player(player)
        if player.slot in players_by_slot:
            raise ValueError("snapshot player slots must be unique")
        players_by_slot[player.slot] = player
    if set(players_by_slot) != set(active_by_slot):
        raise ValueError("snapshot player slots must match active player slots")
    ordered_slots = tuple(sorted(players_by_slot))
    players = tuple(_player_vm(players_by_slot[slot], active_by_slot[slot], tr) for slot in ordered_slots)

    if type(snapshot.bosses) is not tuple:
        raise TypeError("snapshot bosses must be a tuple")
    if len(snapshot.bosses) > 1:
        raise ValueError("snapshot bosses must contain at most one boss")
    if any(not isinstance(item, BossView) for item in snapshot.bosses):
        raise TypeError("snapshot boss must be a BossView")
    boss = _boss_vm(snapshot.bosses[0], stage, tr) if snapshot.bosses else None

    if type(save_status) is not str:
        raise TypeError("save status must be a string")
    save_status_key = _SAVE_STATUS_KEY.get(save_status)
    if save_status_key is None:
        raise ValueError(f"unsupported save status: {save_status}")
    if type(audio_status.ready) is not bool or type(audio_status.muted) is not bool:
        raise TypeError("audio status readiness and mute state must be booleans")
    muted = audio_status.muted or not audio_status.ready
    catch_up_slots = tuple(camera.catch_up_slots)
    if any(slot not in ordered_slots for slot in catch_up_slots):
        raise ValueError("camera catch-up slots must identify active players")
    mote_icons_values = tuple(mote_id in snapshot.collected_mote_ids for mote_id in expected_mote_ids)
    mote_icons = cast(tuple[bool, bool, bool], mote_icons_values)
    return HudViewModel(
        players=players,
        mote_icons=mote_icons,
        gather_label=_gather_label(snapshot, ordered_slots, tr),
        catch_up_slots=catch_up_slots,
        boss=boss,
        muted_indicator=muted,
        save_status_key=save_status_key,
        motes_label=tr.text("hud.motes", found=sum(mote_icons)),
        muted_label=tr.text("audio.muted_failure") if muted else "",
        save_status_label=tr.text(save_status_key),
        catch_up_cues=_catch_up_cues(snapshot, camera),
    )


__all__ = ["BOSS_PHASE_NUMBER", "HudBossVM", "HudCatchUpVM", "HudPlayerVM", "HudViewModel", "build_hud_view"]
