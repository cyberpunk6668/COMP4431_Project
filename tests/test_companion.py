"""Bounded event state cannot leak an unselected chat or replay stale work."""
import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.companion import ActivityInput, ActivityLimit, CompanionBus, ConnectionInput, StaleConnection, encode_event


def drain(sub):
    values = []
    while not sub.queue.empty():
        values.append(sub.queue.get_nowait())
    return values


def activity(bus, *, operation_id="calc-one", kind="calculate", status="started", **extra):
    return ActivityInput(operation_id=operation_id, kind=kind, status=status,
                         session_id=bus.session_id, generation=bus.generation, **extra)


def test_initial_state_and_connection_generation_are_explicit():
    bus = CompanionBus()
    assert bus.connection()["session_id"] is None
    sub = bus.subscribe("workspace")
    sid = str(uuid4())
    selected = bus.connect(sid, language="en", engine="local")
    assert selected["generation"] == 1 and selected["session_id"] == sid
    event = drain(sub)[0]
    assert event["type"] == "connection.changed" and event["payload"]["connection"] == selected
    assert bus.connect(sid)["generation"] == 1
    assert not drain(sub)
    assert bus.connect(sid, engine="deepseek")["generation"] == 1
    with pytest.raises(StaleConnection):
        bus.connect(None, expected_generation=0)
    assert bus.connect(None)["generation"] == 2


def test_switch_cancels_displayed_work_and_late_final_cannot_idle_new_work():
    bus = CompanionBus()
    first, second = str(uuid4()), str(uuid4())
    bus.connect(first)
    old = bus.start_operation(first, "chat")
    old_generation = bus.generation
    bus.connect(second)
    current = bus.start_operation(second, "refresh")
    sub = bus.subscribe("workspace")
    bus.finish_operation(old, "failed")
    assert not drain(sub)
    assert [a["operation_id"] for a in bus.connection()["activities"]] == [current.operation_id]
    with pytest.raises(StaleConnection):
        bus.frontend_activity(ActivityInput(operation_id="old", kind="calculate", status="completed",
                                           generation=old_generation, session_id=first))


def test_backend_and_frontend_operations_are_separate_and_phase_is_truthful():
    bus = CompanionBus()
    bus.connect(str(uuid4()))
    sub = bus.subscribe("workspace")
    server = bus.start_operation(bus.session_id, "chat")
    bus.frontend_activity(activity(bus, kind="speech", operation_id="read", phase="speaking"))
    speech_event = drain(sub)[-1]
    assert speech_event["payload"]["phase"] == "speaking"
    assert len(speech_event["payload"]["activities"]) == 2
    bus.frontend_activity(activity(bus, operation_id=server.operation_id, status="completed"))
    assert len(bus.connection()["activities"]) == 2
    bus.frontend_activity(activity(bus, kind="speech", operation_id="read", status="completed"))
    assert len(bus.connection()["activities"]) == 1
    bus.finish_operation(server, "completed")
    final = drain(sub)[-1]
    assert final["payload"]["activities"] == []
    assert final["payload"]["status"] == "completed"


def test_presence_changes_do_not_switch_the_selected_conversation():
    bus = CompanionBus()
    sid = str(uuid4())
    bus.connect(sid)
    web = bus.subscribe("workspace")
    pet = bus.subscribe("desktop")
    assert bus.connection()["desktop_connected"]
    assert bus.connection()["generation"] == 1
    assert drain(web)[-1]["payload"]["connection"]["desktop_connected"]
    assert not drain(pet)
    bus.unsubscribe(pet)
    assert not bus.connection()["desktop_connected"]
    assert drain(web)[-1]["session_id"] == sid


