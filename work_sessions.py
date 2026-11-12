"""Saved working conversations, one per idea per workspace.

A session keeps the turns (and what each answer was based on) so work on an idea can
continue across visits. Every query is scoped by workspace id, so one workspace can never
read or clear another's sessions.
"""
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SEED_REFLECTIONS_DATA_DIR", ROOT / "data")) / "work_sessions.db"
MAX_TURNS_KEPT = 200


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS work_sessions(
            id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, seed_id TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(workspace_id, seed_id));
        CREATE TABLE IF NOT EXISTS work_turns(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES work_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, meta TEXT NOT NULL DEFAULT '{}');
        CREATE INDEX IF NOT EXISTS work_turns_session ON work_turns(session_id, id);""")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def get_session(workspace_id, seed_id, create=True):
    with closing(_connect()) as db, db:
        row = db.execute("SELECT * FROM work_sessions WHERE workspace_id=? AND seed_id=?", (workspace_id, seed_id)).fetchone()
        if row or not create:
            return dict(row) if row else None
        session = {"id": uuid.uuid4().hex, "workspace_id": workspace_id, "seed_id": seed_id,
                   "created_at": _now(), "updated_at": _now()}
        db.execute("INSERT INTO work_sessions VALUES(:id,:workspace_id,:seed_id,:created_at,:updated_at)", session)
        return session


def turns(workspace_id, seed_id, limit=60):
    session = get_session(workspace_id, seed_id, create=False)
    if not session:
        return []
    with closing(_connect()) as db:
        rows = db.execute("SELECT role,content,created_at,meta FROM work_turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
                          (session["id"], int(limit))).fetchall()
    return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"], "meta": json.loads(r["meta"] or "{}")}
            for r in reversed(rows)]


def add_turn(workspace_id, seed_id, role, content, meta=None):
    session = get_session(workspace_id, seed_id)
    with closing(_connect()) as db, db:
        db.execute("INSERT INTO work_turns(session_id,role,content,created_at,meta) VALUES(?,?,?,?,?)",
                   (session["id"], role, str(content)[:20000], _now(), json.dumps(meta or {}, ensure_ascii=False)))
        db.execute("UPDATE work_sessions SET updated_at=? WHERE id=?", (_now(), session["id"]))
        db.execute("""DELETE FROM work_turns WHERE session_id=? AND id NOT IN
                      (SELECT id FROM work_turns WHERE session_id=? ORDER BY id DESC LIMIT ?)""",
                   (session["id"], session["id"], MAX_TURNS_KEPT))
    return session


def clear(workspace_id, seed_id):
    with closing(_connect()) as db, db:
        return db.execute("DELETE FROM work_sessions WHERE workspace_id=? AND seed_id=?", (workspace_id, seed_id)).rowcount > 0
