"""Persistent archive normalization for Seed Reflections.

This module owns imported conversation records and their source messages.  It is
deliberately independent of the presentation layer so local, hosted, and
enterprise runtimes can use the same archive contract.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import sqlite3
import uuid
import shutil
import itertools
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SEED_REFLECTIONS_DATA_DIR", ROOT / "data")) / "archive.db"


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
        CREATE TABLE IF NOT EXISTS imports(
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, platform TEXT NOT NULL,
          sha256 TEXT NOT NULL, conversation_count INTEGER NOT NULL,
          message_count INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversations(
          id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
          source_id TEXT, platform TEXT NOT NULL, title TEXT NOT NULL,
          snippet TEXT NOT NULL, created_at TEXT, updated_at TEXT,
          message_count INTEGER NOT NULL, raw_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS archive_conversations_recent
          ON conversations(COALESCE(updated_at, created_at), title);
        CREATE TABLE IF NOT EXISTS messages(
          id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
          source_id TEXT, parent_source_id TEXT, ordinal INTEGER NOT NULL,
          role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS archive_messages_conversation
          ON messages(conversation_id, ordinal);
        CREATE VIRTUAL TABLE IF NOT EXISTS archive_search USING fts5(
          conversation_id UNINDEXED, title, content
        );
        CREATE TABLE IF NOT EXISTS source_files(
          id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
          filename TEXT NOT NULL, media_type TEXT NOT NULL, sha256 TEXT NOT NULL,
          byte_count INTEGER NOT NULL, content BLOB NOT NULL, coverage_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS import_jobs(
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, status TEXT NOT NULL,
          stage TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
          error TEXT, result_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS idea_candidates(
          id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
          message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, title TEXT NOT NULL, interpretation TEXT NOT NULL,
          excerpt TEXT NOT NULL, confidence REAL NOT NULL, rationale TEXT NOT NULL,
          extraction_method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          reviewed_at TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS candidate_review_queue ON idea_candidates(status,created_at);
        CREATE TABLE IF NOT EXISTS conversation_analysis(
          conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
          method TEXT NOT NULL, status TEXT NOT NULL, candidate_count INTEGER NOT NULL DEFAULT 0,
          analyzed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analysis_jobs(
          id TEXT PRIMARY KEY, status TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0,
          processed INTEGER NOT NULL DEFAULT 0, candidates_created INTEGER NOT NULL DEFAULT 0,
          existing_candidates INTEGER NOT NULL DEFAULT 0, abstained INTEGER NOT NULL DEFAULT 0,
          error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidate_links(
          id TEXT PRIMARY KEY,
          left_candidate_id TEXT NOT NULL REFERENCES idea_candidates(id) ON DELETE CASCADE,
          right_candidate_id TEXT NOT NULL REFERENCES idea_candidates(id) ON DELETE CASCADE,
          relation_type TEXT NOT NULL, shared_terms_json TEXT NOT NULL, score REAL NOT NULL,
          rationale TEXT NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          reviewed_at TEXT, created_at TEXT NOT NULL,
          UNIQUE(left_candidate_id,right_candidate_id)
        );
        CREATE INDEX IF NOT EXISTS candidate_link_review_queue ON candidate_links(status,score DESC);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(source_files)")}
        if "source_path" not in columns:
            db.execute("ALTER TABLE source_files ADD COLUMN source_path TEXT")
    _migrate_existing_archive_once()


def _migrate_existing_archive_once():
    """Carry forward conversations normalized by the earlier runtime."""
    if DB_PATH.resolve() != (ROOT / "data" / "archive.db").resolve():
        return
    previous = ROOT / "data" / "seed_reflections.db"
    if not previous.exists() or previous.resolve() == DB_PATH.resolve():
        return
    with _connect() as target:
        if target.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]:
            return
        source = sqlite3.connect(previous)
        source.row_factory = sqlite3.Row
        try:
            rows = source.execute("SELECT * FROM conversations ORDER BY COALESCE(updated_at,created_at)").fetchall()
            if not rows:
                return
            import_id = "existing-archive-migration"
            all_messages = 0
            target.execute("INSERT OR IGNORE INTO imports VALUES(?,?,?,?,?,?,?)", (
                import_id, "Existing Seed Reflections Archive", "mixed", "legacy-normalized",
                len(rows), 0, _now(),
            ))
            for conversation in rows:
                messages = source.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY ordinal", (conversation["id"],)).fetchall()
                raw = {"id": conversation["source_id"], "title": conversation["title"], "messages": [
                    {"id": m["source_id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                    for m in messages
                ]}
                first_user = next((m["content"] for m in messages if m["role"].lower() in {"user", "human", "customer"}), "")
                target.execute("INSERT OR IGNORE INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    conversation["id"], import_id, conversation["source_id"], conversation["platform"],
                    conversation["title"], " ".join(first_user.split())[:240], conversation["created_at"],
                    conversation["updated_at"], len(messages), json.dumps(raw, ensure_ascii=False),
                ))
                for message in messages:
                    target.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?)", (
                        message["id"], conversation["id"], message["source_id"], message["parent_source_id"],
                        message["ordinal"], message["role"], message["content"], message["created_at"],
                    ))
                    target.execute("INSERT INTO archive_search VALUES(?,?,?)", (conversation["id"], conversation["title"], message["content"]))
                all_messages += len(messages)
            target.execute("UPDATE imports SET message_count=? WHERE id=?", (all_messages, import_id))
        finally:
            source.close()


def _text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_text(item) for item in value)))
    if isinstance(value, dict):
        return _text(value.get("parts") or value.get("text") or value.get("content") or value.get("value"))
    return str(value)


def _timestamp(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    return str(value)


def _platform(data, filename):
    sample = next((item for item in data if isinstance(item, dict)), {})
    explicit = sample.get("platform") or sample.get("provider") or sample.get("source_platform")
    if explicit:
        return re.sub(r"[^a-z0-9_-]+", "_", str(explicit).strip().lower()).strip("_") or "unknown"
    if "mapping" in sample:
        return "chatgpt"
    if "chat_messages" in sample:
        return "claude"
    if "chunkedPrompt" in sample or "modelResponse" in sample or sample.get("platform") == "gemini":
        return "gemini"
    if "rollout" in sample or "turns" in sample or sample.get("platform") == "codex":
        return "codex"
    name = filename.lower()
    aliases = {
        "openai":"chatgpt", "chatgpt":"chatgpt", "claude":"claude", "anthropic":"claude",
        "gemini":"gemini", "bard":"gemini", "codex":"codex", "deepseek":"deepseek",
        "perplexity":"perplexity", "grok":"grok", "xai":"grok", "mistral":"mistral",
        "qwen":"qwen", "openrouter":"openrouter", "cursor":"cursor", "copilot":"copilot",
    }
    for provider, normalized in aliases.items():
        if provider in name: return normalized
    return "generic"


def _messages(raw, source_id):
    result = []
    mapping = raw.get("mapping")
    if isinstance(mapping, dict):
        staged = []
        for node_id, node in mapping.items():
            message = node.get("message") if isinstance(node, dict) else None
            if not isinstance(message, dict):
                continue
            content = _text(message.get("content")).strip()
            if not content:
                continue
            created = message.get("create_time")
            staged.append((created if isinstance(created, (int, float)) else 0, str(node_id), node, message, content))
        staged.sort(key=lambda item: (item[0], item[1]))
        for ordinal, (_, node_id, node, message, content) in enumerate(staged):
            result.append({
                "source_id": str(message.get("id") or node_id),
                "parent_source_id": node.get("parent"),
                "ordinal": ordinal,
                "role": str((message.get("author") or {}).get("role") or "unknown"),
                "content": content,
                "created_at": _timestamp(message.get("create_time")),
            })
        return result
    items = raw.get("chat_messages") or raw.get("messages") or raw.get("turns") or raw.get("items") or []
    if not items and (raw.get("chunkedPrompt") is not None or raw.get("modelResponse") is not None):
        items = []
        if raw.get("chunkedPrompt") is not None:
            items.append({"id": f"{source_id}-prompt", "role": "user", "content": raw.get("chunkedPrompt"), "created_at": raw.get("timestamp")})
        if raw.get("modelResponse") is not None:
            items.append({"id": f"{source_id}-response", "role": "assistant", "content": raw.get("modelResponse"), "created_at": raw.get("timestamp")})
    for ordinal, message in enumerate(items if isinstance(items, list) else []):
        if not isinstance(message, dict):
            continue
        content = _text(message.get("text") or message.get("content")).strip()
        if not content:
            continue
        result.append({
            "source_id": str(message.get("id") or f"{source_id}-{ordinal}"),
            "parent_source_id": None,
            "ordinal": ordinal,
            "role": str(message.get("role") or message.get("sender") or "unknown"),
            "content": content,
            "created_at": _timestamp(message.get("created_at") or message.get("create_time")),
        })
    return result


def import_json(content, filename="export.json"):
    initialize()
    raw_bytes = content if isinstance(content, bytes) else str(content).encode("utf-8")
    data = json.loads(raw_bytes.decode("utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("conversations") or data.get("data") or [data]
    if not isinstance(data, list):
        raise ValueError("Expected a conversation array or an object containing conversations")
    platform = _platform(data, filename)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    with _connect() as db:
        existing = db.execute("SELECT * FROM imports WHERE sha256=? ORDER BY created_at DESC LIMIT 1", (digest,)).fetchone()
        if existing:
            rows = db.execute("SELECT * FROM conversations WHERE import_id=? ORDER BY COALESCE(updated_at,created_at) DESC", (existing["id"],)).fetchall()
            conversations = [{"id": row["id"], "source_id": row["source_id"], "title": row["title"],
                              "snippet": row["snippet"], "created_at": row["created_at"] or "—",
                              "depth": row["message_count"], "platform": row["platform"], "import_id": row["import_id"]}
                             for row in rows]
            return {"import_id": existing["id"], "platform": existing["platform"],
                    "message_count": existing["message_count"], "conversations": conversations,
                    "duplicate": True, "duplicate_reason": "The exact source file was already imported."}
    import_id = uuid.uuid4().hex
    normalized = []
    message_total = 0
    added_count = 0
    updated_count = 0
    unchanged_count = 0
    with _connect() as db:
        db.execute("INSERT INTO imports VALUES(?,?,?,?,?,?,?)", (
            import_id, Path(filename).name, platform, digest,
            0, 0, _now(),
        ))
        for index, raw in enumerate(data):
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("id") or raw.get("uuid") or raw.get("conversation_id") or f"conversation-{index + 1}")
            title = str(raw.get("title") or raw.get("name") or raw.get("subject") or f"Conversation {index + 1}")
            messages = _messages(raw, source_id)
            raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
            existing_conversation = db.execute(
                "SELECT * FROM conversations WHERE source_id=? AND platform=? ORDER BY COALESCE(updated_at,created_at) DESC LIMIT 1",
                (source_id, platform),
            ).fetchone()
            if existing_conversation and json.dumps(json.loads(existing_conversation["raw_json"]), ensure_ascii=False, sort_keys=True) == raw_json:
                unchanged_count += 1
                normalized.append({"id": existing_conversation["id"], "source_id": source_id,
                                   "title": existing_conversation["title"], "snippet": existing_conversation["snippet"],
                                   "created_at": existing_conversation["created_at"] or "—",
                                   "depth": existing_conversation["message_count"], "platform": platform,
                                   "import_id": existing_conversation["import_id"], "change": "unchanged"})
                message_total += existing_conversation["message_count"]
                continue
            conversation_id = existing_conversation["id"] if existing_conversation else uuid.uuid4().hex
            first_user = next((m["content"] for m in messages if m["role"].lower() in {"user", "human", "customer"}), "")
            snippet = " ".join(first_user.split())[:240]
            created_at = _timestamp(raw.get("create_time") or raw.get("created_at"))
            updated_at = _timestamp(raw.get("update_time") or raw.get("updated_at"))
            if existing_conversation:
                db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
                db.execute("DELETE FROM archive_search WHERE conversation_id=?", (conversation_id,))
                db.execute("""UPDATE conversations SET import_id=?,title=?,snippet=?,created_at=?,updated_at=?,
                              message_count=?,raw_json=? WHERE id=?""",
                           (import_id, title, snippet, created_at, updated_at, len(messages), raw_json, conversation_id))
                updated_count += 1
                change = "updated"
            else:
                db.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    conversation_id, import_id, source_id, platform, title, snippet,
                    created_at, updated_at, len(messages), raw_json,
                ))
                added_count += 1
                change = "added"
            for message in messages:
                db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)", (
                    uuid.uuid4().hex, conversation_id, message["source_id"], message["parent_source_id"],
                    message["ordinal"], message["role"], message["content"], message["created_at"],
                ))
                db.execute("INSERT INTO archive_search VALUES(?,?,?)", (conversation_id, title, message["content"]))
            message_total += len(messages)
            normalized.append({"id": conversation_id, "source_id": source_id, "title": title,
                               "snippet": snippet, "created_at": created_at or "—", "depth": len(messages),
                               "platform": platform, "import_id": import_id, "change": change})
        db.execute("UPDATE imports SET conversation_count=?,message_count=? WHERE id=?",
                   (len(normalized), message_total, import_id))
    return {"import_id": import_id, "platform": platform, "message_count": message_total,
            "conversations": normalized, "duplicate": False,
            "reconciliation": {"added": added_count, "updated": updated_count, "unchanged": unchanged_count}}


def iter_json_array(path, chunk_size=1024 * 1024):
    """Incrementally decode a top-level or conversations/data-wrapped array."""
    decoder = json.JSONDecoder()
    with Path(path).open("r", encoding="utf-8-sig") as stream:
        buffer = ""
        started = False
        ended = False
        wrapped = False
        while not ended:
            chunk = stream.read(chunk_size)
            if chunk:
                buffer += chunk
            position = 0
            while True:
                while position < len(buffer) and buffer[position].isspace(): position += 1
                if not started:
                    if position >= len(buffer): break
                    if buffer[position] == "[":
                        started = True; position += 1
                    elif buffer[position] == "{":
                        match = re.search(r'"(?:conversations|data)"\s*:\s*\[', buffer[position:])
                        if not match:
                            if chunk: break
                            raise ValueError("Wrapped JSON export does not contain a conversations or data array")
                        position += match.end(); started = True; wrapped = True
                    else:
                        raise ValueError("JSON export must be an array or contain a conversations/data array")
                while position < len(buffer) and (buffer[position].isspace() or buffer[position] == ","): position += 1
                if position < len(buffer) and buffer[position] == "]":
                    ended = True; position += 1; break
                if position >= len(buffer): break
                try:
                    value, end = decoder.raw_decode(buffer, position)
                except json.JSONDecodeError:
                    break
                yield value
                position = end
            buffer = buffer[position:]
            if not chunk:
                if not ended:
                    raise ValueError("JSON archive ended before the top-level array was complete")
                if buffer.strip() and not wrapped:
                    raise ValueError("Unexpected data follows the JSON conversation array")
                break


def import_json_path(path, filename="export.json"):
    """Normalize a provider export incrementally from disk."""
    source_path = Path(path)
    digest_builder = hashlib.sha256()
    with source_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest_builder.update(chunk)
    digest = digest_builder.hexdigest()
    initialize()
    with _connect() as db:
        existing = db.execute("SELECT * FROM imports WHERE sha256=? ORDER BY created_at DESC LIMIT 1", (digest,)).fetchone()
        if existing:
            rows = db.execute("SELECT * FROM conversations WHERE import_id=? ORDER BY COALESCE(updated_at,created_at) DESC", (existing["id"],)).fetchall()
            return {"import_id": existing["id"], "platform": existing["platform"], "message_count": existing["message_count"],
                    "conversations": [{"id":r["id"],"source_id":r["source_id"],"title":r["title"],"snippet":r["snippet"],
                    "created_at":r["created_at"] or "—","depth":r["message_count"],"platform":r["platform"],"import_id":r["import_id"]} for r in rows],
                    "duplicate": True, "duplicate_reason": "The exact source file was already imported."}
    iterator = iter_json_array(source_path)
    try:
        first = next(iterator)
    except StopIteration:
        raise ValueError("The JSON archive contains no conversations")
    platform = _platform([first], filename)
    import_id = uuid.uuid4().hex
    normalized=[]; message_total=0; added=updated=unchanged=0
    with _connect() as db:
        db.execute("INSERT INTO imports VALUES(?,?,?,?,?,?,?)", (import_id, Path(filename).name, platform, digest, 0, 0, _now()))
        for index, raw in enumerate(itertools.chain([first], iterator)):
            if not isinstance(raw, dict): continue
            source_id=str(raw.get("id") or raw.get("uuid") or raw.get("conversation_id") or f"conversation-{index+1}")
            title=str(raw.get("title") or raw.get("name") or raw.get("subject") or f"Conversation {index+1}")
            messages=_messages(raw, source_id); raw_json=json.dumps(raw,ensure_ascii=False,sort_keys=True)
            prior=db.execute("SELECT * FROM conversations WHERE source_id=? AND platform=? ORDER BY COALESCE(updated_at,created_at) DESC LIMIT 1",(source_id,platform)).fetchone()
            if prior and json.dumps(json.loads(prior["raw_json"]),ensure_ascii=False,sort_keys=True)==raw_json:
                unchanged+=1; message_total+=prior["message_count"]
                normalized.append({"id":prior["id"],"source_id":source_id,"title":prior["title"],"snippet":prior["snippet"],"created_at":prior["created_at"] or "—","depth":prior["message_count"],"platform":platform,"import_id":prior["import_id"],"change":"unchanged"}); continue
            conversation_id=prior["id"] if prior else uuid.uuid4().hex
            snippet=" ".join(next((m["content"] for m in messages if m["role"].lower() in {"user","human","customer"}),"").split())[:240]
            created_at=_timestamp(raw.get("create_time") or raw.get("created_at")); updated_at=_timestamp(raw.get("update_time") or raw.get("updated_at"))
            if prior:
                db.execute("DELETE FROM messages WHERE conversation_id=?",(conversation_id,)); db.execute("DELETE FROM archive_search WHERE conversation_id=?",(conversation_id,))
                db.execute("UPDATE conversations SET import_id=?,title=?,snippet=?,created_at=?,updated_at=?,message_count=?,raw_json=? WHERE id=?",(import_id,title,snippet,created_at,updated_at,len(messages),raw_json,conversation_id)); updated+=1; change="updated"
            else:
                db.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?)",(conversation_id,import_id,source_id,platform,title,snippet,created_at,updated_at,len(messages),raw_json)); added+=1; change="added"
            for message in messages:
                message_id=uuid.uuid4().hex; db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)",(message_id,conversation_id,message["source_id"],message["parent_source_id"],message["ordinal"],message["role"],message["content"],message["created_at"]))
                db.execute("INSERT INTO archive_search VALUES(?,?,?)",(conversation_id,title,message["content"]))
            message_total+=len(messages); normalized.append({"id":conversation_id,"source_id":source_id,"title":title,"snippet":snippet,"created_at":created_at or "—","depth":len(messages),"platform":platform,"import_id":import_id,"change":change})
        db.execute("UPDATE imports SET conversation_count=?,message_count=? WHERE id=?",(len(normalized),message_total,import_id))
    return {"import_id":import_id,"platform":platform,"message_count":message_total,"conversations":normalized,"duplicate":False,"reconciliation":{"added":added,"updated":updated,"unchanged":unchanged}}


def import_text(text, title="Pasted conversation", filename="pasted-conversation.txt"):
    content = str(text or "").strip()
    if not content:
        raise ValueError("Conversation text is required")
    messages = []
    current_role = "user"
    buffer = []
    role_names = {"user": "user", "human": "user", "you": "user", "assistant": "assistant",
                  "chatgpt": "assistant", "claude": "assistant", "gemini": "assistant", "system": "system"}
    for line in content.splitlines():
        stripped = line.strip()
        label, separator, remainder = stripped.partition(":")
        mapped = role_names.get(label.lower()) if separator else None
        if mapped:
            if buffer:
                messages.append({"role": current_role, "content": "\n".join(buffer).strip()})
            current_role, buffer = mapped, [remainder.strip()]
        else:
            buffer.append(line)
    if buffer:
        messages.append({"role": current_role, "content": "\n".join(buffer).strip()})
    messages = [message for message in messages if message["content"]]
    if not messages:
        messages = [{"role": "user", "content": content}]
    payload = [{"id": uuid.uuid4().hex, "title": str(title or "Pasted conversation"),
                "created_at": _now(), "messages": messages}]
    return import_json(json.dumps(payload, ensure_ascii=False), filename)


def _search_filter(query):
    """Return (sql_where, params) shared by list and count so they always agree.

    The query is tokenised into quoted FTS terms, so punctuation such as
    "C++", "what?" or a bare AND cannot raise an FTS syntax error. Titles are
    matched too, so conversations without messages stay findable.
    """
    text = (query or "").strip()
    if not text:
        return "1=1", ()
    tokens = re.findall(r"\w+", text, re.UNICODE)
    like = f"%{text}%"
    if not tokens:
        return "c.title LIKE ?", (like,)
    fts = " ".join(f'"{token}"' for token in tokens)
    return ("(c.id IN (SELECT conversation_id FROM archive_search WHERE archive_search MATCH ?) OR c.title LIKE ?)",
            (fts, like))


def list_conversations(query="", limit=500, offset=0):
    initialize()
    limit = max(1, min(int(limit), 2000))
    where, params = _search_filter(query)
    with _connect() as db:
        rows = db.execute(f"SELECT c.* FROM conversations c WHERE {where} "
                          "ORDER BY COALESCE(c.updated_at,c.created_at) DESC LIMIT ? OFFSET ?",
                          (*params, limit, offset)).fetchall()
    return [{"id": row["id"], "source_id": row["source_id"], "title": row["title"],
             "snippet": row["snippet"], "created_at": row["created_at"] or "—",
             "depth": row["message_count"], "platform": row["platform"], "import_id": row["import_id"]}
            for row in rows]


def count_conversations(query=""):
    initialize()
    where, params = _search_filter(query)
    with _connect() as db:
        return db.execute(f"SELECT COUNT(*) FROM conversations c WHERE {where}", params).fetchone()[0]


def get_conversation(conversation_id):
    initialize()
    with _connect() as db:
        conversation = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not conversation:
            return None
        messages = db.execute("SELECT id,source_id,role,content,created_at,ordinal FROM messages WHERE conversation_id=? ORDER BY ordinal", (conversation_id,)).fetchall()
    return {"conversation": dict(conversation), "messages": [dict(row) for row in messages]}


def raw_conversations(conversation_ids):
    initialize()
    if not conversation_ids:
        return []
    placeholders = ",".join("?" for _ in conversation_ids)
    with _connect() as db:
        rows = db.execute(f"SELECT raw_json FROM conversations WHERE id IN ({placeholders})", tuple(conversation_ids)).fetchall()
    return [json.loads(row["raw_json"]) for row in rows]


def preserve_source(import_id, filename, media_type, content, coverage):
    initialize()
    payload = bytes(content)
    with _connect() as db:
        digest = hashlib.sha256(payload).hexdigest()
        if db.execute("SELECT 1 FROM source_files WHERE import_id=? AND sha256=?", (import_id, digest)).fetchone():
            return
        db.execute("INSERT INTO source_files(id,import_id,filename,media_type,sha256,byte_count,content,coverage_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (
            uuid.uuid4().hex, import_id, Path(filename).name, media_type,
            digest, len(payload), payload,
            json.dumps(coverage, ensure_ascii=False), _now(),
        ))


def preserve_source_path(import_id, filename, media_type, staged_path, coverage):
    initialize()
    source = Path(staged_path)
    digest_builder = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest_builder.update(chunk)
    digest = digest_builder.hexdigest()
    managed_dir = ROOT / "data" / "sources"
    managed_dir.mkdir(parents=True, exist_ok=True)
    destination = managed_dir / f"{digest}{Path(filename).suffix.lower()}"
    if not destination.exists(): shutil.copyfile(source, destination)
    with _connect() as db:
        if db.execute("SELECT 1 FROM source_files WHERE import_id=? AND sha256=?", (import_id, digest)).fetchone(): return
        db.execute("INSERT INTO source_files(id,import_id,filename,media_type,sha256,byte_count,content,coverage_json,created_at,source_path) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (uuid.uuid4().hex, import_id, Path(filename).name, media_type, digest, source.stat().st_size, b"",
                    json.dumps(coverage,ensure_ascii=False), _now(), str(destination)))


def find_source_import(content):
    initialize()
    digest = hashlib.sha256(bytes(content)).hexdigest()
    with _connect() as db:
        source = db.execute("SELECT * FROM source_files WHERE sha256=? ORDER BY created_at DESC LIMIT 1", (digest,)).fetchone()
        if not source:
            return None
        imported = db.execute("SELECT * FROM imports WHERE id=?", (source["import_id"],)).fetchone()
        rows = db.execute("SELECT * FROM conversations WHERE import_id=? ORDER BY COALESCE(updated_at,created_at) DESC", (source["import_id"],)).fetchall()
    conversations = [{"id": row["id"], "source_id": row["source_id"], "title": row["title"],
                      "snippet": row["snippet"], "created_at": row["created_at"] or "—",
                      "depth": row["message_count"], "platform": row["platform"], "import_id": row["import_id"]}
                     for row in rows]
    return {"import_id": imported["id"], "platform": imported["platform"],
            "message_count": imported["message_count"], "conversations": conversations,
            "coverage": json.loads(source["coverage_json"]), "duplicate": True,
            "duplicate_reason": "The exact source file was already imported."}


def list_imports(limit=50):
    initialize()
    with _connect() as db:
        rows = db.execute("""SELECT i.*,s.media_type,s.byte_count,s.coverage_json
          FROM imports i LEFT JOIN source_files s ON s.import_id=i.id
          ORDER BY i.created_at DESC LIMIT ?""", (max(1, min(int(limit), 200)),)).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["coverage"] = json.loads(item.pop("coverage_json") or "null")
        results.append(item)
    return results


def create_import_job(filename):
    initialize()
    job_id = uuid.uuid4().hex
    now = _now()
    with _connect() as db:
        db.execute("INSERT INTO import_jobs VALUES(?,?,?,?,?,?,?,?,?)",
                   (job_id, Path(filename).name, "queued", "received", 5, None, None, now, now))
    return job_id


def update_import_job(job_id, status=None, stage=None, progress=None, error=None, result=None):
    fields, values = [], []
    for column, value in (("status", status), ("stage", stage), ("progress", progress), ("error", error)):
        if value is not None:
            fields.append(column + "=?"); values.append(value)
    if result is not None:
        fields.append("result_json=?"); values.append(json.dumps(result, ensure_ascii=False))
    fields.append("updated_at=?"); values.append(_now())
    values.append(job_id)
    with _connect() as db:
        db.execute("UPDATE import_jobs SET " + ",".join(fields) + " WHERE id=?", values)


def get_import_job(job_id):
    initialize()
    with _connect() as db:
        row = db.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
    return item


def list_import_jobs(limit=25):
    initialize()
    with _connect() as db:
        rows = db.execute("SELECT * FROM import_jobs ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 100)),)).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
        results.append(item)
    return results


_CANDIDATE_PATTERNS = [
    ("decision", re.compile(r"\b(?:we decided|decision:|we will use|we chose|i decided)\s+(.{12,400})", re.I)),
    ("requirement", re.compile(r"\b(?:must|needs? to|required to|requirement:)\s+(.{12,400})", re.I)),
    ("constraint", re.compile(r"\b(?:must not|cannot|never|constraint:)\s+(.{12,400})", re.I)),
    ("task", re.compile(r"\b(?:next step|todo|need to|have to)\s+(.{12,400})", re.I)),
    ("idea", re.compile(r"\b(?:i want to|we should|let's|idea:|what if we|could build)\s+(.{12,400})", re.I)),
    ("question", re.compile(r"\b(?:open question|we need to figure out|should we)\s+(.{12,400})", re.I)),
    ("abandoned", re.compile(r"\b(?:abandon|dropped|no longer|decided against|not pursuing)\s+(.{12,400})", re.I)),
]


def analyze_conversation(conversation_id):
    initialize()
    with _connect() as db:
        conversation = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not conversation: raise ValueError("Conversation not found")
        messages = db.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY ordinal", (conversation_id,)).fetchall()
        existing = db.execute("SELECT COUNT(*) FROM idea_candidates WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        if existing:
            db.execute("""INSERT OR REPLACE INTO conversation_analysis
              (conversation_id,method,status,candidate_count,analyzed_at) VALUES(?,?,?,?,?)""",
              (conversation_id,"evidence_rules_v1","mapped",existing,_now()))
            return {"created":0,"existing":existing,"abstained":False,"method":"evidence_rules_v1"}
        created=0; seen=set()
        for message in messages:
            if message["role"].lower() not in {"user","human","customer"}: continue
            for kind, pattern in _CANDIDATE_PATTERNS:
                for match in pattern.finditer(message["content"]):
                    interpretation = re.split(r"[\n.!?](?:\s|$)", match.group(1).strip(), maxsplit=1)[0].strip()
                    key = re.sub(r"\W+"," ",interpretation.lower()).strip()
                    if len(key)<12 or key in seen: continue
                    seen.add(key); words=interpretation.split(); title=" ".join(words[:12])+("…" if len(words)>12 else "")
                    confidence=min(.9,.58+min(len(interpretation),180)/1800+(.08 if kind in {"decision","constraint","requirement"} else 0))
                    db.execute("INSERT INTO idea_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                        uuid.uuid4().hex,conversation_id,message["id"],kind,title,interpretation,match.group(0)[:700],round(confidence,2),
                        f"Direct {kind} language found in a user-authored source message. Human confirmation required.",
                        "evidence_rules_v1","pending",None,_now()))
                    created+=1
        db.execute("""INSERT OR REPLACE INTO conversation_analysis
          (conversation_id,method,status,candidate_count,analyzed_at) VALUES(?,?,?,?,?)""",
          (conversation_id,"evidence_rules_v1","mapped" if created else "no_explicit_evidence",created,_now()))
        return {"created":created,"existing":0,"abstained":created==0,"method":"evidence_rules_v1"}


def create_analysis_job():
    initialize(); job_id=uuid.uuid4().hex; now=_now()
    with _connect() as db:
        total=db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        db.execute("INSERT INTO analysis_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
          (job_id,"queued",total,0,0,0,0,None,now,now))
    return get_analysis_job(job_id)


def get_analysis_job(job_id):
    initialize()
    with _connect() as db:
        row=db.execute("SELECT * FROM analysis_jobs WHERE id=?",(job_id,)).fetchone()
    return dict(row) if row else None


def archive_analysis_overview():
    initialize()
    with _connect() as db:
        total=db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        mapped=db.execute("SELECT COUNT(*) FROM conversation_analysis").fetchone()[0]
        with_evidence=db.execute("SELECT COUNT(*) FROM conversation_analysis WHERE candidate_count>0").fetchone()[0]
        no_evidence=db.execute("SELECT COUNT(*) FROM conversation_analysis WHERE status='no_explicit_evidence'").fetchone()[0]
        pending=db.execute("SELECT COUNT(*) FROM idea_candidates WHERE status='pending'").fetchone()[0]
    return {"total":total,"mapped":mapped,"unmapped":max(total-mapped,0),"with_evidence":with_evidence,
            "no_explicit_evidence":no_evidence,"pending_candidates":pending,"method":"evidence_rules_v1"}


def source_coverage():
    """Return the providers actually represented in the archive.

    Coverage is deliberately data-driven: new/custom providers appear without a
    frontend release, and unidentified records remain visible for correction.
    """
    initialize()
    with _connect() as db:
        rows=db.execute("""SELECT LOWER(COALESCE(NULLIF(TRIM(c.platform),''),'unknown')) provider,
          COUNT(DISTINCT c.import_id) imports, COUNT(*) conversations,
          COALESCE(SUM(c.message_count),0) messages,
          SUM(CASE WHEN c.message_count=0 THEN 1 ELSE 0 END) unreadable,
          SUM(CASE WHEN a.conversation_id IS NOT NULL THEN 1 ELSE 0 END) analyzed,
          MAX(COALESCE(c.updated_at,c.created_at,i.created_at)) last_activity
          FROM conversations c LEFT JOIN imports i ON i.id=c.import_id
          LEFT JOIN conversation_analysis a ON a.conversation_id=c.id
          GROUP BY LOWER(COALESCE(NULLIF(TRIM(c.platform),''),'unknown'))
          ORDER BY conversations DESC,provider""").fetchall()
        pending={row[0]:row[1] for row in db.execute("""SELECT LOWER(COALESCE(NULLIF(TRIM(v.platform),''),'unknown')),COUNT(*)
          FROM idea_candidates k JOIN conversations v ON v.id=k.conversation_id WHERE k.status='pending' GROUP BY 1""")}
    result=[dict(row) for row in rows]
    for item in result: item["pending"]=pending.get(item["provider"],0)
    return result


def run_archive_analysis(job_id):
    with _connect() as db:
        ids=[row[0] for row in db.execute("SELECT id FROM conversations ORDER BY COALESCE(updated_at,created_at),id")]
        db.execute("UPDATE analysis_jobs SET status='running',total=?,updated_at=? WHERE id=?",(len(ids),_now(),job_id))
    created=existing=abstained=processed=0
    try:
        for conversation_id in ids:
            result=analyze_conversation(conversation_id)
            processed+=1; created+=result["created"]; existing+=result["existing"]
            abstained+=1 if result["abstained"] else 0
            with _connect() as db:
                db.execute("""UPDATE analysis_jobs SET processed=?,candidates_created=?,existing_candidates=?,
                  abstained=?,updated_at=? WHERE id=?""",(processed,created,existing,abstained,_now(),job_id))
        generate_candidate_links()
        with _connect() as db:
            db.execute("UPDATE analysis_jobs SET status='complete',updated_at=? WHERE id=?",(_now(),job_id))
    except Exception as exc:
        with _connect() as db:
            db.execute("UPDATE analysis_jobs SET status='failed',error=?,updated_at=? WHERE id=?",(str(exc),_now(),job_id))
        raise
    return get_analysis_job(job_id)


_LINK_STOPWORDS = {
    "about","after","again","also","and","are","because","been","before","being","build","could",
    "does","from","have","into","just","more","must","need","only","other","should","that","their",
    "them","then","there","these","they","this","through","using","want","what","when","where","which",
    "will","with","would","your","idea","make","work","user","users","system","platform"
}


def _link_terms(text):
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]{3,}", (text or "").lower())
            if token not in _LINK_STOPWORDS and not token.isdigit()}


MAX_LINKS_PER_CANDIDATE = 8


def bounded_term_pairs(term_sets, conversation_ids, min_shared=2, max_per_item=MAX_LINKS_PER_CANDIDATE):
    """Yield (i, j, shared_terms) for likely-related candidates without all-pairs work.

    An inverted index finds only candidates that share terms; for terms common to a
    large share of the archive only a bounded window of nearby postings is
    inspected (so work stays linear without discarding the signal); and each candidate keeps at most
    ``max_per_item`` links, so stored links grow linearly with candidates.
    """
    count = len(term_sets)
    postings = {}
    for index, terms in enumerate(term_sets):
        for term in terms:
            postings.setdefault(term, []).append(index)
    document_frequency_cap = max(50, int(count * 0.02))
    common_window = 200
    degree = [0] * count
    for i, left_terms in enumerate(term_sets):
        if len(left_terms) < min_shared or degree[i] >= max_per_item:
            continue
        overlap = {}
        for term in left_terms:
            posting = postings.get(term, ())
            if len(posting) > document_frequency_cap:
                # Very common term: inspect only the next ``common_window`` postings
                # so work stays linear, without discarding the signal entirely.
                start = bisect.bisect_right(posting, i)
                neighbours = posting[start:start + common_window]
            else:
                neighbours = (j for j in posting if j > i)
            for j in neighbours:
                overlap[j] = overlap.get(j, 0) + 1
        scored = []
        for j, hits in overlap.items():
            if hits < min_shared or conversation_ids[i] == conversation_ids[j]:
                continue
            shared = left_terms & term_sets[j]
            if len(shared) >= min_shared:
                scored.append((len(shared) / len(left_terms | term_sets[j]), -j, j, shared))
        scored.sort(reverse=True)
        for _, _, j, shared in scored:
            if degree[i] >= max_per_item:
                break
            if degree[j] >= max_per_item:
                continue
            degree[i] += 1; degree[j] += 1
            yield i, j, shared


def generate_candidate_links(min_score=.18, min_shared=2):
    """Propose lexical overlap across conversations; never asserts semantic equivalence."""
    initialize(); created=0
    with _connect() as db:
        rows=db.execute("""SELECT c.*,v.title conversation_title FROM idea_candidates c
          JOIN conversations v ON v.id=c.conversation_id WHERE c.status!='rejected' ORDER BY c.created_at,c.id""").fetchall()
        prepared=[(row,_link_terms(row["title"]+" "+row["interpretation"])) for row in rows]
        term_sets=[terms for _,terms in prepared]; conversation_ids=[row["conversation_id"] for row,_ in prepared]
        for left_index,right_index,shared_set in bounded_term_pairs(term_sets,conversation_ids,min_shared):
            left,left_terms=prepared[left_index]; right,right_terms=prepared[right_index]
            if True:
                shared=sorted(shared_set)
                score=len(shared)/len(left_terms | right_terms)
                if score<min_score: continue
                kinds={left["kind"],right["kind"]}
                if "abandoned" in kinds:
                    relation_type="possible_abandonment"
                    rationale="One source explicitly uses abandonment language and both candidates share specific terms. Review whether it actually closes or abandons the related work."
                elif "decision" in kinds and kinds & {"idea","requirement","constraint"}:
                    relation_type="possible_decision_link"
                    rationale="A decision candidate and related work share specific source terms. Review whether the decision governs that work."
                elif "task" in kinds and "idea" in kinds:
                    relation_type="possible_next_step"
                    rationale="An idea and task candidate share specific source terms. Review whether the task advances that idea."
                elif kinds & {"constraint","requirement"} and kinds & {"idea","task"}:
                    relation_type="possible_boundary"
                    rationale="A requirement or constraint shares specific source terms with related work. Review whether it defines a real boundary for that work."
                else:
                    relation_type="possible_overlap"
                    rationale="These candidates share specific source-language terms across different conversations. Lexical overlap does not prove they are the same idea."
                left_id,right_id=sorted((left["id"],right["id"]))
                cursor=db.execute("""INSERT OR IGNORE INTO candidate_links VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
                    uuid.uuid4().hex,left_id,right_id,relation_type,json.dumps(shared),round(score,3),rationale,
                    "lexical_overlap_v1","pending",None,_now()))
                created += cursor.rowcount
    return {"created":created,"method":"lexical_overlap_v1"}


