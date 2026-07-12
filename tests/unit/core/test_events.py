"""Queue and subscriber ownership contracts for deterministic game events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from enum import Enum
from typing import cast

import pytest

from windsprig.core.events import EventBus, EventEnumValue, GameEvent


class MutablePayload:
    def __init__(self) -> None:
        self.value = "original"


class MutableString(str):
    mutable: list[str]

    def __new__(cls, value: str) -> MutableString:
        instance = super().__new__(cls, value)
        instance.mutable = list[str]()
        return instance


class EventKind(Enum):
    OBSERVED = "observed"


class MutableEventKind(Enum):
    OBSERVED = list[str]()


def pending_bus() -> tuple[EventBus, list[GameEvent], list[GameEvent]]:
    bus = EventBus()
    observed: list[GameEvent] = []
    bus.subscribe("*", observed.append)
    bus.publish("Pending", {"order": 1})
    pending = bus.peek()
    observed.clear()
    return bus, observed, pending


def test_notify_delivers_same_event_once_without_changing_pending_queue() -> None:
    bus = EventBus()
    observed: list[GameEvent] = []
    bus.subscribe("PlayerJoined", observed.append)
    bus.publish("PendingFirst", {"order": 1})
    bus.publish("PendingSecond", {"order": 2})
    pending = bus.peek()
    observed.clear()
    immediate = GameEvent("PlayerJoined", {"slot": 2})

    bus.notify(immediate)

    assert observed == [immediate]
    assert observed[0] is immediate
    assert bus.peek() == pending


def test_event_constructor_copies_and_deeply_freezes_payload() -> None:
    source: dict[str, object] = {
        "stage_id": "world_1_stage_1",
        "details": {
            "slots": [1, 2],
            "tags": {"leaf", "wind"},
            "bytes": bytearray(b"wind"),
            "kind": EventKind.OBSERVED,
        },
    }

    event = GameEvent("StageObserved", source)
    details_source = cast(dict[str, object], source["details"])
    cast(list[int], details_source["slots"]).append(3)
    cast(set[str], details_source["tags"]).add("changed")
    cast(bytearray, details_source["bytes"])[0] = 0
    source["stage_id"] = "changed"
    details_source["extra"] = True

    assert not hasattr(event, "__dict__")
    assert event.payload["stage_id"] == "world_1_stage_1"
    details = cast(Mapping[str, object], event.payload["details"])
    assert details["slots"] == (1, 2)
    assert details["tags"] == frozenset({"leaf", "wind"})
    assert details["bytes"] == b"wind"
    frozen_kind = cast(EventEnumValue, details["kind"])
    assert frozen_kind.member == "OBSERVED"
    assert frozen_kind.value == "observed"
    with pytest.raises(FrozenInstanceError):
        event.topic = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        event.payload["stage_id"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        details["extra"] = True  # type: ignore[index]
    slots = cast(tuple[int, ...], details["slots"])
    with pytest.raises(TypeError):
        slots[0] = 9  # type: ignore[index]
    tags = cast(frozenset[str], details["tags"])
    with pytest.raises(AttributeError):
        tags.add("changed")  # type: ignore[attr-defined]


def test_publish_queues_and_notifies_the_same_owned_event_snapshot() -> None:
    bus = EventBus()
    observed: list[GameEvent] = []
    bus.subscribe("*", observed.append)
    source: dict[str, object] = {"stage_id": "world_1_stage_1"}

    bus.publish("StageObserved", source)
    source["stage_id"] = "changed"

    queued = bus.peek()[0]
    assert observed[0] is queued
    assert queued.payload == {"stage_id": "world_1_stage_1"}


def test_event_constructor_rejects_unsupported_mutable_values() -> None:
    with pytest.raises(TypeError, match="unsupported.*MutablePayload"):
        GameEvent("Unsafe", {"value": MutablePayload()})


def test_event_constructor_rejects_mutable_valued_enums() -> None:
    with pytest.raises(TypeError, match="enum values must be immutable"):
        GameEvent("Unsafe", {"kind": MutableEventKind.OBSERVED})


def test_event_enum_snapshot_is_independent_of_later_singleton_mutation() -> None:
    class LaterMutableKind(Enum):
        OBSERVED = "observed"

    member = LaterMutableKind.OBSERVED
    event = GameEvent("Observed", {"kind": member})
    member._value_ = "changed"
    member.added = []  # type: ignore[attr-defined]

    frozen_kind = cast(EventEnumValue, event.payload["kind"])
    assert frozen_kind.member == "OBSERVED"
    assert frozen_kind.value == "observed"


def test_event_enum_value_direct_construction_copies_mutable_input() -> None:
    source = ["observed"]

    frozen = EventEnumValue("tests.EventKind", "OBSERVED", source)
    source.append("changed")

    assert frozen.value == ("observed",)


def test_enum_bearing_event_payload_can_be_republished_idempotently() -> None:
    first = GameEvent("Observed", {"kind": EventKind.OBSERVED})
    bus = EventBus()

    bus.publish("Republished", first.payload)

    second = bus.peek()[0]
    assert second.payload == first.payload
    assert second.payload["kind"] is first.payload["kind"]


def test_event_rejects_event_enum_value_subclasses_with_extra_state() -> None:
    class ExtendedEventEnumValue(EventEnumValue):
        mutable = list[str]()

    extended = ExtendedEventEnumValue("tests.EventKind", "OBSERVED", "observed")

    with pytest.raises(TypeError, match="unsupported.*ExtendedEventEnumValue"):
        GameEvent("Unsafe", {"kind": extended})


def test_event_rejects_nested_enum_member_with_mutable_state() -> None:
    class InnerKind(Enum):
        OBSERVED = "observed"

    InnerKind.OBSERVED.mutable = []  # type: ignore[attr-defined]

    class OuterKind(Enum):
        INNER = InnerKind.OBSERVED

    with pytest.raises(TypeError, match="enum values must be immutable"):
        GameEvent("Unsafe", {"kind": OuterKind.INNER})


def test_publish_rejects_non_string_nested_mapping_keys_before_delivery() -> None:
    bus = EventBus()
    observed: list[GameEvent] = []
    bus.subscribe("*", observed.append)

    with pytest.raises(TypeError, match="mapping keys must be strings"):
        bus.publish("Unsafe", {"nested": {1: "value"}})

    assert bus.peek() == []
    assert observed == []


def test_publish_rejects_mutable_string_payload_keys_without_partial_mutation() -> None:
    bus, observed, pending = pending_bus()
    mutable_key = MutableString("stage_id")

    with pytest.raises(TypeError, match="mapping keys must be strings"):
        bus.publish("Unsafe", {"nested": {mutable_key: "stage"}})

    assert bus.peek() == pending
    assert observed == []


def test_event_constructor_rejects_mutable_string_topics() -> None:
    with pytest.raises(TypeError, match="event topic must be a string"):
        GameEvent(MutableString("Unsafe"))


def test_publish_rejects_mutable_string_topics_without_partial_mutation() -> None:
    bus, observed, pending = pending_bus()

    with pytest.raises(TypeError, match="event topic must be a string"):
        bus.publish(MutableString("Unsafe"), {"value": 1})

    assert bus.peek() == pending
    assert observed == []


def test_subscribe_rejects_mutable_string_topics_without_registration() -> None:
    bus = EventBus()
    observed: list[GameEvent] = []

    with pytest.raises(TypeError, match="event topic must be a string"):
        bus.subscribe(MutableString("Unsafe"), observed.append)

    exact = GameEvent("Unsafe")
    bus.notify(exact)
    assert observed == []
    assert bus.peek() == []


def test_notify_rejects_game_event_subclasses_without_delivery_or_queue_changes() -> None:
    class ExtendedGameEvent(GameEvent):
        mutable = list[str]()

    bus, observed, pending = pending_bus()
    unsafe = ExtendedGameEvent("Unsafe")

    with pytest.raises(TypeError, match="event must be a GameEvent"):
        bus.notify(unsafe)

    assert bus.peek() == pending
    assert observed == []


def test_publish_rejects_mutable_slotted_enum_state_without_partial_mutation() -> None:
    class MutableSlotMixin:
        __slots__ = ("mutable",)

        def __init__(self, value: str) -> None:
            _ = value
            self.mutable = list[str]()

    class SlottedEventKind(MutableSlotMixin, Enum):
        OBSERVED = "observed"

    bus, observed, pending = pending_bus()

    with pytest.raises(TypeError, match="enum values must be immutable"):
        bus.publish("Unsafe", {"kind": SlottedEventKind.OBSERVED})

    assert bus.peek() == pending
    assert observed == []
