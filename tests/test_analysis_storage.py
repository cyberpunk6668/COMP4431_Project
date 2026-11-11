"""Persistence and isolation guarantees for server-owned option analyses."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from uuid import UUID, uuid4

import pytest

from app.storage import Store


def result(symbol="AAPL", value=0.24):
    return {"snapshot": {"symbol": symbol, "expiration": "2027-01-15"},
            "metrics": {"atm_iv": {"value": value, "observations": [0.22, 0.26]}},
            "interpretation": {"status": "skipped"}}


def answer(context=None):
    return {"answer": "波动率反映市场对价格变化的定价。", "sources": [],
            "mode": "local", "analysis_context": context}


def test_legacy_database_migrates_without_losing_chat(tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
              mode TEXT, calculation TEXT, warning TEXT, created_at TEXT NOT NULL);
            INSERT INTO sessions VALUES ('old-session','原有对话','2026-11-01','2026-11-02');
            INSERT INTO messages(session_id,role,content,created_at) VALUES ('old-session','user','旧问题','2026-11-01');
        """)
        db.execute("""INSERT INTO messages(session_id,role,content,sources,mode,calculation,warning,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                   ("old-session", "assistant", "旧回答", json.dumps([{"title": "旧资料"}]),
                    "local", '{"value": 42}', "旧提示", "2026-11-02"))
    store = Store(path)
    session = store.get("old-session")
    assert {key: session[key] for key in ("id", "title", "created_at", "updated_at")} == {
        "id": "old-session", "title": "原有对话", "created_at": "2026-11-01", "updated_at": "2026-11-02",
    }
    assert session["active_analysis_id"] is None
    assert [message["content"] for message in session["messages"]] == ["旧问题", "旧回答"]
    assert all(message["analysis_context"] is None for message in session["messages"])
    assert session["messages"][1]["sources"] == [{"title": "旧资料"}]
    assert session["messages"][1]["calculation"] == {"value": 42}
    assert session["messages"][1]["warning"] == "旧提示"
    identifier = store.save_analysis(result())
    assert store.set_active_analysis("old-session", identifier)
    store.append_turn("old-session", "后续问题", answer({"analysis_id": identifier}))
    # Reopening the same database must keep the migration idempotent.
    reopened = Store(path).get("old-session")
    assert reopened["active_analysis_id"] == identifier
    assert len(reopened["messages"]) == 4
    assert reopened["messages"][-1]["analysis_context"] == {"analysis_id": identifier}
    assert store.create()["active_analysis_id"] is None


def test_saved_analyses_are_distinct_immutable_and_persistent(tmp_path):
    path = tmp_path / "snapshots.sqlite"
    store = Store(path)
    original = result()
    first = store.save_analysis(original)
    second = store.save_analysis(original)
    assert first != second and UUID(first).version == UUID(second).version == 4
    original["metrics"]["atm_iv"]["observations"].append(99)
    retrieved = store.get_analysis(first)
    assert retrieved == {**result(), "analysis_id": first}
    retrieved["metrics"]["atm_iv"]["value"] = 999
    retrieved["snapshot"]["symbol"] = "MUTATED"
    assert Store(path).get_analysis(first) == {**result(), "analysis_id": first}
    assert store.get_analysis(second) == {**result(), "analysis_id": second}
    assert store.get_analysis(str(uuid4())) is None
    tagged = store.save_analysis({**result(), "analysis_id": "preexisting-tag"})
    assert store.get_analysis(tagged)["analysis_id"] == tagged


def test_message_context_is_decoded_and_independent_of_active_binding(tmp_path):
    store = Store(tmp_path / "messages.sqlite")
    session = store.create()
    first, second = store.save_analysis(result()), store.save_analysis(result("MSFT"))
    context = {"analysis_id": first, "evidence_ids": ["g0.atm_iv"], "symbol": "AAPL"}
    assert store.set_active_analysis(session["id"], first)
    store.append_turn(session["id"], "如何理解？", answer(context))
    context["evidence_ids"].append("caller-mutation")
    assert store.set_active_analysis(session["id"], second)
    persisted = store.get(session["id"])
    assert persisted["active_analysis_id"] == second
    assert persisted["messages"][0]["analysis_context"] is None
    assert persisted["messages"][1]["analysis_context"] == {
        "analysis_id": first, "evidence_ids": ["g0.atm_iv"], "symbol": "AAPL",
    }
    persisted["messages"][1]["analysis_context"]["evidence_ids"].append("reader-mutation")
    assert store.get(session["id"])["messages"][1]["analysis_context"]["evidence_ids"] == ["g0.atm_iv"]
    store.append_turn(session["id"], "一般问题", answer())
    assert store.get(session["id"])["messages"][-1]["analysis_context"] is None


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_json_is_rejected_without_partial_writes(tmp_path, invalid):
    store = Store(tmp_path / "strict.sqlite")
    session = store.create("保持原始标题")
    valid_id = store.save_analysis(result())
    with pytest.raises(ValueError):
        store.save_analysis(result(value=invalid))
    with pytest.raises(ValueError):
        store.append_turn(session["id"], "不应保留半个回合", answer({"value": invalid}))
    with pytest.raises(ValueError):
        store.append_turn(session["id"], "也不应保留", {**answer(), "calculation": {"value": invalid}})
    assert store.get(session["id"])["messages"] == []
    assert store.get(session["id"])["title"] == "保持原始标题"
    assert store.get_analysis(valid_id) == {**result(), "analysis_id": valid_id}
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM option_analyses").fetchone()[0] == 1


def test_binding_requires_a_saved_snapshot_and_preserves_previous_binding(tmp_path):
    store = Store(tmp_path / "binding.sqlite")
    session = store.create()
    identifier = store.save_analysis(result())
    assert store.set_active_analysis(session["id"], identifier)
    with pytest.raises(KeyError):
        store.set_active_analysis(session["id"], str(uuid4()))
    assert store.get(session["id"])["active_analysis_id"] == identifier
    assert store.list()[0]["active_analysis_id"] == identifier
    assert not store.set_active_analysis("missing-session", identifier)
    assert store.set_active_analysis(session["id"], None)
    assert store.get(session["id"])["active_analysis_id"] is None


def test_bound_snapshot_cannot_be_deleted_and_session_deletion_preserves_it(tmp_path):
    store = Store(tmp_path / "cleanup.sqlite")
    one, two = store.create(), store.create()
    identifier = store.save_analysis(result())
    store.set_active_analysis(one["id"], identifier)
    store.set_active_analysis(two["id"], identifier)
    assert not store.delete_analysis(identifier)
    assert store.delete(one["id"])
    assert not store.delete_analysis(identifier)
    assert store.get_analysis(identifier) is not None
    store.set_active_analysis(two["id"], None)
    assert not store.delete_analysis(identifier)  # Historical bindings remain protected.
    assert store.delete(two["id"])
    assert store.delete_analysis(identifier)
    assert store.get_analysis(identifier) is None
    assert not store.delete_analysis(identifier)


def test_concurrent_sessions_keep_their_analysis_and_message_context_separate(tmp_path):
    path = tmp_path / "concurrent.sqlite"
    store = Store(path)
    sessions = [store.create(f"会话 {index}")["id"] for index in range(8)]

    def write(index):
        worker = Store(path)
        identifier = worker.save_analysis(result(f"SYM{index}", index / 10))
        assert worker.set_active_analysis(sessions[index], identifier)
        worker.append_turn(sessions[index], f"问题 {index}", answer({"analysis_id": identifier}))
        return identifier

    with ThreadPoolExecutor(max_workers=8) as pool:
        identifiers = list(pool.map(write, range(8)))
    assert len(set(identifiers)) == 8
    reopened = Store(path)
    for index, (sid, identifier) in enumerate(zip(sessions, identifiers)):
        session = reopened.get(sid)
        assert session["active_analysis_id"] == identifier
        assert [message["role"] for message in session["messages"]] == ["user", "assistant"]
        assert session["messages"][0]["content"] == f"问题 {index}"
        assert session["messages"][1]["analysis_context"] == {"analysis_id": identifier}
        assert reopened.get_analysis(identifier)["snapshot"]["symbol"] == f"SYM{index}"


def test_concurrent_legacy_migrations_are_idempotent(tmp_path):
    path = tmp_path / "legacy-concurrent.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
              mode TEXT, calculation TEXT, warning TEXT, created_at TEXT NOT NULL);
        """)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sessions = list(pool.map(lambda _: Store(path).create(), range(4)))
    assert len(Store(path).list()) == 4
    assert all(session["active_analysis_id"] is None for session in sessions)