def list_candidate_links(status="pending", limit=250):
    initialize()
    with _connect() as db:
        rows=db.execute("""SELECT l.*,a.title left_title,a.interpretation left_interpretation,
          av.title left_conversation,b.title right_title,b.interpretation right_interpretation,
          bv.title right_conversation FROM candidate_links l
          JOIN idea_candidates a ON a.id=l.left_candidate_id JOIN conversations av ON av.id=a.conversation_id
          JOIN idea_candidates b ON b.id=l.right_candidate_id JOIN conversations bv ON bv.id=b.conversation_id
          WHERE l.status=? ORDER BY l.score DESC,l.created_at DESC LIMIT ?""",
          (status,max(1,min(int(limit),1000)))).fetchall()
    result=[]
    for row in rows:
        item=dict(row); item["shared_terms"]=json.loads(item.pop("shared_terms_json")); result.append(item)
    return result


def review_candidate_link(link_id, action):
    if action not in {"accept","reject","defer"}: raise ValueError("Review action must be accept, reject, or defer")
    initialize(); new_status={"accept":"accepted","reject":"rejected","defer":"deferred"}[action]
    with _connect() as db:
        row=db.execute("SELECT * FROM candidate_links WHERE id=? AND status='pending'",(link_id,)).fetchone()
        if not row: raise ValueError("Pending relationship suggestion not found")
        db.execute("UPDATE candidate_links SET status=?,reviewed_at=? WHERE id=?",(new_status,_now(),link_id))
    return dict(row) | {"status":new_status}


