"""Seed Reflections integrated product runtime.

One codebase supports local, hosted, and enterprise deployment modes.  Local mode
is the default; hosted capabilities remain dormant unless explicitly enabled.
The runtime uses only the Python standard library so a recovered archive remains
usable without a package registry or cloud dependency.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("SEED_REFLECTIONS_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "seed_reflections.db"
PORT = int(os.environ.get("SEED_REFLECTIONS_PORT", "8477"))
MODE = os.environ.get("SEED_REFLECTIONS_MODE", "local").strip().lower()
if MODE not in {"local", "hosted", "enterprise"}:
    raise RuntimeError("SEED_REFLECTIONS_MODE must be local, hosted, or enterprise")
HOST = os.environ.get("SEED_REFLECTIONS_HOST", "127.0.0.1" if MODE == "local" else "0.0.0.0")
SESSION_HOURS = int(os.environ.get("SEED_REFLECTIONS_SESSION_HOURS", "24"))
MAX_BODY_BYTES = int(os.environ.get("SEED_REFLECTIONS_MAX_IMPORT_BYTES", str(250 * 1024 * 1024)))
BILLING_ENABLED = os.environ.get("SEED_REFLECTIONS_BILLING_ENABLED", "0") == "1"
EXTERNAL_AI_ENABLED = os.environ.get("SEED_REFLECTIONS_EXTERNAL_AI_ENABLED", "0") == "1"
TEAM_ENABLED = os.environ.get("SEED_REFLECTIONS_TEAM_ENABLED", "0") == "1"
DB_LOCK = threading.RLock()


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, password_hash TEXT, role TEXT NOT NULL DEFAULT 'owner',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  filename TEXT NOT NULL, platform TEXT NOT NULL, sha256 TEXT NOT NULL, schema_version TEXT NOT NULL,
  status TEXT NOT NULL, conversation_count INTEGER NOT NULL DEFAULT 0,
  message_count INTEGER NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE, source_id TEXT,
  platform TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT, updated_at TEXT,
  message_count INTEGER NOT NULL DEFAULT 0, analysis_status TEXT NOT NULL DEFAULT 'not_analyzed'
);
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id, updated_at);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  source_id TEXT, parent_source_id TEXT, ordinal INTEGER NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, ordinal);
CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING fts5(
  message_id UNINDEXED, workspace_id UNINDEXED, conversation_id UNINDEXED, title, content
);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL, mission TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  kind TEXT NOT NULL, title TEXT NOT NULL, interpretation TEXT NOT NULL,
  confidence REAL NOT NULL, rationale TEXT NOT NULL, extraction_method TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', reviewed_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidates_review ON candidates(workspace_id, status, created_at);
CREATE TABLE IF NOT EXISTS candidate_evidence (
  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  excerpt TEXT NOT NULL, evidence_type TEXT NOT NULL DEFAULT 'direct'
);
CREATE TABLE IF NOT EXISTS seeds (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
  candidate_id TEXT REFERENCES candidates(id) ON DELETE SET NULL,
  title TEXT NOT NULL, intent TEXT NOT NULL, lifecycle TEXT NOT NULL DEFAULT 'inbox',
  authority TEXT NOT NULL DEFAULT 'user_confirmed', continuity TEXT NOT NULL DEFAULT 'active',
  source_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  source_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
  recovery_suggestion TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seeds_workspace ON seeds(workspace_id, lifecycle, continuity);
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  statement TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', source_message_id TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  event_type TEXT NOT NULL, entity_type TEXT, entity_id TEXT, detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  workspace_id TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL,
  PRIMARY KEY(workspace_id, key)
);
"""


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()
    )


def password_valid(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        _, rounds, salt, expected = encoded.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.urlsafe_b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
    except Exception:
        return False


def issue_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(40)
    token_digest = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    conn.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
        (token_digest, user_id, expires, utcnow()),
    )
    return token


