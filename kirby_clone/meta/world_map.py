from __future__ import annotations

from dataclasses import dataclass

from kirby_clone.content.loader import CampaignCatalog, WorldNode
from .completion import CompletionTracker
from .unlock_rules import UnlockRules


@dataclass
class WorldMapService:
    catalog: CampaignCatalog
    rules: UnlockRules

    def unlocked_nodes(self, tracker: CompletionTracker, unlocked_worlds: set[str]) -> dict[str, list[WorldNode]]:
        visible: dict[str, list[WorldNode]] = {}
        for world_id, nodes in self.catalog.worlds.items():
            if world_id not in unlocked_worlds:
                continue
            visible[world_id] = [
                node for node in nodes if self.rules.is_node_unlocked(node.node_id, tracker, unlocked_worlds)
            ]
        return visible

    def first_playable_node(self, tracker: CompletionTracker, unlocked_worlds: set[str]) -> WorldNode | None:
        visible = self.unlocked_nodes(tracker, unlocked_worlds)
        for world_id in sorted(visible.keys()):
            for node in visible[world_id]:
                if node.node_id not in tracker.cleared_nodes:
                    return node
        return None
