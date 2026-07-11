"""Queue semantic gameplay events without coupling simulation to presentation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GameEvent:
    topic: str
    payload: dict[str, object] = field(default_factory=dict)


class EventBus:
    """Observer pattern hub used to decouple gameplay systems."""

    def __init__(self) -> None:
        self._queue: list[GameEvent] = []
        self._subscribers: dict[str, list[Callable[[GameEvent], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[GameEvent], None]) -> None:
        self._subscribers.setdefault(topic, []).append(callback)

    def publish(self, topic: str, payload: dict[str, object] | None = None) -> None:
        event = GameEvent(topic=topic, payload=payload or {})
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
