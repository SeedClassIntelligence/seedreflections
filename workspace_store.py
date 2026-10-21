"""Authoritative SQLite persistence for the Seed Reflections workspace.

The current application still consumes the established workspace document shape.
This adapter moves that document into the same SQLite database as the archive so
the JSON file becomes migration input/export evidence rather than live state.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from archive_store import DB_PATH


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS workspace_state(
          workspace_id TEXT PRIMARY KEY, document_json TEXT NOT NULL,
          revision INTEGER NOT NULL, migrated_from TEXT, source_sha256 TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_revisions(
          workspace_id TEXT NOT NULL, revision INTEGER NOT NULL,
          document_json TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(workspace_id,revision)
        );
        CREATE TABLE IF NOT EXISTS workspace_normalization(
          workspace_id TEXT PRIMARY KEY, normalized_at TEXT NOT NULL, schema_version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_projects(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          name TEXT, stage TEXT, payload_json TEXT NOT NULL, PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE TABLE IF NOT EXISTS workspace_seeds(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          project_id TEXT, title TEXT, lifecycle TEXT, continuity TEXT, candidate_id TEXT,
          payload_json TEXT NOT NULL, PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE INDEX IF NOT EXISTS workspace_seed_project ON workspace_seeds(workspace_id,project_id);
        CREATE TABLE IF NOT EXISTS workspace_decisions(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          project_id TEXT, status TEXT, candidate_id TEXT, payload_json TEXT NOT NULL,
          PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE TABLE IF NOT EXISTS workspace_relationships(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          source_id TEXT, target_id TEXT, relation_type TEXT, approval_status TEXT,
          payload_json TEXT NOT NULL, PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE TABLE IF NOT EXISTS workspace_conflicts(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          project_id TEXT, status TEXT, payload_json TEXT NOT NULL, PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE TABLE IF NOT EXISTS workspace_sources(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          source_type TEXT, payload_json TEXT NOT NULL, PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE TABLE IF NOT EXISTS workspace_accounts(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          email TEXT, role TEXT, plan TEXT, status TEXT, payload_json TEXT NOT NULL,
          PRIMARY KEY(workspace_id,entity_id)
        );
        CREATE TABLE IF NOT EXISTS workspace_telemetry(
          workspace_id TEXT NOT NULL, entity_id TEXT NOT NULL, row_order INTEGER NOT NULL,
          event_type TEXT, payload_json TEXT NOT NULL, PRIMARY KEY(workspace_id,entity_id)
        );
        """)


_ENTITY_TABLES = {
    "projects":"workspace_projects", "seeds":"workspace_seeds", "decisions":"workspace_decisions",
    "relationships":"workspace_relationships", "conflicts":"workspace_conflicts", "sources":"workspace_sources",
    "accounts":"workspace_accounts", "telemetry":"workspace_telemetry",
}


def _entity_id(kind, item, index):
    keys = {
        "projects":("project_id","id"), "seeds":("seed_id","id"), "decisions":("decision_id","id"),
        "relationships":("relationship_id","id"), "conflicts":("conflict_id","id"),
        "sources":("source_id","id"), "accounts":("id","email"), "telemetry":("id","event_id"),
    }[kind]
    value = next((item.get(key) for key in keys if item.get(key)), None)
    if value: return str(value)
    digest = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    return f"{kind}-{digest}-{index}"


def _entity_columns(kind, item):
    if kind == "projects": return (item.get("name") or item.get("title"), item.get("stage") or item.get("status"))
    if kind == "seeds": return (item.get("project_id"), item.get("title"), item.get("status"), item.get("continuity_status"), item.get("candidate_id"))
    if kind == "decisions": return (item.get("project_id"), item.get("status"), item.get("candidate_id"))
    if kind == "relationships": return (item.get("source_seed_id"), item.get("target_seed_id"), item.get("relationship_type"), item.get("approval_status"))
    if kind == "conflicts": return (item.get("project_id"), item.get("status"))
    if kind == "sources": return (item.get("type") or item.get("platform"),)
    if kind == "accounts": return (item.get("email"), item.get("role"), item.get("plan"), item.get("status"))
    return (item.get("event_type") or item.get("type"),)