def initialize() -> None:
    with DB_LOCK, connect() as conn:
        conn.executescript(SCHEMA)
        if MODE == "local":
            conn.execute(
                "INSERT OR IGNORE INTO workspaces(id,name,mode,created_at) VALUES('local','My Archive','local',?)",
                (utcnow(),),
            )
            conn.execute(
                """INSERT OR IGNORE INTO users(id,workspace_id,email,name,password_hash,role,created_at)
                   VALUES('local-owner','local','local@seedreflections.internal','Local Owner',NULL,'owner',?)""",
                (utcnow(),),
            )
            conn.execute(
                """INSERT OR IGNORE INTO projects(id,workspace_id,name,mission,status,created_at,updated_at)
                   VALUES('inbox','local','Unsorted Ideas','Ideas awaiting project assignment','active',?,?)""",
                (utcnow(), utcnow()),
            )
        conn.commit()
    if MODE == "local" and os.environ.get("SEED_REFLECTIONS_MIGRATE_LEGACY", "1") == "1":
        migrate_legacy_if_needed()


def migrate_legacy_if_needed() -> None:
    """Import the existing JSON workspace once without modifying legacy files."""
    legacy_path = ROOT / "seeds.json"
    if not legacy_path.exists():
        return
    with DB_LOCK, connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM seeds WHERE workspace_id='local'").fetchone()[0]:
            return
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Legacy migration skipped: {exc}", file=sys.stderr)
            return
        if isinstance(legacy, list):
            legacy = {"seeds": legacy}
        project_map = {"default_project": "inbox", None: "inbox", "": "inbox"}
        for old in legacy.get("projects", []):
            old_id = old.get("project_id") or old.get("id")
            if not old_id or old_id == "default_project":
                continue
            project_id = uuid.uuid4().hex
            project_map[old_id] = project_id
            conn.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?,?)", (
                project_id, "local", old.get("name") or old.get("title") or "Imported Project",
                old.get("purpose") or old.get("mission") or old.get("description") or "",
                "active", old.get("created_at") or utcnow(), old.get("updated_at") or utcnow()))
        conversation_map = {}
        for old in legacy.get("seeds", []):
            transcript_id = old.get("source_transcript_id")
            conversation_id = None; message_id = None
            if transcript_id:
                if transcript_id in conversation_map:
                    conversation_id, message_id = conversation_map[transcript_id]
                else:
                    transcript_path = ROOT / "transcripts" / f"{transcript_id}.txt"
                    transcript_text = transcript_path.read_text(encoding="utf-8", errors="replace") if transcript_path.exists() else (old.get("source_excerpt") or old.get("intent") or old.get("description") or "")
                    import_id = "legacy-" + hashlib.sha256(str(transcript_id).encode()).hexdigest()[:20]
                    conversation_id = "legacy-conv-" + hashlib.sha256(str(transcript_id).encode()).hexdigest()[:20]
                    message_id = "legacy-msg-" + hashlib.sha256(str(transcript_id).encode()).hexdigest()[:20]
                    conn.execute("INSERT OR IGNORE INTO imports VALUES(?,?,?,?,?,?,?,?,?,?,?)", (import_id, "local", "legacy-workspace", old.get("source_platform") or "unknown", hashlib.sha256(transcript_text.encode()).hexdigest(), "legacy", "ready", 1, 1, None, old.get("created_at") or utcnow()))
                    conn.execute("INSERT OR IGNORE INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?)", (conversation_id, "local", import_id, str(transcript_id), old.get("source_platform") or "unknown", old.get("source_thread_title") or "Imported legacy conversation", old.get("created_at"), old.get("modified_at") or old.get("created_at"), 1, "legacy_imported"))
                    conn.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (message_id, "local", conversation_id, old.get("source_message_id") or message_id, None, 0, "user", transcript_text, old.get("source_timestamp") or old.get("created_at")))
                    conn.execute("INSERT INTO message_search VALUES(?,?,?,?,?)", (message_id, "local", conversation_id, old.get("source_thread_title") or "Imported legacy conversation", transcript_text))
                    conversation_map[transcript_id] = (conversation_id, message_id)
            title = old.get("title") or old.get("intent") or old.get("description") or "Untitled imported idea"
            intent = old.get("intent") or old.get("description") or title
            old_status = str(old.get("status") or "inbox").lower()
            lifecycle = {"planted": "inbox", "growing": "active", "bloomed": "done", "completed": "done", "wilted": "archived"}.get(old_status, old_status if old_status in {"inbox","active","done","archived"} else "inbox")
            continuity = str(old.get("continuity_status") or "active").lower()
            if continuity not in {"active","dormant","lost","recovered","restored","replaced","historical","superseded"}: continuity = "active"
            conn.execute("INSERT OR IGNORE INTO seeds VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                str(old.get("seed_id") or uuid.uuid4().hex), "local", project_map.get(old.get("project_id"), "inbox"), None,
                title, intent, lifecycle, "legacy_unverified", continuity, conversation_id, message_id,
                old.get("recovery_suggestion") or "Review the original source and choose a next action.",
                old.get("created_at") or utcnow(), old.get("modified_at") or old.get("created_at") or utcnow()))
        conn.execute("INSERT OR REPLACE INTO settings VALUES('local','legacy_migration',?)", (json.dumps({"completed_at": utcnow(), "source": str(legacy_path), "seed_count": len(legacy.get('seeds', []))}),))
        conn.commit()


