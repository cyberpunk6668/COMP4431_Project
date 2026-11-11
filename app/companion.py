"""Ephemeral, local-only companion coordination; never calls a model or broker.

The database is authoritative. Events only invalidate one explicitly connected
conversation or describe bounded operation state; they never carry chat text.
All bus methods run on the application's event loop and never await consumers.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID | None
    language: Literal["zh", "en"] | None = None
    engine: Literal["deepseek", "local"] | None = None
    expected_generation: int | None = Field(None, ge=0, strict=True)


class ActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Literal["calculate", "options", "history", "retrieval", "speech"]
    status: Literal["started", "completed", "failed", "cancelled"]
    session_id: UUID
    generation: int = Field(ge=0, strict=True)
    phase: Literal["listening", "speaking"] | None = None

    @model_validator(mode="after")
    def speech_phase_only(self):
        if self.phase is not None and self.kind != "speech":
            raise ValueError("Only speech activity may carry a listening/speaking phase")
        return self


class StaleConnection(ValueError):
    pass


class ActivityLimit(ValueError):
    pass


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue
    surface: str


@dataclass(frozen=True)
class Operation:
    operation_id: str
    generation: int
    session_id: str


def encode_event(event: dict) -> str:
    """Only bus-generated event types/IDs enter the SSE framing."""
    return (f"id: {event['epoch']}:{event['seq']}\n"
            f"event: {event['type']}\n"
            "data: " + json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n\n")


class CompanionBus:
    def __init__(self, *, queue_size=64, max_subscribers=32, frontend_ttl=90, clock=time.monotonic):
        self.epoch = str(uuid4())
        self.seq = self.generation = 0
        self.session_id = None
        self.language, self.engine = "zh", "deepseek"
        self.subscribers: set[Subscriber] = set()
        self.activities = {}
        self.queue_size, self.max_subscribers = queue_size, max_subscribers
        self.frontend_ttl, self.clock = frontend_ttl, clock
        self.closed = False

    def connection(self) -> dict:
        return {"epoch": self.epoch, "seq": self.seq, "generation": self.generation,
                "session_id": self.session_id, "language": self.language, "engine": self.engine,
                "desktop_connected": any(s.surface == "desktop" for s in self.subscribers),
                "activities": [{k: v for k, v in item.items() if not k.startswith("_")}
                               for item in self.activities.values()]}

    def event(self, kind, payload=None, *, sid=None):
        return {"epoch": self.epoch, "seq": self.seq, "generation": self.generation,
                "type": kind, "session_id": self.session_id if sid is None else sid,
                "payload": payload or {}}

    def reset(self):
        return self.event("reset", {"connection": self.connection()})

    def _publish(self, kind, payload=None, *, sid=None):
        if self.closed:
            return
        self.seq += 1
        event = self.event(kind, payload, sid=sid)
        # Materialize the post-increment connection snapshot. Consumers can
        # discard older seq values without confusing metadata with prior state.
        if kind == "connection.changed":
            event["payload"] = {"connection": self.connection()}
        elif kind == "activity":
            event["payload"] = {**event["payload"], "activities": self.connection()["activities"]}
        for sub in tuple(self.subscribers):
            if sub.queue.full():
                while not sub.queue.empty():
                    sub.queue.get_nowait()
                # A slow client receives the authoritative invalidation/reset,
                # rather than blocking persistence or replaying partial deltas.
                sub.queue.put_nowait(self.reset())
            else:
                sub.queue.put_nowait(event)

    def connect(self, sid, *, language=None, engine=None, expected_generation=None):
        if expected_generation is not None and expected_generation != self.generation:
            raise StaleConnection("companion_connection_changed")
        sid = str(sid) if sid is not None else None
        changed = sid != self.session_id
        if changed:
            self.generation += 1
            self.session_id = sid
            self.activities.clear()
        prefs_changed = ((language is not None and language != self.language) or
                         (engine is not None and engine != self.engine))
        if language is not None:
            self.language = language
        if engine is not None:
            self.engine = engine
        if changed or prefs_changed:
            self._publish("connection.changed")
        return self.connection()

    def subscribe(self, surface):
        if self.closed or len(self.subscribers) >= self.max_subscribers:
            raise ActivityLimit("companion_connection_limit")
        before = any(s.surface == "desktop" for s in self.subscribers)
        sub = Subscriber(asyncio.Queue(maxsize=self.queue_size), surface)
        if surface == "desktop" and not before:
            # New subscriber gets its own reset; announce presence to the
            # already subscribed clients without queueing an obsolete event.
            self.subscribers.add(sub)
            self._publish("connection.changed")
            while not sub.queue.empty():
                sub.queue.get_nowait()
        else:
            self.subscribers.add(sub)
        return sub

    def unsubscribe(self, sub):
        before = any(s.surface == "desktop" for s in self.subscribers)
        self.subscribers.discard(sub)
        after = any(s.surface == "desktop" for s in self.subscribers)
        if before != after:
            self._publish("connection.changed")

    def notify(self, kind, sid, *, analysis_id=None):
        if self.session_id != sid:
            return
        if kind not in {"session.changed", "analysis.changed", "session.deleted"}:
            raise ValueError("Unsupported companion invalidation")
        payload = {"analysis_id": analysis_id} if kind == "analysis.changed" else {}
        self._publish(kind, payload, sid=sid)
        if kind == "session.deleted":
            self.connect(None)

    def _start(self, operation_id, kind, source, phase=None):
        if source == "frontend" and len(self.activities) >= 32 and operation_id not in self.activities:
            raise ActivityLimit("companion_activity_limit")
        if operation_id in self.activities:
            item = self.activities[operation_id]
            if item["kind"] != kind or item["source"] != source:
                raise StaleConnection("companion_operation_conflict")
            item["_seen"] = self.clock()
            if item.get("phase") != phase:
                item["phase"] = phase
                self._publish("activity", {k: v for k, v in item.items() if not k.startswith("_")})
            return
        item = {"operation_id": operation_id, "kind": kind, "status": "started", "source": source,
                "phase": phase, "started_at": datetime.now(timezone.utc).isoformat(), "_seen": self.clock()}
        self.activities[operation_id] = item
        self._publish("activity", {k: v for k, v in item.items() if not k.startswith("_")})

    def start_operation(self, sid, kind):
        if sid != self.session_id or self.closed:
            return None
        if kind not in {"chat", "refresh"}:
            raise ValueError("Unsupported server activity")
        operation = Operation(str(uuid4()), self.generation, sid)
        self._start(operation.operation_id, kind, "backend")
        return operation

    def finish_operation(self, operation, status):
        if (operation is None or operation.generation != self.generation or
                operation.session_id != self.session_id):
            return
        item = self.activities.get(operation.operation_id)
        if item is not None and item["source"] == "backend":
            self.activities.pop(operation.operation_id)
            self._publish("activity", {"operation_id": operation.operation_id, "kind": item["kind"],
                                       "source": "backend", "status": status})

    def frontend_activity(self, body: ActivityInput):
        self.expire_activities()
        if body.generation != self.generation or str(body.session_id) != self.session_id:
            raise StaleConnection("companion_connection_changed")
        if body.status == "started":
            self._start(body.operation_id, body.kind, "frontend", body.phase)
        else:
            item = self.activities.get(body.operation_id)
            if item is None or item["source"] != "frontend" or item["kind"] != body.kind:
                # A final event cannot invent work or finish another source's
                # operation. A duplicate completed/cancelled event is harmless.
                return
            self.activities.pop(body.operation_id)
            self._publish("activity", {"operation_id": body.operation_id, "kind": body.kind,
                                       "source": "frontend", "status": body.status, "phase": item.get("phase")})

    def expire_activities(self):
        for key, item in list(self.activities.items()):
            if item["source"] == "frontend" and self.clock() - item["_seen"] >= self.frontend_ttl:
                self.activities.pop(key)
                self._publish("activity", {"operation_id": key, "kind": item["kind"], "source": "frontend",
                                           "status": "cancelled", "reason": "expired"})

    def close(self):
        self.closed = True
        self.activities.clear()
        for sub in self.subscribers:
            while not sub.queue.empty():
                sub.queue.get_nowait()
            sub.queue.put_nowait(None)