def test_slow_subscriber_gets_reset_not_a_partial_unbounded_history():
    bus = CompanionBus(queue_size=2)
    bus.connect(str(uuid4()))
    sub = bus.subscribe("workspace")
    for _ in range(3):
        bus.notify("session.changed", bus.session_id)
    events = drain(sub)
    assert len(events) == 1 and events[0]["type"] == "reset"
    assert events[0]["seq"] == bus.seq
    assert events[0]["payload"]["connection"]["session_id"] == bus.session_id


def test_only_connected_sid_can_invalidate_and_deletion_unlinks():
    bus = CompanionBus()
    sid = str(uuid4())
    bus.connect(sid)
    sub = bus.subscribe("workspace")
    bus.notify("session.changed", str(uuid4()))
    assert not drain(sub)
    bus.notify("session.deleted", sid)
    values = drain(sub)
    assert [e["type"] for e in values] == ["session.deleted", "connection.changed"]
    assert values[0]["generation"] == 1 and values[1]["generation"] == 2
    assert values[-1]["session_id"] is None


def test_frontend_abandonment_expires_without_expiring_actual_model_work():
    clock = [0]
    bus = CompanionBus(frontend_ttl=10, clock=lambda: clock[0])
    bus.connect(str(uuid4()))
    server = bus.start_operation(bus.session_id, "chat")
    bus.frontend_activity(activity(bus))
    clock[0] = 9
    bus.frontend_activity(activity(bus))  # Same operation refreshes its lease.
    clock[0] = 15
    bus.expire_activities()
    assert len(bus.connection()["activities"]) == 2
    clock[0] = 20
    bus.expire_activities()
    assert [x["operation_id"] for x in bus.connection()["activities"]] == [server.operation_id]


def test_client_caps_do_not_block_model_work_and_shutdown_releases_consumers():
    bus = CompanionBus(max_subscribers=1)
    bus.connect(str(uuid4()))
    sub = bus.subscribe("workspace")
    with pytest.raises(ActivityLimit):
        bus.subscribe("desktop")
    for i in range(32):
        bus.frontend_activity(activity(bus, operation_id=f"calc-{i}"))
    with pytest.raises(ActivityLimit):
        bus.frontend_activity(activity(bus, operation_id="overflow"))
    assert bus.start_operation(bus.session_id, "chat") is not None
    bus.close()
    assert drain(sub) == [None]


def test_sse_framing_is_json_and_cannot_contain_chat_text():
    bus = CompanionBus()
    bus.connect(str(uuid4()))
    event = bus.reset()
    encoded = encode_event(event)
    assert encoded.startswith(f"id: {bus.epoch}:{bus.seq}\nevent: reset\ndata: ")
    assert encoded.endswith("\n\n")
    assert json.loads(encoded.split("data: ", 1)[1]) == event
    assert set(event) == {"epoch", "seq", "generation", "type", "session_id", "payload"}
    assert "messages" not in event["payload"]["connection"]


@pytest.mark.parametrize("patch", [
    {"kind": "chat"}, {"status": "arbitrary"}, {"operation_id": "\nattack"},
    {"operation_id": "x" * 81}, {"generation": True}, {"generation": -1},
    {"message": "private words"}, {"phase": "speaking"},
])
def test_activity_is_a_restricted_state_schema(patch):
    value = {"operation_id": "x", "kind": "calculate", "status": "started", "generation": 0, "session_id": str(uuid4())}
    value.update(patch)
    with pytest.raises(ValidationError):
        ActivityInput.model_validate(value)


def test_unknown_connection_fields_and_missing_explicit_selection_rejected():
    with pytest.raises(ValidationError):
        ConnectionInput.model_validate({"engine": "deepseek"})
    with pytest.raises(ValidationError):
        ConnectionInput.model_validate({"session_id": None, "analysis_id": str(uuid4())})


def test_restart_has_distinct_epoch_and_no_remembered_conversation():
    first = CompanionBus()
    first.connect(str(uuid4()))
    second = CompanionBus()
    assert first.epoch != second.epoch
    assert second.connection()["session_id"] is None
