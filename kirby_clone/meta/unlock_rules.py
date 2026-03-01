from __future__ import annotations

from dataclasses import dataclass

from kirby_clone.content.loader import CampaignCatalog
from .completion import CompletionTracker


@dataclass
class UnlockRules:
    catalog: CampaignCatalog

    def is_node_unlocked(self, node_id: str, tracker: CompletionTracker, unlocked_worlds: set[str]) -> bool:
        for world_id, nodes in self.catalog.worlds.items():
            for node in nodes:
                if node.node_id != node_id:
                    continue
                if world_id not in unlocked_worlds:
                    return False
                return all(req in tracker.cleared_nodes for req in node.requires)
        return False

    def apply_stage_rewards(self, node_id: str, unlocked_worlds: set[str]) -> set[str]:
        for nodes in self.catalog.worlds.values():
            for node in nodes:
                if node.node_id != node_id:
                    continue
                for reward in node.rewards:
                    if reward.startswith("unlock:"):
                        unlocked_worlds.add(reward.split(":", 1)[1])
        return unlocked_worlds
