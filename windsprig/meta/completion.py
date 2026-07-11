"""Mutable session completion state expressed in save-v2 identities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .save_models import _id_frozenset, _identifier, _immutable_int_map, _strict_int


@dataclass(slots=True)
class CompletionTracker:
    """Track session progression using the same stable vocabulary as save v2."""

    cleared_nodes: set[str] = field(default_factory=set)
    collected_mote_ids: set[str] = field(default_factory=set)
    challenge_rewards: set[str] = field(default_factory=set)
    best_times_ms: dict[str, int] = field(default_factory=dict)
    clear_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cleared_nodes = set(_id_frozenset(self.cleared_nodes, "cleared_nodes"))
        self.collected_mote_ids = set(
            _id_frozenset(self.collected_mote_ids, "collected_mote_ids")
        )
        self.challenge_rewards = set(_id_frozenset(self.challenge_rewards, "challenge_rewards"))
        self.best_times_ms = self._mutable_int_map(self.best_times_ms, "best_times_ms")
        self.clear_counts = self._mutable_int_map(self.clear_counts, "clear_counts")

    @staticmethod
    def _mutable_int_map(payload: Mapping[str, int], name: str) -> dict[str, int]:
        return dict(_immutable_int_map(payload, name))

    def mark_stage_clear(self, node_id: str, stage_id: str, elapsed_ms: int) -> None:
        """Unlock a node while retaining stage-keyed best time and replay count."""

        node_id = _identifier("node_id", node_id)
        stage_id = _identifier("stage_id", stage_id)
        elapsed_ms = _strict_int("elapsed_ms", elapsed_ms)
        self.cleared_nodes.add(node_id)
        previous = self.best_times_ms.get(stage_id)
        self.best_times_ms[stage_id] = elapsed_ms if previous is None else min(previous, elapsed_ms)
        self.clear_counts[stage_id] = self.clear_counts.get(stage_id, 0) + 1

    def collect_mote(self, mote_id: str) -> None:
        """Record one stable mote ID idempotently."""

        self.collected_mote_ids.add(_identifier("mote_id", mote_id))
