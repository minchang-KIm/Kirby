from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompletionTracker:
    cleared_nodes: set[str] = field(default_factory=set)
    energy_spheres: dict[str, int] = field(default_factory=dict)
    challenge_unlocks: set[str] = field(default_factory=set)
    best_times: dict[str, int] = field(default_factory=dict)

    def mark_stage_clear(self, node_id: str, time_ms: int) -> None:
        self.cleared_nodes.add(node_id)
        if node_id not in self.best_times:
            self.best_times[node_id] = time_ms
        else:
            self.best_times[node_id] = min(self.best_times[node_id], time_ms)

    def add_energy_spheres(self, stage_id: str, amount: int) -> None:
        self.energy_spheres[stage_id] = self.energy_spheres.get(stage_id, 0) + amount
