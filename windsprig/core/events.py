"""Queue semantic gameplay events without coupling simulation to presentation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

_ENUM_INTERNAL_STATE = frozenset({"_value_", "_name_", "__objclass__", "_sort_order_"})


@dataclass(frozen=True, slots=True)
class EventEnumValue:
    """Event-owned immutable snapshot of one accepted Enum member."""

    enum_type: str
    member: str
    value: object

    def __post_init__(self) -> None:
        if type(self.enum_type) is not str or type(self.member) is not str:
            raise TypeError("event enum type and member must be strings")
        object.__setattr__(self, "value", _freeze_event_value(self.value))


def _is_immutable_enum_state(value: object, seen: frozenset[int] = frozenset()) -> bool:
    if value is None or type(value) in {bool, int, float, str, bytes}:
        return True
    if isinstance(value, Enum):
        identity = id(value)
        return (
            identity not in seen
            and all(name in _ENUM_INTERNAL_STATE for name in vars(value))
            and _is_immutable_enum_state(
                value.value,
                seen | {identity},
            )
        )
    if isinstance(value, tuple):
        return all(_is_immutable_enum_state(item, seen) for item in value)
    if isinstance(value, frozenset):
        return all(_is_immutable_enum_state(item, seen) for item in value)
    return False


def _validate_enum_payload(value: Enum) -> None:
    if not _is_immutable_enum_state(value):
        raise TypeError("event payload enum values must be immutable")


def _freeze_event_mapping[KeyT](value: Mapping[KeyT, object]) -> Mapping[str, object]:
    frozen: dict[str, object] = {}
    for key, nested in value.items():
        if not isinstance(key, str):
            raise TypeError("event payload mapping keys must be strings")
        frozen[key] = _freeze_event_value(nested)
    return MappingProxyType(frozen)


def _freeze_event_value(value: object) -> object:
    """Copy supported values into a recursively immutable event-owned form."""
    if type(value) is EventEnumValue:
        return value
    if isinstance(value, Mapping):
        return _freeze_event_mapping(value)
    if isinstance(value, Set):
        return frozenset(_freeze_event_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_event_value(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, Enum):
        _validate_enum_payload(value)
        enum_type = type(value)
        return EventEnumValue(
            enum_type=f"{enum_type.__module__}.{enum_type.__qualname__}",
            member=value.name,
            value=_freeze_event_value(value.value),
        )
    if value is None or type(value) in {bool, int, float, str, bytes}:
        return value
    raise TypeError(f"event payload value type is unsupported: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class GameEvent:
    """Owned immutable semantic event safe to retain across simulation frames."""

    topic: str
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.payload, Mapping):
            raise TypeError("event payload must be a mapping")
        object.__setattr__(
            self,
            "payload",
            _freeze_event_mapping(self.payload),
        )


class EventBus:
    """Observer pattern hub used to decouple gameplay systems."""

    def __init__(self) -> None:
        self._queue: list[GameEvent] = []
        self._subscribers: dict[str, list[Callable[[GameEvent], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[GameEvent], None]) -> None:
        self._subscribers.setdefault(topic, []).append(callback)

    def publish(self, topic: str, payload: Mapping[str, object] | None = None) -> None:
        event = GameEvent(topic=topic, payload={} if payload is None else payload)
        self._queue.append(event)
        self.notify(event)

    def notify(self, event: GameEvent) -> None:
        """Deliver an event without queueing it when the caller owns consumption.

        Fixed-step systems use :meth:`publish` so ``World.step`` owns the queued
        event. Boundaries that return an event directly use this method to avoid
        replaying the same event on the next simulation step.
        """
        for callback in self._subscribers.get(event.topic, []):
            callback(event)
        for callback in self._subscribers.get("*", []):
            callback(event)

    def drain(self) -> list[GameEvent]:
        events = self._queue
        self._queue = []
        return events

    def peek(self) -> list[GameEvent]:
        return list(self._queue)