def list_candidates(status="pending", limit=250, offset=0):
    initialize()
    with _connect() as db:
        rows=db.execute("""SELECT c.*,v.title conversation_title,v.platform,m.ordinal message_ordinal
          FROM idea_candidates c JOIN conversations v ON v.id=c.conversation_id
          JOIN messages m ON m.id=c.message_id WHERE c.status=? ORDER BY c.created_at DESC,c.id LIMIT ? OFFSET ?""",
          (status,max(1,min(int(limit),1000)),max(0,int(offset)))).fetchall()
    return [dict(row) for row in rows]


def count_candidates(status="pending"):
    initialize()
    with _connect() as db:
        return db.execute("SELECT COUNT(*) FROM idea_candidates WHERE status=?",(status,)).fetchone()[0]


def review_candidate(candidate_id, action):
    if action not in {"accept","reject","defer"}: raise ValueError("Review action must be accept, reject, or defer")
    initialize()
    with _connect() as db:
        row=db.execute("""SELECT c.*,v.title conversation_title,v.platform,m.source_id message_source_id
          FROM idea_candidates c JOIN conversations v ON v.id=c.conversation_id
          JOIN messages m ON m.id=c.message_id WHERE c.id=? AND c.status='pending'""",(candidate_id,)).fetchone()
        if not row: raise ValueError("Pending candidate not found")
        status={"accept":"accepted","reject":"rejected","defer":"deferred"}[action]
        db.execute("UPDATE idea_candidates SET status=?,reviewed_at=? WHERE id=?",(status,_now(),candidate_id))
    return dict(row) | {"status":status}


