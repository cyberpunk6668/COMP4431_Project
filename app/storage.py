"""SQLite persistence with atomic chat turns and immutable analysis snapshots."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS option_analyses (
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  active_analysis_id TEXT REFERENCES option_analyses(id) ON DELETE RESTRICT);
                CREATE TABLE IF NOT EXISTS messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                  role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
                  mode TEXT, calculation TEXT, warning TEXT, created_at TEXT NOT NULL, analysis_context TEXT);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
                CREATE TABLE IF NOT EXISTS session_analysis_history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                  analysis_id TEXT NOT NULL REFERENCES option_analyses(id) ON DELETE RESTRICT,
                  attached_at TEXT NOT NULL,
                  UNIQUE(session_id, analysis_id));
            """)
            # Serialize schema inspection and migration so simultaneous Store
            # instances cannot both attempt to add the same legacy column.
            db.execute("BEGIN IMMEDIATE")
            if "active_analysis_id" not in {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}:
                db.execute("ALTER TABLE sessions ADD COLUMN active_analysis_id TEXT REFERENCES option_analyses(id) ON DELETE RESTRICT")
            if "analysis_context" not in {row["name"] for row in db.execute("PRAGMA table_info(messages)")}:
                db.execute("ALTER TABLE messages ADD COLUMN analysis_context TEXT")
            # v10 retained only the current binding. Its session update time is
            # the best available legacy timestamp; older bindings cannot be inferred.
            db.execute("""INSERT OR IGNORE INTO session_analysis_history(session_id,analysis_id,attached_at)
                       SELECT sessions.id, sessions.active_analysis_id, sessions.updated_at FROM sessions
                       JOIN option_analyses ON option_analyses.id=sessions.active_analysis_id""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, title: str = "新对话 / New chat") -> dict:
        stamp = now()
        session = dict(id=str(uuid.uuid4()), title=title[:80], created_at=stamp, updated_at=stamp,
                       active_analysis_id=None)
        with self.connect() as db:
            db.execute("""INSERT INTO sessions(id,title,created_at,updated_at,active_analysis_id)
                       VALUES (:id,:title,:created_at,:updated_at,:active_analysis_id)""", session)
        return session

    def list(self) -> list:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 100")]

    def get(self, sid: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["messages"] = []
            for msg in db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,)):
                item = dict(msg)
                item.pop("session_id")
                item["sources"] = json.loads(item["sources"])
                item["calculation"] = json.loads(item["calculation"]) if item["calculation"] else None
                item["analysis_context"] = json.loads(item["analysis_context"]) if item["analysis_context"] else None
                result["messages"].append(item)
            return result

    def save_analysis(self, result: dict) -> str:
        """Save a server-produced result under a fresh ID; no update is exposed."""
        if not isinstance(result, dict):
            raise TypeError("An analysis result must be a dictionary")
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
        analysis_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO option_analyses(id,payload,created_at) VALUES (?,?,?)",
                       (analysis_id, payload, now()))
        return analysis_id

    def get_analysis(self, analysis_id: str) -> dict | None:
        """Return a fresh JSON copy, tagged with its authoritative server ID."""
        with self.connect() as db:
            row = db.execute("SELECT payload FROM option_analyses WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            return None
        return {**json.loads(row["payload"]), "analysis_id": analysis_id}

    def set_active_analysis(self, sid: str, analysis_id: str | None) -> bool:
        """Bind a saved snapshot, or clear it. Unknown analysis IDs raise KeyError."""
        with self.connect() as db:
            # Keep existence validation and binding atomic with snapshot deletion.
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone() is None:
                return False
            if analysis_id is not None and db.execute("SELECT id FROM option_analyses WHERE id=?", (analysis_id,)).fetchone() is None:
                raise KeyError(analysis_id)
            stamp = now()
            if analysis_id is not None:
                self._record_analysis_attachment(db, sid, analysis_id, stamp)
            return db.execute("UPDATE sessions SET active_analysis_id=?, updated_at=? WHERE id=?",
                              (analysis_id, stamp, sid)).rowcount > 0

    @staticmethod
    def _record_analysis_attachment(db, sid, analysis_id, stamp):
        # Rebinding updates a snapshot's last attachment and its tie-break order.
        # No child rows reference this mapping's integer key.
        db.execute("""INSERT OR REPLACE INTO session_analysis_history(session_id,analysis_id,attached_at)
                   VALUES (?,?,?)""", (sid, analysis_id, stamp))

    def get_analysis_history(self, sid: str) -> list[dict]:
        """Return distinct saved analyses in most-recent-attachment order."""
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT analysis_id,attached_at FROM session_analysis_history
                       WHERE session_id=? ORDER BY attached_at DESC,id DESC""", (sid,))]

    def commit_analysis_refresh(self, sid: str, expected_id: str, result: dict) -> str:
        """Atomically save and bind a refresh if the old binding is unchanged.

        Missing sessions raise KeyError(sid). A changed or empty expected binding
        raises ValueError('analysis_refresh_conflict'), with no snapshot inserted.
        Old snapshots and message contexts are never updated.
        """
        if not isinstance(result, dict):
            raise TypeError("An analysis result must be a dictionary")
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT active_analysis_id FROM sessions WHERE id=?", (sid,)).fetchone()
            if row is None:
                raise KeyError(sid)
            if not expected_id or row["active_analysis_id"] != expected_id:
                raise ValueError("analysis_refresh_conflict")
            analysis_id, stamp = str(uuid.uuid4()), now()
            db.execute("INSERT INTO option_analyses(id,payload,created_at) VALUES (?,?,?)",
                       (analysis_id, payload, stamp))
            db.execute("UPDATE sessions SET active_analysis_id=?,updated_at=? WHERE id=?", (analysis_id, stamp, sid))
            self._record_analysis_attachment(db, sid, analysis_id, stamp)
        return analysis_id

    def delete_analysis(self, analysis_id: str) -> bool:
        """Remove only snapshots absent from both active bindings and history."""
        with self.connect() as db:
            # A single write statement prevents a concurrent bind from racing
            # the deletion. The foreign key also protects active references.
            return db.execute("""DELETE FROM option_analyses WHERE id=? AND NOT EXISTS (
                               SELECT 1 FROM sessions WHERE active_analysis_id=option_analyses.id) AND NOT EXISTS (
                               SELECT 1 FROM session_analysis_history WHERE analysis_id=option_analyses.id)""",
                              (analysis_id,)).rowcount > 0

    def delete(self, sid: str) -> bool:
        with self.connect() as db:
            return db.execute("DELETE FROM sessions WHERE id=?", (sid,)).rowcount > 0

    def append_turn(self, sid: str, question: str, answer: dict):
        with self.connect() as db:
            session = db.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
            if session is None:
                raise KeyError(sid)
            stamp = now()
            db.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES (?,?,?,?)",
                       (sid, "user", question, stamp))
            context = answer.get("analysis_context")
            db.execute("""INSERT INTO messages(session_id,role,content,sources,mode,calculation,warning,created_at,analysis_context)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                       (sid, "assistant", answer["answer"], json.dumps(answer["sources"], ensure_ascii=False, allow_nan=False),
                        answer["mode"], json.dumps(answer.get("calculation"), ensure_ascii=False, allow_nan=False), answer.get("warning"), stamp,
                        json.dumps(context, ensure_ascii=False, allow_nan=False) if context is not None else None))
            db.execute("UPDATE sessions SET title=CASE WHEN (SELECT COUNT(*) FROM messages WHERE session_id=?)=2 THEN ? ELSE title END, updated_at=? WHERE id=?",
                       (sid, question[:48], stamp, sid))
