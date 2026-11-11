from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from uuid import UUID

import pytest

import app.storage as storage_module
from app.storage import Store


def test_history_tracks_distinct_versions_and_survives_unbinding(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "now", lambda: "2026-11-11T12:00:00+00:00")
    store = Store(tmp_path / "history.sqlite")
    sid, other = store.create()["id"], store.create()["id"]
    first, second = store.save_analysis({"value": 1}), store.save_analysis({"value": 2})
    store.set_active_analysis(sid, first)
    store.set_active_analysis(sid, second)
    assert [row["analysis_id"] for row in store.get_analysis_history(sid)] == [second, first]
    store.set_active_analysis(sid, first)
    store.set_active_analysis(sid, None)
    history = store.get_analysis_history(sid)
    assert [row["analysis_id"] for row in history] == [first, second]
    assert all(set(row) == {"analysis_id", "attached_at"} for row in history)
    assert store.get_analysis_history(other) == store.get_analysis_history("missing") == []
    assert not store.delete_analysis(first) and not store.delete_analysis(second)
    assert store.get_analysis(first)["value"] == 1
    assert Store(store.path).get_analysis_history(sid) == history


def test_v10_active_analysis_is_added_to_history_without_rewriting_old_data(tmp_path):
    path = tmp_path / "v10.sqlite"
    payload = {"snapshot": {"symbol": "AAPL"}, "value": [1, 2]}
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE option_analyses(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
              active_analysis_id TEXT REFERENCES option_analyses(id) ON DELETE RESTRICT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              role TEXT NOT NULL,content TEXT NOT NULL,sources TEXT NOT NULL DEFAULT '[]',mode TEXT,calculation TEXT,warning TEXT,
              created_at TEXT NOT NULL,analysis_context TEXT);
        """)
        db.execute("INSERT INTO option_analyses VALUES (?,?,?)", ("old-analysis", json.dumps(payload), "old-created"))
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", ("old-session", "旧标题", "old-created", "old-updated", "old-analysis"))
        db.execute("INSERT INTO messages(session_id,role,content,created_at,analysis_context) VALUES (?,?,?,?,?)",
                   ("old-session", "assistant", "旧消息", "old-message-time", '{"analysis_id":"old-analysis"}'))
    store = Store(path)
    before = store.get("old-session")
    assert store.get_analysis_history("old-session") == [{"analysis_id": "old-analysis", "attached_at": "old-updated"}]
    assert store.get_analysis("old-analysis") == {**payload, "analysis_id": "old-analysis"}
    assert Store(path).get("old-session") == before
    store.set_active_analysis("old-session", None)
    assert store.get_analysis_history("old-session")[0]["analysis_id"] == "old-analysis"
    assert not store.delete_analysis("old-analysis")


def test_atomic_refresh_keeps_old_snapshot_messages_and_history(tmp_path):
    store = Store(tmp_path / "refresh.sqlite")
    sid = store.create()["id"]
    old = store.save_analysis({"value": {"nested": [1]}})
    store.set_active_analysis(sid, old)
    store.append_turn(sid, "旧问题", {"answer": "旧回答", "sources": [], "mode": "offline", "analysis_context": {"analysis_id": old}})
    old_messages = store.get(sid)["messages"]
    new = store.commit_analysis_refresh(sid, old, {"value": 2, "previous_analysis_id": old})
    assert UUID(new).version == 4 and new != old
    assert store.get(sid)["active_analysis_id"] == new
    assert store.get(sid)["messages"] == old_messages
    assert store.get_analysis(old) == {"value": {"nested": [1]}, "analysis_id": old}
    assert store.get_analysis(new) == {"value": 2, "previous_analysis_id": old, "analysis_id": new}
    assert [row["analysis_id"] for row in store.get_analysis_history(sid)] == [new, old]


def test_refresh_conflicts_and_invalid_json_create_no_orphans(tmp_path):
    store = Store(tmp_path / "conflict.sqlite")
    sid = store.create()["id"]
    old, changed = store.save_analysis({"value": 1}), store.save_analysis({"value": 2})
    store.set_active_analysis(sid, old)
    store.set_active_analysis(sid, changed)
    history = store.get_analysis_history(sid)
    with pytest.raises(ValueError, match="analysis_refresh_conflict"):
        store.commit_analysis_refresh(sid, old, {"value": 3})
    with pytest.raises(ValueError, match="analysis_refresh_conflict"):
        store.commit_analysis_refresh(sid, None, {"value": 3})
    with pytest.raises(KeyError):
        store.commit_analysis_refresh("missing", changed, {"value": 3})
    with pytest.raises(ValueError):
        store.commit_analysis_refresh(sid, changed, {"value": float("nan")})
    assert store.get(sid)["active_analysis_id"] == changed
    assert store.get_analysis_history(sid) == history
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM option_analyses").fetchone()[0] == 2


def test_two_concurrent_refresh_commits_have_one_winner(tmp_path):
    store = Store(tmp_path / "race.sqlite")
    sid = store.create()["id"]
    old = store.save_analysis({"value": "old"})
    store.set_active_analysis(sid, old)

    def commit(index):
        try:
            return store.commit_analysis_refresh(sid, old, {"value": index})
        except ValueError as error:
            assert str(error) == "analysis_refresh_conflict"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, range(2)))
    winners = [identifier for identifier in outcomes if identifier]
    assert len(winners) == 1 and store.get(sid)["active_analysis_id"] == winners[0]
    assert [row["analysis_id"] for row in store.get_analysis_history(sid)] == [winners[0], old]
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM option_analyses").fetchone()[0] == 2