initialize()


def export_local_backup_archive():
    """Build a read-only, consistent ZIP snapshot of the local archive.

    Uses SQLite's online backup API, so it is safe while the server is running.
    Stored model credentials are removed from the snapshot: a backup must never
    carry secrets. Returns the path of a temporary ZIP the caller must delete.
    """
    import hashlib, tempfile, zipfile
    initialize()
    work = Path(tempfile.mkdtemp(prefix="seed-backup-"))
    snapshot = work / "archive.db"
    try:
        source = sqlite3.connect(DB_PATH, timeout=30); target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
            tables = {row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "model_credentials" in tables:
                target.execute("DELETE FROM model_credentials")
            target.commit(); target.execute("VACUUM")
        finally:
            target.close(); source.close()
        digest = hashlib.sha256(); size = 0
        with snapshot.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk); size += len(chunk)
        manifest = {"format": "seedreflections-local-snapshot-v1", "created_at": _now(),
                    "database": "archive.db", "sha256": digest.hexdigest(), "byte_count": size,
                    "credentials_included": False}
        fd, archive_name = tempfile.mkstemp(prefix="seed-backup-", suffix=".zip"); os.close(fd)
        with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as package:
            package.write(snapshot, "archive.db")
            package.writestr("manifest.json", json.dumps(manifest, indent=2))
        return Path(archive_name)
    finally:
        shutil.rmtree(work, ignore_errors=True)



