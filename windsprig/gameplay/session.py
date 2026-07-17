"""Own explicit stage-flow phases above the deterministic ECS runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from windsprig.config import GameConfig
from windsprig.content.loader import StageSpec
from windsprig.core.events import GameEvent
from windsprig.gameplay.abilities import AbilityRegistry
from windsprig.gameplay.runtime import StageRuntime
from windsprig.gameplay.snapshot import (
    StageFrame,
    StageOutcome,
    StageResult,
    StageSnapshot,
)
from windsprig.input.commands import InputFrame
from windsprig.input.roster import ActivePlayer


class SessionPhase(StrEnum):
    """Explicit stage-flow phase controlling simulation and menu authority."""

    INTRO = "intro"
    PLAYING = "playing"
    PAUSED = "paused"
    VICTORY = "victory"
    DEFEAT = "defeat"
    RESULTS = "results"
    CLOSED = "closed"


class SessionAction(StrEnum):
    """Complete public action vocabulary accepted by a gameplay session."""

    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    SHOW_RESULTS = "show_results"
    RETRY_CHECKPOINT = "retry_checkpoint"
    RETRY_STAGE = "retry_stage"
    REPLAY_STAGE = "replay_stage"
    NEXT_STAGE = "next_stage"
    RETURN_TO_MAP = "return_to_map"


class SessionNavigation(StrEnum):
    """Frozen destination handed to the application after session closure."""

    NEXT_STAGE = "next_stage"
    WORLD_MAP = "world_map"


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable stage-flow state consumed by presentation controllers."""

    phase: SessionPhase
    stage: StageSnapshot
    result: StageResult | None
    allowed_actions: tuple[SessionAction, ...]
    navigation: SessionNavigation | None


ALLOWED_ACTIONS: Mapping[SessionPhase, tuple[SessionAction, ...]] = MappingProxyType(
    {
        SessionPhase.INTRO: (SessionAction.START, SessionAction.RETURN_TO_MAP),
        SessionPhase.PLAYING: (SessionAction.PAUSE,),
        SessionPhase.PAUSED: (
            SessionAction.RESUME,
            SessionAction.RETRY_STAGE,
            SessionAction.RETURN_TO_MAP,
        ),
        SessionPhase.VICTORY: (SessionAction.SHOW_RESULTS,),
        SessionPhase.DEFEAT: (
            SessionAction.RETRY_CHECKPOINT,
            SessionAction.RETRY_STAGE,
            SessionAction.RETURN_TO_MAP,
        ),
        SessionPhase.RESULTS: (
            SessionAction.NEXT_STAGE,
            SessionAction.REPLAY_STAGE,
            SessionAction.RETURN_TO_MAP,
        ),
        SessionPhase.CLOSED: (),
    }
)

_Transition = tuple[SessionPhase, SessionNavigation | None]
_TRANSITIONS: Mapping[tuple[SessionPhase, SessionAction], _Transition] = MappingProxyType(
    {
        (SessionPhase.INTRO, SessionAction.START): (SessionPhase.PLAYING, None),
        (SessionPhase.INTRO, SessionAction.RETURN_TO_MAP): (
            SessionPhase.CLOSED,
            SessionNavigation.WORLD_MAP,
        ),
        (SessionPhase.PLAYING, SessionAction.PAUSE): (SessionPhase.PAUSED, None),
        (SessionPhase.PAUSED, SessionAction.RESUME): (SessionPhase.PLAYING, None),
        (SessionPhase.PAUSED, SessionAction.RETRY_STAGE): (SessionPhase.PLAYING, None),
        (SessionPhase.PAUSED, SessionAction.RETURN_TO_MAP): (
            SessionPhase.CLOSED,
            SessionNavigation.WORLD_MAP,
        ),
        (SessionPhase.VICTORY, SessionAction.SHOW_RESULTS): (SessionPhase.RESULTS, None),
        (SessionPhase.DEFEAT, SessionAction.RETRY_CHECKPOINT): (SessionPhase.PLAYING, None),
        (SessionPhase.DEFEAT, SessionAction.RETRY_STAGE): (SessionPhase.PLAYING, None),
        (SessionPhase.DEFEAT, SessionAction.RETURN_TO_MAP): (
            SessionPhase.CLOSED,
            SessionNavigation.WORLD_MAP,
        ),
        (SessionPhase.RESULTS, SessionAction.NEXT_STAGE): (
            SessionPhase.CLOSED,
            SessionNavigation.NEXT_STAGE,
        ),
        (SessionPhase.RESULTS, SessionAction.REPLAY_STAGE): (SessionPhase.PLAYING, None),
        (SessionPhase.RESULTS, SessionAction.RETURN_TO_MAP): (
            SessionPhase.CLOSED,
            SessionNavigation.WORLD_MAP,
        ),
    }
)