def flatten_content(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten_content(v) for v in value if flatten_content(v))
    if isinstance(value, dict):
        if "parts" in value:
            return flatten_content(value["parts"])
        return flatten_content(value.get("text") or value.get("content") or value.get("value"))
    return str(value)


def iso_time(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except Exception:
            return None
    return str(value)


def detect_platform(data, hint: str = "") -> str:
    if isinstance(data, list) and data:
        sample = next((x for x in data if isinstance(x, dict)), {})
        if "mapping" in sample:
            return "chatgpt"
        if "chat_messages" in sample:
            return "claude"
    text = hint.lower()
    return "chatgpt" if "chatgpt" in text else "claude" if "claude" in text else "generic"


def normalize_export(data, platform: str):
    if not isinstance(data, list):
        raise ValueError("Expected an array of conversations")
    for index, raw in enumerate(data):
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("id") or raw.get("uuid") or f"conversation-{index+1}")
        title = str(raw.get("title") or raw.get("name") or raw.get("subject") or f"Conversation {index+1}")
        messages = []
        if platform == "chatgpt" and isinstance(raw.get("mapping"), dict):
            nodes = raw["mapping"]
            ordered = []
            for node_id, node in nodes.items():
                msg = node.get("message") if isinstance(node, dict) else None
                if not msg:
                    continue
                created = msg.get("create_time")
                ordered.append((created if isinstance(created, (int, float)) else 0, node_id, node, msg))
            ordered.sort(key=lambda x: (x[0], x[1]))
            for ordinal, (_, node_id, node, msg) in enumerate(ordered):
                content = flatten_content(msg.get("content"))
                if not content.strip():
                    continue
                messages.append({
                    "source_id": str(msg.get("id") or node_id),
                    "parent_source_id": node.get("parent"),
                    "role": str((msg.get("author") or {}).get("role") or "unknown"),
                    "content": content.strip(), "created_at": iso_time(msg.get("create_time")),
                    "ordinal": ordinal,
                })
        else:
            raw_messages = raw.get("chat_messages") or raw.get("messages") or []
            for ordinal, msg in enumerate(raw_messages if isinstance(raw_messages, list) else []):
                if not isinstance(msg, dict):
                    continue
                content = flatten_content(msg.get("text") or msg.get("content"))
                if not content.strip():
                    continue
                role = msg.get("role") or msg.get("sender") or msg.get("author") or "unknown"
                messages.append({"source_id": str(msg.get("id") or f"{source_id}-{ordinal}"),
                    "parent_source_id": None, "role": str(role), "content": content.strip(),
                    "created_at": iso_time(msg.get("created_at") or msg.get("create_time")), "ordinal": ordinal})
        yield {"source_id": source_id, "title": title, "created_at": iso_time(raw.get("create_time") or raw.get("created_at")),
               "updated_at": iso_time(raw.get("update_time") or raw.get("updated_at")), "messages": messages}


INTENT_PATTERNS = [
    ("decision", re.compile(r"\b(?:we decided|decision:|we will use|we chose|must use)\s+(.{12,260})", re.I)),
    ("constraint", re.compile(r"\b(?:must not|cannot|never|requirement:|constraint:)\s+(.{12,260})", re.I)),
    ("task", re.compile(r"\b(?:next step|todo|need to|have to)\s+(.{12,260})", re.I)),
    ("idea", re.compile(r"\b(?:i want to|we should|let's|idea:|what if we|could build)\s+(.{12,260})", re.I)),
]