# ── Verified local restore ────────────────────────────────────────────────────
RESTORE_PRESERVED_TABLES = ("model_credentials", "api_integrations", "runtime_users", "runtime_workspaces",
                            "runtime_memberships", "runtime_sessions", "runtime_invitations", "runtime_auth_attempts")
RESTORE_COUNT_TABLES = (("conversations", "Conversations"), ("messages", "Messages"), ("imports", "Imports"),
                        ("source_files", "Preserved source files"), ("idea_candidates", "Candidates"),
                        ("workspace_seeds", "Accepted ideas"), ("workspace_decisions", "Decisions"),
                        ("workspace_projects", "Projects"), ("workspace_artifacts", "Work artifacts"))
RESTORE_STAGING_SECONDS = 30 * 60


class RestoreError(ValueError):
    """A restore was refused or rolled back; the message is safe to show the user."""


def _table_counts(path):
    connection = sqlite3.connect(path)
    try:
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {label: (connection.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0] if table in existing else 0)
                for table, label in RESTORE_COUNT_TABLES}
    finally:
        connection.close()


def _restore_staging_dir():
    directory = DB_PATH.parent / "restore-staging"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _purge_stale_staging():
    cutoff = datetime.now().timestamp() - RESTORE_STAGING_SECONDS
    for item in _restore_staging_dir().glob("*.db"):
        if item.stat().st_mtime < cutoff:
            item.unlink(missing_ok=True)


