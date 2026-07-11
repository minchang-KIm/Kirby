from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from typing import Protocol

from .events import EventBus
from .rng import DeterministicRng

EntityId = int


@dataclass(frozen=True)
class FrameSnapshot:
    frame_index: int
    rng_state_hash: str
    world_state_hash: str
    event_count: int


class ComponentStore:
    def __init__(self) -> None:
        self._data: dict[type, dict[EntityId, object]] = {}

    def add(self, entity_id: EntityId, component: object) -> None:
        self._data.setdefault(type(component), {})[entity_id] = component

    def remove(self, entity_id: EntityId, component_type: type) -> None:
        self._data.get(component_type, {}).pop(entity_id, None)

    def purge_entity(self, entity_id: EntityId) -> None:
        for mapping in self._data.values():
            mapping.pop(entity_id, None)

    def get(self, entity_id: EntityId, component_type: type) -> object:
        return self._data[component_type][entity_id]

    def try_get(self, entity_id: EntityId, component_type: type) -> object | None:
        return self._data.get(component_type, {}).get(entity_id)

    def has(self, entity_id: EntityId, component_type: type) -> bool:
        return entity_id in self._data.get(component_type, {})

    def components_of_type(self, component_type: type) -> dict[EntityId, object]:
        return self._data.get(component_type, {})

    def entities_with(self, *component_types: type) -> list[EntityId]:
        if not component_types:
            return []
        base = set(self._data.get(component_types[0], {}).keys())
        for comp_type in component_types[1:]:
            base &= set(self._data.get(comp_type, {}).keys())
        return sorted(base)

    def debug_dump(self) -> dict[str, dict[int, object]]:
        dump: dict[str, dict[int, object]] = {}
        for comp_type, mapping in sorted(self._data.items(), key=lambda item: item[0].__name__):
            dump[comp_type.__name__] = {}
            for entity_id, component in sorted(mapping.items(), key=lambda pair: pair[0]):
                dump[comp_type.__name__][entity_id] = component
        return dump


class System(Protocol):
    def update(self, world: "World", dt_ms: int) -> None:
        ...


class SystemScheduler:
    def __init__(self, systems: list[System] | None = None) -> None:
        self.systems = systems or []

    def add(self, system: System) -> None:
        self.systems.append(system)

    def run(self, world: "World", dt_ms: int) -> None:
        for system in self.systems:
            system.update(world, dt_ms)


class World:
    def __init__(self, seed: int = 1337) -> None:
        self._next_entity_id: EntityId = 1
        self.alive_entities: set[EntityId] = set()
        self.components = ComponentStore()
        self.events = EventBus()
        self.rng = DeterministicRng(seed)
        self.scheduler = SystemScheduler()
        self.frame_index = 0
        self.frame_input: object | None = None
        self.resources: dict[str, object] = {}

    def create_entity(self) -> EntityId:
        entity_id = self._next_entity_id
        self._next_entity_id += 1
        self.alive_entities.add(entity_id)
        return entity_id

    def destroy_entity(self, entity_id: EntityId) -> None:
        if entity_id not in self.alive_entities:
            return
        self.alive_entities.remove(entity_id)
        self.components.purge_entity(entity_id)

    def add_component(self, entity_id: EntityId, component: object) -> None:
        self.components.add(entity_id, component)

    def get_component(self, entity_id: EntityId, component_type: type) -> object:
        return self.components.get(entity_id, component_type)

    def try_component(self, entity_id: EntityId, component_type: type) -> object | None:
        return self.components.try_get(entity_id, component_type)

    def has_component(self, entity_id: EntityId, component_type: type) -> bool:
        return self.components.has(entity_id, component_type)

    def query(self, *component_types: type) -> list[tuple[EntityId, ...]]:
        entities = self.components.entities_with(*component_types)
        rows: list[tuple[EntityId, ...]] = []
        for entity_id in entities:
            if entity_id not in self.alive_entities:
                continue
            row: list[object] = [entity_id]
            for comp_type in component_types:
                row.append(self.components.get(entity_id, comp_type))
            rows.append(tuple(row))
        return rows

    def step(self, dt_ms: int, input_frame: object) -> FrameSnapshot:
        self.frame_input = input_frame
        self.scheduler.run(self, dt_ms)
        snapshot = self.snapshot()
        self.events.drain()
        self.frame_index += 1
        return snapshot

    def snapshot(self) -> FrameSnapshot:
        events = self.events.peek()
        return FrameSnapshot(
            frame_index=self.frame_index,
            rng_state_hash=self.rng.state_hash(),
            world_state_hash=self.world_hash(),
            event_count=len(events),
        )

    def world_hash(self) -> str:
        payload = {
            "frame": self.frame_index,
            "entities": sorted(self.alive_entities),
            "components": self._serialized_components(),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _serialized_components(self) -> dict[str, dict[int, object]]:
        dump = self.components.debug_dump()
        output: dict[str, dict[int, object]] = {}
        for component_name, mapping in dump.items():
            output[component_name] = {}
            for entity_id, component in mapping.items():
                output[component_name][entity_id] = _serialize_component(component)
        return output


def _serialize_component(component: object) -> object:
    if is_dataclass(component):
        return asdict(component)
    if hasattr(component, "__dict__"):
        return dict(vars(component))
    return repr(component)