def candidate_title(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip(" -*#\t\r\n.?!")
    words = clean.split()
    return " ".join(words[:12]) + ("…" if len(words) > 12 else "")


def extract_candidates(messages: list[sqlite3.Row]):
    found = []
    seen = set()
    for message in messages:
        if message["role"].lower() not in {"user", "human", "customer"}:
            continue
        text = message["content"]
        for kind, pattern in INTENT_PATTERNS:
            for match in pattern.finditer(text):
                value = re.split(r"[\n.!?](?:\s|$)", match.group(1).strip(), maxsplit=1)[0].strip()
                key = re.sub(r"\W+", " ", value.lower()).strip()
                if len(key) < 12 or key in seen:
                    continue
                seen.add(key)
                markers = sum(1 for token in ("must", "need", "decided", "important", "should") if token in match.group(0).lower())
                confidence = min(0.88, 0.58 + markers * 0.08 + min(len(value), 160) / 1600)
                found.append({"kind": kind, "title": candidate_title(value), "interpretation": value,
                    "confidence": round(confidence, 2),
                    "rationale": f"Direct {kind} language in a user-authored message. Requires human confirmation.",
                    "message_id": message["id"], "excerpt": match.group(0)[:600]})
    return found


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    server_version = "SeedReflections/2"

    def log_message(self, fmt, *args):
        if os.environ.get("SEED_REFLECTIONS_QUIET") != "1":
            super().log_message(fmt, *args)

    def headers_common(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
        self.send_header("Cache-Control", "no-store")

    def json_response(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def text_response(self, value: str, content_type="text/html; charset=utf-8", status=200):
        body = value.encode()
        self.send_response(status); self.headers_common()
        self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def body_json(self):
        try: length = int(self.headers.get("Content-Length", "0"))
        except ValueError: raise APIError(400, "Invalid content length")
        if length > MAX_BODY_BYTES: raise APIError(413, "Import exceeds configured size limit")
        try: return json.loads(self.rfile.read(length) or b"{}")
        except Exception: raise APIError(400, "Invalid JSON body")

    def current_user(self, conn, required=True):
        if MODE == "local":
            return conn.execute("SELECT * FROM users WHERE id='local-owner'").fetchone()
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if token:
            digest = hashlib.sha256(token.encode()).hexdigest()
            row = conn.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                                  WHERE s.token_hash=? AND s.expires_at>?""", (digest, utcnow())).fetchone()
            if row: return row
        if required: raise APIError(401, "Authentication required")
        return None

    def route(self, method):
        parsed = urlparse(self.path); path = parsed.path; query = parse_qs(parsed.query)
        if path in {"/", "/app", "/product.html"} and method == "GET":
            return self.text_response((ROOT / "product.html").read_text(encoding="utf-8"))
        if path == "/api/v2/capabilities" and method == "GET":
            return self.json_response({"mode": MODE, "billing": BILLING_ENABLED, "external_ai": EXTERNAL_AI_ENABLED,
                "teams": TEAM_ENABLED, "local_first": True, "product_version": 2})
        if path == "/api/v2/health" and method == "GET":
            return self.json_response({"status": "healthy", "mode": MODE, "database": "sqlite", "time": utcnow()})
        if path == "/api/v2/auth/signup" and method == "POST":
            if MODE == "local": raise APIError(409, "Local mode uses the device owner and does not require an account")
            data = self.body_json(); email = str(data.get("email", "")).strip().lower(); password = str(data.get("password", "")); name = str(data.get("name", "")).strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(password) < 12 or not name:
                raise APIError(400, "Name, valid email, and a password of at least 12 characters are required")
            with DB_LOCK, connect() as conn:
                if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone(): raise APIError(409, "Account already exists")
                workspace_id, user_id = uuid.uuid4().hex, uuid.uuid4().hex
                conn.execute("INSERT INTO workspaces VALUES(?,?,?,?)", (workspace_id, f"{name}'s Archive", MODE, utcnow()))
                conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (user_id, workspace_id, email, name, password_hash(password), "owner", utcnow()))
                conn.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?)", (uuid.uuid4().hex, workspace_id, "Unsorted Ideas", "Ideas awaiting project assignment", "active", utcnow(), utcnow()))
                token = issue_session(conn, user_id); conn.commit()
            return self.json_response({"access_token": token, "user": {"id": user_id, "name": name, "email": email}}, 201)
        if path == "/api/v2/auth/login" and method == "POST":
            data = self.body_json(); email = str(data.get("email", "")).strip().lower(); password = str(data.get("password", ""))
            with DB_LOCK, connect() as conn:
                user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if not user or not password_valid(password, user["password_hash"]): raise APIError(401, "Invalid credentials")
                token = issue_session(conn, user["id"]); conn.commit()
            return self.json_response({"access_token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}})

        if path == "/api/v2/auth/logout" and method == "POST":
            if MODE == "local":
                return self.json_response({"status": "local_session"})
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.startswith("Bearer ") else ""
            if token:
                with DB_LOCK, connect() as conn:
                    conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
                    conn.commit()
            return self.json_response({"status": "signed_out"})

        with DB_LOCK, connect() as conn:
            user = self.current_user(conn); workspace = user["workspace_id"]
            if path == "/api/v2/overview" and method == "GET":
                counts = {}
                for name, table in (("imports","imports"),("conversations","conversations"),("messages","messages"),("pending","candidates"),("seeds","seeds"),("projects","projects")):
                    where = "workspace_id=?" + (" AND status='pending'" if name == "pending" else "")
                    counts[name] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", (workspace,)).fetchone()[0]
                recovered = conn.execute("SELECT COUNT(*) FROM seeds WHERE workspace_id=? AND continuity='recovered'", (workspace,)).fetchone()[0]
                counts["recovered"] = recovered
                return self.json_response(counts)
            if path == "/api/v2/imports" and method == "POST":
                data = self.body_json(); filename = Path(str(data.get("filename") or "export.json")).name
                archive = data.get("data"); raw = json.dumps(archive, ensure_ascii=False, separators=(",", ":")).encode()
                platform = str(data.get("platform") or "auto").lower()
                if platform == "auto": platform = detect_platform(archive, filename)
                import_id = uuid.uuid4().hex; conversations = list(normalize_export(archive, platform)); message_total = sum(len(c["messages"]) for c in conversations)
                conn.execute("INSERT INTO imports VALUES(?,?,?,?,?,?,?,?,?,?,?)", (import_id, workspace, filename, platform, hashlib.sha256(raw).hexdigest(), "v2", "processing", 0, 0, None, utcnow()))
                for conversation in conversations:
                    conversation_id = uuid.uuid4().hex
                    conn.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?)", (conversation_id, workspace, import_id, conversation["source_id"], platform, conversation["title"], conversation["created_at"], conversation["updated_at"], len(conversation["messages"]), "not_analyzed"))
                    for msg in conversation["messages"]:
                        message_id = uuid.uuid4().hex
                        conn.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)", (message_id, workspace, conversation_id, msg["source_id"], msg["parent_source_id"], msg["ordinal"], msg["role"], msg["content"], msg["created_at"]))
                        conn.execute("INSERT INTO message_search VALUES(?,?,?,?,?)", (message_id, workspace, conversation_id, conversation["title"], msg["content"]))
                conn.execute("UPDATE imports SET status='ready',conversation_count=?,message_count=? WHERE id=?", (len(conversations), message_total, import_id)); conn.commit()
                return self.json_response({"id": import_id, "platform": platform, "conversations": len(conversations), "messages": message_total}, 201)
            if path == "/api/v2/conversations" and method == "GET":
                search = (query.get("q") or [""])[0].strip(); params = [workspace]
                if search:
                    sql = """SELECT DISTINCT c.* FROM message_search f JOIN conversations c ON c.id=f.conversation_id
                             WHERE f.workspace_id=? AND message_search MATCH ? ORDER BY c.updated_at DESC LIMIT 200"""; params.append(search.replace('"',' '))
                else:
                    sql = "SELECT * FROM conversations WHERE workspace_id=? ORDER BY COALESCE(updated_at,created_at) DESC LIMIT 500"
                rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
                return self.json_response({"conversations": rows})
            match = re.fullmatch(r"/api/v2/conversations/([^/]+)", path)
            if match and method == "GET":
                conv = conn.execute("SELECT * FROM conversations WHERE id=? AND workspace_id=?", (match.group(1), workspace)).fetchone()
                if not conv: raise APIError(404, "Conversation not found")
                messages = [dict(r) for r in conn.execute("SELECT * FROM messages WHERE conversation_id=? AND workspace_id=? ORDER BY ordinal", (conv["id"], workspace))]
                return self.json_response({"conversation": dict(conv), "messages": messages})
            match = re.fullmatch(r"/api/v2/conversations/([^/]+)/analyze", path)
            if match and method == "POST":
                conv = conn.execute("SELECT * FROM conversations WHERE id=? AND workspace_id=?", (match.group(1), workspace)).fetchone()
                if not conv: raise APIError(404, "Conversation not found")
                messages = conn.execute("SELECT * FROM messages WHERE conversation_id=? AND workspace_id=? ORDER BY ordinal", (conv["id"], workspace)).fetchall()
                candidates = extract_candidates(messages); created = []
                for candidate in candidates:
                    candidate_id = uuid.uuid4().hex
                    conn.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (candidate_id, workspace, conv["id"], None, candidate["kind"], candidate["title"], candidate["interpretation"], candidate["confidence"], candidate["rationale"], "local_evidence_rules_v2", "pending", None, utcnow()))
                    conn.execute("INSERT INTO candidate_evidence VALUES(?,?,?,?,?)", (uuid.uuid4().hex, candidate_id, candidate["message_id"], candidate["excerpt"], "direct")); created.append(candidate_id)
                conn.execute("UPDATE conversations SET analysis_status='analyzed' WHERE id=?", (conv["id"],)); conn.commit()
                return self.json_response({"candidates_created": len(created), "method": "local_evidence_rules_v2", "abstained": len(created) == 0})
            if path == "/api/v2/candidates" and method == "GET":
                status = (query.get("status") or ["pending"])[0]
                rows = conn.execute("""SELECT c.*,cv.title conversation_title,cv.platform,
                    e.excerpt,e.message_id FROM candidates c JOIN conversations cv ON cv.id=c.conversation_id
                    LEFT JOIN candidate_evidence e ON e.candidate_id=c.id
                    WHERE c.workspace_id=? AND c.status=? ORDER BY c.created_at DESC""", (workspace, status)).fetchall()
                return self.json_response({"candidates": [dict(r) for r in rows]})
            match = re.fullmatch(r"/api/v2/candidates/([^/]+)/review", path)
            if match and method == "POST":
                data = self.body_json(); action = str(data.get("action", "")); candidate = conn.execute("SELECT * FROM candidates WHERE id=? AND workspace_id=?", (match.group(1), workspace)).fetchone()
                if not candidate or candidate["status"] != "pending": raise APIError(404, "Pending candidate not found")
                if action not in {"accept", "reject", "defer"}: raise APIError(400, "Action must be accept, reject, or defer")
                if action == "accept":
                    evidence = conn.execute("SELECT * FROM candidate_evidence WHERE candidate_id=? LIMIT 1", (candidate["id"],)).fetchone()
                    seed_id = uuid.uuid4().hex; title = str(data.get("title") or candidate["title"]).strip(); intent = str(data.get("intent") or candidate["interpretation"]).strip(); project_id = data.get("project_id")
                    if project_id and not conn.execute("SELECT 1 FROM projects WHERE id=? AND workspace_id=?", (project_id, workspace)).fetchone(): raise APIError(400, "Project not found")
                    conn.execute("INSERT INTO seeds VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (seed_id, workspace, project_id, candidate["id"], title, intent, "inbox", "user_confirmed", "active", candidate["conversation_id"], evidence["message_id"] if evidence else None, str(data.get("next_action") or "Review the source context and choose the next concrete action."), utcnow(), utcnow()))
                    result = {"seed_id": seed_id}
                else: result = {}
                conn.execute("UPDATE candidates SET status=?,reviewed_at=? WHERE id=?", ({"accept":"accepted","reject":"rejected","defer":"deferred"}[action], utcnow(), candidate["id"]))
                conn.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, workspace, user["id"], f"candidate.{action}", "candidate", candidate["id"], json.dumps(result), utcnow())); conn.commit()
                return self.json_response({"status": "ok", **result})
            if path == "/api/v2/projects" and method == "GET":
                projects = []
                for row in conn.execute("SELECT * FROM projects WHERE workspace_id=? ORDER BY updated_at DESC", (workspace,)):
                    obj = dict(row); obj["seed_count"] = conn.execute("SELECT COUNT(*) FROM seeds WHERE project_id=?", (row["id"],)).fetchone()[0]; projects.append(obj)
                return self.json_response({"projects": projects})
            if path == "/api/v2/projects" and method == "POST":
                data = self.body_json(); name = str(data.get("name", "")).strip(); mission = str(data.get("mission", "")).strip()
                if not name: raise APIError(400, "Project name is required")
                project_id = uuid.uuid4().hex; conn.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?)", (project_id, workspace, name, mission, "active", utcnow(), utcnow())); conn.commit()
                return self.json_response({"id": project_id}, 201)
            if path == "/api/v2/recovery" and method == "GET":
                rows = conn.execute("""SELECT s.*,c.title conversation_title,m.content source_text,
                    CAST(julianday('now')-julianday(s.updated_at) AS INTEGER) dormant_days
                    FROM seeds s LEFT JOIN conversations c ON c.id=s.source_conversation_id
                    LEFT JOIN messages m ON m.id=s.source_message_id
                    WHERE s.workspace_id=? AND s.lifecycle NOT IN ('done','archived')
                    ORDER BY dormant_days DESC""", (workspace,)).fetchall()
                items = []
                for row in rows:
                    item = dict(row); days = max(0, item.get("dormant_days") or 0)
                    item["recovery_score"] = min(100, 35 + min(days, 180) // 3 + (15 if item.get("source_message_id") else 0))
                    item["reason"] = f"User-confirmed idea remains {item['lifecycle']} with no completion or rejection record. Source evidence is preserved."
                    items.append(item)
                return self.json_response({"recovery_candidates": items})
            match = re.fullmatch(r"/api/v2/seeds/([^/]+)/resume", path)
            if match and method == "POST":
                changed = conn.execute("UPDATE seeds SET lifecycle='active',continuity='recovered',updated_at=? WHERE id=? AND workspace_id=?", (utcnow(), match.group(1), workspace)).rowcount
                if not changed: raise APIError(404, "Seed not found")
                conn.commit(); return self.json_response({"status": "recovered"})
            match = re.fullmatch(r"/api/v2/projects/([^/]+)/context", path)
            if match and method == "GET":
                project = conn.execute("SELECT * FROM projects WHERE id=? AND workspace_id=?", (match.group(1), workspace)).fetchone()
                if not project: raise APIError(404, "Project not found")
                seeds = conn.execute("SELECT * FROM seeds WHERE project_id=? AND workspace_id=? AND lifecycle!='archived'", (project["id"], workspace)).fetchall()
                decisions = conn.execute("SELECT * FROM decisions WHERE project_id=? AND workspace_id=? AND status='active'", (project["id"], workspace)).fetchall()
                lines = [f"# Project Context: {project['name']}", "", "## Mission", project["mission"] or "Not yet defined.", "", "## Confirmed Ideas"]
                lines += [f"- **{s['title']}** — {s['intent']} (state: {s['lifecycle']})" for s in seeds] or ["- No confirmed ideas yet."]
                lines += ["", "## Decisions"] + ([f"- {d['statement']}" for d in decisions] or ["- No active decisions recorded."])
                lines += ["", "## Operating instruction", "Treat this package as user-reviewed context. Ask before changing the mission or superseding confirmed decisions."]
                return self.json_response({"project": dict(project), "markdown": "\n".join(lines), "seed_count": len(seeds), "decision_count": len(decisions)})
        raise APIError(404, "Endpoint not found")

    def dispatch(self, method):
        try: self.route(method)
        except APIError as exc: self.json_response({"error": exc.message}, exc.status)
        except Exception as exc:
            self.json_response({"error": "Internal error", "request_id": uuid.uuid4().hex[:12]}, 500)
            print(f"Seed Reflections error: {exc}", file=sys.stderr)

    def do_GET(self): self.dispatch("GET")
    def do_POST(self): self.dispatch("POST")


def run():
    initialize()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Seed Reflections v2 — {MODE} mode — http://{HOST}:{PORT}")
    print(f"Data: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    run()