def _sync_entities(db, document, workspace_id):
    for kind, table in _ENTITY_TABLES.items():
        db.execute(f"DELETE FROM {table} WHERE workspace_id=?", (workspace_id,))
        for index, item in enumerate(document.get(kind, []) if isinstance(document, dict) else []):
            if not isinstance(item, dict): continue
            values=(workspace_id,_entity_id(kind,item,index),index,*_entity_columns(kind,item),json.dumps(item,ensure_ascii=False))
            placeholders=",".join("?" for _ in values)
            db.execute(f"INSERT INTO {table} VALUES({placeholders})",values)


def _hydrate_entities(db, document, workspace_id):
    if not isinstance(document, dict): document={}
    for kind, table in _ENTITY_TABLES.items():
        rows=db.execute(f"SELECT payload_json FROM {table} WHERE workspace_id=? ORDER BY row_order",(workspace_id,)).fetchall()
        document[kind]=[json.loads(row["payload_json"]) for row in rows]
    return document


def _read_legacy(path):
    source = Path(path)
    if not source.exists():
        return [], None
    raw = source.read_bytes()
    try:
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except Exception:
        return [], hashlib.sha256(raw).hexdigest()


def ensure_migrated(legacy_path="seeds.json", workspace_id="local"):
    initialize()
    with _connect() as db:
        # First-load browser requests arrive concurrently. Reserve the writer
        # before checking workspace_state so only one request performs migration.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT revision FROM workspace_state WHERE workspace_id=?", (workspace_id,)).fetchone()
        if row:
            normalized=db.execute("SELECT 1 FROM workspace_normalization WHERE workspace_id=?",(workspace_id,)).fetchone()
            if not normalized:
                stored=db.execute("SELECT document_json FROM workspace_state WHERE workspace_id=?",(workspace_id,)).fetchone()
                _sync_entities(db,json.loads(stored["document_json"]),workspace_id)
                db.execute("INSERT INTO workspace_normalization VALUES(?,?,2)",(workspace_id,_now()))
            return {"migrated":False,"revision":row["revision"]}
        document, source_hash = ({key:[] for key in _ENTITY_TABLES},None) if (
            workspace_id=="local" and os.environ.get("SEED_REFLECTIONS_MIGRATE_LEGACY","1")=="0"
        ) else _read_legacy(legacy_path)
        now = _now(); encoded = json.dumps(document, ensure_ascii=False)
        db.execute("""INSERT INTO workspace_state
          (workspace_id,document_json,revision,migrated_from,source_sha256,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?)""", (workspace_id,encoded,1,str(Path(legacy_path).resolve()),source_hash,now,now))
        db.execute("INSERT INTO workspace_revisions VALUES(?,?,?,?,?)",
                   (workspace_id,1,encoded,"legacy_json_migration",now))
        _sync_entities(db,document,workspace_id)
        db.execute("INSERT INTO workspace_normalization VALUES(?,?,2)",(workspace_id,now))
    return {"migrated":True,"revision":1,"source_sha256":source_hash}


def create_empty_workspace(workspace_id):
    initialize(); now=_now(); document={key:[] for key in _ENTITY_TABLES}; encoded=json.dumps(document)
    with _connect() as db:
        if db.execute("SELECT 1 FROM workspace_state WHERE workspace_id=?",(workspace_id,)).fetchone(): return
        db.execute("INSERT INTO workspace_state VALUES(?,?,?,?,?,?,?)",(workspace_id,encoded,1,None,None,now,now))
        db.execute("INSERT INTO workspace_revisions VALUES(?,?,?,?,?)",(workspace_id,1,encoded,"workspace_created",now))
        _sync_entities(db,document,workspace_id)
        db.execute("INSERT INTO workspace_normalization VALUES(?,?,2)",(workspace_id,now))


def load_workspace(legacy_path="seeds.json", workspace_id="local"):
    ensure_migrated(legacy_path, workspace_id)
    with _connect() as db:
        row = db.execute("SELECT document_json FROM workspace_state WHERE workspace_id=?", (workspace_id,)).fetchone()
        document=_hydrate_entities(db,json.loads(row["document_json"]),workspace_id)
    return document


