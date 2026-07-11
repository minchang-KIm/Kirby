"""Queue and subscriber ownership contracts for deterministic game events."""

from __future__ import annotations

from windsprig.core.events import EventBus, GameEvent


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
