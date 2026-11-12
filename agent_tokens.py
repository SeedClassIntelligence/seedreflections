"""Workspace-scoped, read-only access tokens for connecting an outside assistant (MCP).

- The token is shown once. Only its SHA-256 digest is stored, so a copy of the database
  cannot be used to connect.
- A token belongs to one workspace (taken from the signed-in session that created it) and
  can only be used on /mcp, where every tool is read-only.
- Tokens expire (90 days by default) and can be revoked at any time.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SEED_REFLECTIONS_DATA_DIR", ROOT / "data")) / "agent_tokens.db"
PREFIX = "srm_"
MAX_ACTIVE_PER_WORKSPACE = 10
DEFAULT_DAYS = 90


def _now():
    return datetime.now(timezone.utc)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS agent_tokens(
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
        digest TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        revoked_at TEXT, last_used_at TEXT, use_count INTEGER NOT NULL DEFAULT 0)""")
    return db


def create_token(workspace_id, name, days=DEFAULT_DAYS):
    name = " ".join(str(name or "").split())[:60] or "Assistant"
    with closing(_connect()) as db, db:
        active = db.execute("SELECT COUNT(*) FROM agent_tokens WHERE workspace_id=? AND revoked_at IS NULL AND expires_at>?",
                            (workspace_id, _iso(_now()))).fetchone()[0]
        if active >= MAX_ACTIVE_PER_WORKSPACE:
            raise ValueError(f"A workspace can have at most {MAX_ACTIVE_PER_WORKSPACE} active tokens. Revoke one first.")
        token = PREFIX + secrets.token_urlsafe(32)
        token_id = secrets.token_hex(8)
        created, expires = _now(), _now() + timedelta(days=int(days))
        db.execute("INSERT INTO agent_tokens(id,workspace_id,name,digest,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                   (token_id, workspace_id, name, _digest(token), _iso(created), _iso(expires)))
    return {"id": token_id, "name": name, "token": token, "created_at": _iso(created), "expires_at": _iso(expires)}


def list_tokens(workspace_id):
    with closing(_connect()) as db:
        rows = db.execute("""SELECT id,name,created_at,expires_at,revoked_at,last_used_at,use_count FROM agent_tokens
                             WHERE workspace_id=? ORDER BY created_at DESC""", (workspace_id,)).fetchall()
    now = _iso(_now())
    return [{**dict(row), "active": row["revoked_at"] is None and row["expires_at"] > now} for row in rows]


def revoke_token(workspace_id, token_id):
    with closing(_connect()) as db, db:
        cursor = db.execute("UPDATE agent_tokens SET revoked_at=? WHERE id=? AND workspace_id=? AND revoked_at IS NULL",
                            (_iso(_now()), str(token_id), workspace_id))
        return cursor.rowcount == 1


def verify(token):
    """Return {"id","workspace_id"} for a valid, unexpired, unrevoked token; otherwise None."""
    token = str(token or "")
    if not token.startswith(PREFIX) or len(token) > 200:
        return None
    digest = _digest(token)
    with closing(_connect()) as db, db:
        row = db.execute("SELECT * FROM agent_tokens WHERE digest=?", (digest,)).fetchone()
        if not row or not hmac.compare_digest(row["digest"], digest):
            return None
        if row["revoked_at"] is not None or row["expires_at"] <= _iso(_now()):
            return None
        db.execute("UPDATE agent_tokens SET last_used_at=?, use_count=use_count+1 WHERE id=?", (_iso(_now()), row["id"]))
    return {"id": row["id"], "workspace_id": row["workspace_id"]}