def save_workspace_in_transaction(db, document, workspace_id="local", reason="application_write"):
    """Persist a workspace using an existing SQLite transaction.

    This is intentionally public for operations, such as verified tenant restore,
    that must update archive rows and workspace state in one database commit.
    The caller owns BEGIN/COMMIT/ROLLBACK.
    """
    encoded=json.dumps(document, ensure_ascii=False); now=_now()
    row=db.execute("SELECT revision FROM workspace_state WHERE workspace_id=?",(workspace_id,)).fetchone()
    if not row:
        raise RuntimeError("Workspace must be migrated before it can be saved")
    revision=row["revision"]+1
    _sync_entities(db,document,workspace_id)
    db.execute("UPDATE workspace_state SET document_json=?,revision=?,updated_at=? WHERE workspace_id=?",
               (encoded,revision,now,workspace_id))
    db.execute("INSERT INTO workspace_revisions VALUES(?,?,?,?,?)",(workspace_id,revision,encoded,reason,now))
    db.execute("""DELETE FROM workspace_revisions WHERE workspace_id=? AND revision NOT IN
      (SELECT revision FROM workspace_revisions WHERE workspace_id=? ORDER BY revision DESC LIMIT 50)""",
      (workspace_id,workspace_id))
    return revision


def save_workspace(document, workspace_id="local", reason="application_write"):
    initialize()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        return save_workspace_in_transaction(db,document,workspace_id,reason)


def storage_status(workspace_id="local"):
    initialize()
    with _connect() as db:
        row=db.execute("""SELECT revision,migrated_from,source_sha256,created_at,updated_at
          FROM workspace_state WHERE workspace_id=?""",(workspace_id,)).fetchone()
        revisions=db.execute("SELECT COUNT(*) FROM workspace_revisions WHERE workspace_id=?",(workspace_id,)).fetchone()[0]
        entity_counts={kind:db.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?",(workspace_id,)).fetchone()[0]
                       for kind,table in _ENTITY_TABLES.items()}
    return ({"backend":"sqlite_normalized","database":str(DB_PATH),"schema_version":2,
             "revision_count":revisions,"entity_counts":entity_counts,**dict(row)} if row
            else {"backend":"sqlite","database":str(DB_PATH),"revision_count":0,"revision":0})


def accept_tenant_candidate(workspace_id, candidate_id, project_id=None, title=None, intent=None, next_action=None):
    """Atomically accept a hosted candidate and materialize its governed workspace entity."""
    initialize(); now=_now()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        candidate=db.execute("SELECT * FROM tenant_candidates WHERE id=? AND workspace_id=? AND status='pending'",
                             (candidate_id,workspace_id)).fetchone()
        if not candidate: raise KeyError("Pending candidate not found")
        state=db.execute("SELECT document_json,revision FROM workspace_state WHERE workspace_id=?",(workspace_id,)).fetchone()
        if not state: raise RuntimeError("Workspace must exist before accepting a candidate")
        document=_hydrate_entities(db,json.loads(state["document_json"]),workspace_id)
        if project_id and not any((item.get("project_id") or item.get("id"))==project_id for item in document.get("projects",[])):
            raise ValueError("Project not found")
        entity_id=uuid.uuid4().hex
        if candidate["kind"]=="decision":
            document.setdefault("decisions",[]).append({"decision_id":entity_id,"project_id":project_id,
                "candidate_id":candidate_id,"statement":str(title or candidate["title"]),
                "rationale":str(intent or candidate["interpretation"]),"status":"active",
                "source_conversation_id":candidate["conversation_id"],"source_message_id":candidate["message_id"],"created_at":now})
            entity_key="decision_id"
        else:
            document.setdefault("seeds",[]).append({"seed_id":entity_id,"project_id":project_id,
                "candidate_id":candidate_id,"title":str(title or candidate["title"]),
                "intent":str(intent or candidate["interpretation"]),"status":"Active",
                "continuity_status":"User Confirmed","source_conversation_id":candidate["conversation_id"],
                "source_message_id":candidate["message_id"],"next_action":str(next_action or "Review the source context and choose the next concrete action."),
                "created_at":now,"updated_at":now})
            entity_key="seed_id"
        revision=state["revision"]+1; encoded=json.dumps(document,ensure_ascii=False)
        _sync_entities(db,document,workspace_id)
        db.execute("UPDATE workspace_state SET document_json=?,revision=?,updated_at=? WHERE workspace_id=?",(encoded,revision,now,workspace_id))
        db.execute("INSERT INTO workspace_revisions VALUES(?,?,?,?,?)",(workspace_id,revision,encoded,"candidate_accepted_atomic",now))
        changed=db.execute("UPDATE tenant_candidates SET status='accepted',reviewed_at=? WHERE id=? AND workspace_id=? AND status='pending'",
                           (now,candidate_id,workspace_id)).rowcount
        if changed!=1: raise RuntimeError("Candidate acceptance lost its concurrency race")
    result=dict(candidate); result["status"]="accepted"
    return {"candidate":result,"status":"accepted",entity_key:entity_id}