def preview_local_restore(zip_path):
    """Verify a local backup ZIP completely, stage it, and describe what a restore would replace.

    Nothing live is modified. Raises RestoreError for anything unverifiable.
    """
    import hashlib, secrets, zipfile
    initialize(); _purge_stale_staging()
    try:
        package = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise RestoreError("File is not a SeedReflections backup ZIP") from exc
    with package:
        names = set(package.namelist())
        if names != {"archive.db", "manifest.json"}:
            raise RestoreError("Not a SeedReflections local backup (unexpected contents). Hosted backups restore only through a hosted workspace.")
        try:
            manifest = json.loads(package.read("manifest.json"))
        except ValueError as exc:
            raise RestoreError("Backup manifest is unreadable") from exc
        if manifest.get("format") != "seedreflections-local-snapshot-v1" or not manifest.get("sha256"):
            raise RestoreError("Unsupported or incomplete backup manifest")
        declared = int(manifest.get("byte_count") or 0)
        if package.getinfo("archive.db").file_size != declared:
            raise RestoreError("Backup size does not match its manifest")
        token = secrets.token_hex(16); staged = _restore_staging_dir() / f"{token}.db"
        digest = hashlib.sha256(); written = 0
        try:
            with package.open("archive.db") as source, staged.open("wb") as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    written += len(chunk)
                    if written > declared:
                        raise RestoreError("Backup contains more data than its manifest declares")
                    digest.update(chunk); target.write(chunk)
            if digest.hexdigest() != manifest["sha256"]:
                raise RestoreError("Backup checksum verification failed; the file is corrupt or has been modified")
            check = sqlite3.connect(staged)
            try:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RestoreError("Backup database failed its integrity check")
                tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                check.close()
            if not {"conversations", "messages", "imports"} <= tables:
                raise RestoreError("Backup database is missing core archive tables")
            incoming = _table_counts(staged)
        except Exception:
            staged.unlink(missing_ok=True)
            raise
    return {"token": token, "created_at": manifest.get("created_at"), "backup": incoming,
            "current": _table_counts(DB_PATH), "preserved": list(RESTORE_PRESERVED_TABLES),
            "expires_in_seconds": RESTORE_STAGING_SECONDS,
            "notice": "Everything in your archive and work history will be replaced by this backup. A safety snapshot is taken first and the restore is rolled back automatically if anything fails. Model keys, integration tokens and account sessions are kept as they are now."}


