"""Scoped API connections for provider-neutral conversation delivery."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone

from archive_store import DB_PATH


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS api_integrations(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
          provider TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'active', delivery_count INTEGER NOT NULL DEFAULT 0,
          last_delivery_at TEXT, last_error TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_api_integrations_workspace
          ON api_integrations(workspace_id,status,created_at);
        """)


def create_integration(workspace_id, name, provider):
    initialize()
    name = str(name or "").strip()
    provider = str(provider or "other").strip().lower()
    if not name:
        raise ValueError("Connection name is required")
    raw_token = "sr_live_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    integration_id = uuid.uuid4().hex
    now = _now()
    with _connect() as db:
        db.execute("INSERT INTO api_integrations(id,workspace_id,name,provider,token_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                   (integration_id, workspace_id, name[:120], provider[:64], digest, now, now))
    return {"id": integration_id, "workspace_id": workspace_id, "name": name[:120], "provider": provider[:64],
            "status": "active", "delivery_count": 0, "last_delivery_at": None, "created_at": now,
            "token": raw_token, "token_displayed_once": True}


def list_integrations(workspace_id):
    initialize()
    with _connect() as db:
        rows = db.execute("""SELECT id,name,provider,status,delivery_count,last_delivery_at,last_error,created_at,updated_at
                           FROM api_integrations WHERE workspace_id=? ORDER BY created_at DESC""", (workspace_id,)).fetchall()
    return [dict(row) for row in rows]


def authenticate(token):
    initialize()
    if not token or not token.startswith("sr_live_"):
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as db:
        row = db.execute("SELECT * FROM api_integrations WHERE token_hash=? AND status='active'", (digest,)).fetchone()
    return dict(row) if row else None


def record_delivery(integration_id, error=None):
    now = _now()
    with _connect() as db:
        if error:
            db.execute("UPDATE api_integrations SET last_error=?,updated_at=? WHERE id=?", (str(error)[:1000], now, integration_id))
        else:
            db.execute("""UPDATE api_integrations SET delivery_count=delivery_count+1,last_delivery_at=?,last_error=NULL,updated_at=?
                          WHERE id=?""", (now, now, integration_id))


def revoke_integration(integration_id, workspace_id):
    initialize()
    now = _now()
    with _connect() as db:
        changed = db.execute("UPDATE api_integrations SET status='revoked',updated_at=? WHERE id=? AND workspace_id=?",
                             (now, integration_id, workspace_id)).rowcount
    if not changed:
        raise KeyError("API connection not found")
    return {"id": integration_id, "status": "revoked"}