class GameSession:
    """Coordinate stage simulation, explicit choices, and frozen navigation."""

    def __init__(self, runtime: StageRuntime) -> None:
        self.runtime = runtime
        self._phase = SessionPhase.INTRO
        self._navigation: SessionNavigation | None = None
        self._last_frame: StageFrame | None = None

    @classmethod
    def create(
        cls,
        config: GameConfig,
        stage: StageSpec,
        ability_registry: AbilityRegistry,
        active_players: Sequence[ActivePlayer],
        seed: int,
    ) -> GameSession:
        """Create an introduction-phase session around one production runtime."""
        return cls(StageRuntime(config, stage, ability_registry, active_players, seed))

    @property
    def phase(self) -> SessionPhase:
        """Return the current explicit stage-flow phase."""
        return self._phase

    @property
    def navigation(self) -> SessionNavigation | None:
        """Return the destination frozen when this session closed."""
        return self._navigation

    @property
    def last_frame(self) -> StageFrame | None:
        """Return the last simulated frame, including its immutable events."""
        return self._last_frame

    def step(self, input_frame: InputFrame) -> SessionSnapshot:
        """Advance exactly one runtime step only while actively playing."""
        if self._phase is not SessionPhase.PLAYING:
            return self.snapshot()
        frame = self.runtime.step(input_frame)
        self._last_frame = frame
        self._synchronize_outcome(frame.view.outcome)
        return self.snapshot()

    def dispatch(self, action: SessionAction) -> SessionSnapshot:
        """Apply one legal explicit action without partial phase transitions."""
        if type(action) is not SessionAction:
            raise TypeError("action must be a SessionAction")
        allowed_actions = self._allowed_actions()
        if action not in allowed_actions:
            if action is SessionAction.RETRY_CHECKPOINT and self._phase is SessionPhase.DEFEAT:
                raise ValueError("checkpoint retry is unavailable")
            raise ValueError(f"{action.value} is not allowed from {self._phase.value}")

        target_phase, target_navigation = _TRANSITIONS[(self._phase, action)]
        target_actions = self._allowed_actions_for(target_phase)
        # Retry effects must succeed before the visible phase commits.
        if action is SessionAction.RETRY_CHECKPOINT:
            stage = self.runtime.retry_from_checkpoint()
            result = None
        elif action in {SessionAction.RETRY_STAGE, SessionAction.REPLAY_STAGE}:
            stage = self.runtime.reset_stage()
            result = None
        else:
            stage = self.runtime.snapshot()
            result = self.runtime.result

        prepared = SessionSnapshot(
            phase=target_phase,
            stage=stage,
            result=result,
            allowed_actions=target_actions,
            navigation=target_navigation,
        )

        if action in {
            SessionAction.RETRY_CHECKPOINT,
            SessionAction.RETRY_STAGE,
            SessionAction.REPLAY_STAGE,
        }:
            self._last_frame = None
        self._phase = target_phase
        self._navigation = target_navigation
        return prepared

    def sync_active_players(
        self,
        active_players: Sequence[ActivePlayer],
    ) -> tuple[GameEvent, ...]:
        """Delegate roster changes only from introduction or pause lobbies."""
        if self._phase not in {SessionPhase.INTRO, SessionPhase.PAUSED}:
            raise ValueError(f"roster changes are not allowed from {self._phase.value}")
        return self.runtime.sync_active_players(active_players)

    def snapshot(self) -> SessionSnapshot:
        """Return current session state without stepping or draining events."""
        return SessionSnapshot(
            phase=self._phase,
            stage=self.runtime.snapshot(),
            result=self.runtime.result,
            allowed_actions=self._allowed_actions(),
            navigation=self._navigation,
        )

    def _allowed_actions(self) -> tuple[SessionAction, ...]:
        return self._allowed_actions_for(self._phase)

    def _allowed_actions_for(
        self,
        phase: SessionPhase,
    ) -> tuple[SessionAction, ...]:
        actions = ALLOWED_ACTIONS[phase]
        if phase is SessionPhase.DEFEAT and not self.runtime.can_retry_checkpoint:
            return tuple(
                action for action in actions if action is not SessionAction.RETRY_CHECKPOINT
            )
        return actions

    def _synchronize_outcome(self, outcome: StageOutcome | None = None) -> None:
        if self._phase is not SessionPhase.PLAYING:
            return
        current_outcome = self.runtime.snapshot().outcome if outcome is None else outcome
        if current_outcome is StageOutcome.COMPLETED:
            self._phase = SessionPhase.VICTORY
        elif current_outcome is StageOutcome.FAILED:
            self._phase = SessionPhase.DEFEAT