def _read_rows(path, tables):
    saved = {}
    connection = sqlite3.connect(path)
    try:
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            if table in existing:
                cursor = connection.execute(f"SELECT * FROM [{table}]")
                saved[table] = ([column[0] for column in cursor.description], cursor.fetchall())
    finally:
        connection.close()
    return saved


def _write_rows(path, saved):
    connection = sqlite3.connect(path, timeout=30)
    try:
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, (columns, rows) in saved.items():
            if table not in existing:
                continue
            connection.execute(f"DELETE FROM [{table}]")
            names = ",".join(f"[{c}]" for c in columns)
            connection.executemany(f"INSERT INTO [{table}]({names}) VALUES({','.join('?' * len(columns))})", rows)
        connection.commit()
    finally:
        connection.close()


def _copy_database(source_path, destination_path):
    source = sqlite3.connect(source_path); destination = sqlite3.connect(destination_path, timeout=60)
    try:
        source.backup(destination)
    finally:
        destination.close(); source.close()


def apply_local_restore(token):
    """Replace the local archive with a previously previewed, verified backup.

    Takes a safety snapshot first, preserves live credentials/tokens/identity, and rolls
    back to the snapshot if anything fails or the result does not match the backup.
    """
    import zipfile, tempfile
    initialize()
    if not re.fullmatch(r"[0-9a-f]{32}", str(token or "")):
        raise RestoreError("Restore token is invalid")
    staged = _restore_staging_dir() / f"{token}.db"
    if not staged.exists() or staged.stat().st_mtime < datetime.now().timestamp() - RESTORE_STAGING_SECONDS:
        staged.unlink(missing_ok=True)
        raise RestoreError("Restore preview expired or was not found; upload the backup again")
    with _connect() as db:
        running = db.execute("SELECT (SELECT COUNT(*) FROM import_jobs WHERE status IN ('queued','running')) + "
                             "(SELECT COUNT(*) FROM analysis_jobs WHERE status IN ('queued','running'))").fetchone()[0]
    if running:
        raise RestoreError("An import or analysis is still running. Wait for it to finish, then restore.")
    expected = _table_counts(staged)
    snapshot_dir = DB_PATH.parent / "safety-snapshots"; snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_zip = export_local_backup_archive()
    snapshot = snapshot_dir / f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    shutil.move(str(snapshot_zip), str(snapshot))
    preserved = _read_rows(DB_PATH, RESTORE_PRESERVED_TABLES)
    try:
        _copy_database(staged, DB_PATH)
        _write_rows(DB_PATH, preserved)
        check = sqlite3.connect(DB_PATH)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RestoreError("Restored database failed its integrity check")
        finally:
            check.close()
        if _table_counts(DB_PATH) != expected:
            raise RestoreError("Restored data does not match the backup")
        initialize()
    except Exception as exc:
        try:
            work = Path(tempfile.mkdtemp(prefix="seed-rollback-"))
            try:
                with zipfile.ZipFile(snapshot) as package:
                    package.extract("archive.db", work)
                _copy_database(work / "archive.db", DB_PATH)
                _write_rows(DB_PATH, preserved)
            finally:
                shutil.rmtree(work, ignore_errors=True)
        except Exception as rollback_error:
            raise RestoreError(f"Restore failed AND automatic rollback failed ({rollback_error}). "
                               f"Your pre-restore snapshot is at {snapshot}") from exc
        raise RestoreError(f"Restore failed and your previous archive was put back: {exc}") from exc
    finally:
        staged.unlink(missing_ok=True)
    return {"status": "restored", "restored": expected, "safety_snapshot": str(snapshot)}
