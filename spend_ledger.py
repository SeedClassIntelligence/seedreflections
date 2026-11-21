"""Durable record of estimated AI spend, kept in the archive database so it survives restarts, is included in backups,
and covers the whole calendar month (UTC).

Each row is one model call: when, provider, model, caller, token counts, estimated cost, and who pays ("platform" for
managed calls, "own_key" for calls made with a person's own key). No prompt or answer text and no account identity is
stored. Costs are estimates from per-model rates; the provider's own bill is the authority."""
import json
import os
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone

import archive_store


def _now():
    return datetime.now(timezone.utc)


def _connect():
    archive_store.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(archive_store.DB_PATH, timeout=30)
    db.execute("""CREATE TABLE IF NOT EXISTS ai_spend(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, month TEXT NOT NULL, provider TEXT, model TEXT,
        caller TEXT, prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0, billed TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS ai_spend_month ON ai_spend(month, billed)")
    if "call_id" not in {row[1] for row in db.execute("PRAGMA table_info(ai_spend)")}:
        db.execute("ALTER TABLE ai_spend ADD COLUMN call_id TEXT")
    if "status" not in {row[1] for row in db.execute("PRAGMA table_info(ai_spend)")}:
        # pending: a platform-paid call reserved before it was sent; settled: its real cost is known;
        # resolved: an operator settled a call whose real cost was never learned, at its reserved amount.
        db.execute("ALTER TABLE ai_spend ADD COLUMN status TEXT NOT NULL DEFAULT 'settled'")
    # One row per call: writing the same call again (a retried recovery) changes nothing.
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ai_spend_call ON ai_spend(call_id)")
    return db


def month_key(when=None):
    return (when or _now()).strftime("%Y-%m")


def new_call_id():
    return uuid.uuid4().hex


def record(provider, model, prompt_tokens, completion_tokens, cost_usd, billed="platform", caller="", when=None, call_id=None):
    """Write one call. With a call_id the write is idempotent: a call already in the ledger is not added again."""
    when = when or _now()
    with closing(_connect()) as db, db:
        db.execute("INSERT OR IGNORE INTO ai_spend(created_at,month,provider,model,caller,prompt_tokens,completion_tokens,cost_usd,billed,call_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (when.isoformat(), month_key(when), str(provider or ""), str(model or ""), str(caller or ""), int(prompt_tokens or 0),
                    int(completion_tokens or 0), float(cost_usd or 0.0), "platform" if billed == "platform" else "own_key", call_id))


def reserve(call_id, provider, model, caller, reserved_cost, when=None):
    """Write a pending row for a platform-paid call BEFORE it is sent. Raises if it cannot be written; the caller must
    then not send the call. A pending row counts toward the month at its reserved (upper-estimate) cost."""
    when = when or _now()
    with closing(_connect()) as db, db:
        db.execute("INSERT INTO ai_spend(created_at,month,provider,model,caller,prompt_tokens,completion_tokens,cost_usd,billed,call_id,status) "
                   "VALUES(?,?,?,?,?,0,0,?, 'platform', ?, 'pending')",
                   (when.isoformat(), month_key(when), str(provider or ""), str(model or ""), str(caller or ""), float(reserved_cost or 0.0), call_id))


def settle(call_id, prompt_tokens, completion_tokens, cost_usd, **row):
    """Replace a reservation with the call's real cost. Idempotent. A call an administrator already resolved at its
    estimate is corrected to the real cost when that arrives late, so real usage is never discarded. If no reservation
    exists, insert the call."""
    with closing(_connect()) as db, db:
        changed = db.execute("UPDATE ai_spend SET prompt_tokens=?, completion_tokens=?, cost_usd=?, status='settled' WHERE call_id=? AND status IN ('pending','resolved')",
                             (int(prompt_tokens or 0), int(completion_tokens or 0), float(cost_usd or 0.0), call_id)).rowcount
    if not changed:
        record(row.get("provider"), row.get("model"), prompt_tokens, completion_tokens, cost_usd, row.get("billed", "platform"), row.get("caller", ""),
               when=row.get("when"), call_id=call_id)


def pending_calls():
    with closing(_connect()) as db:
        return [r[0] for r in db.execute("SELECT call_id FROM ai_spend WHERE status='pending'")]


# Longer than any model call can take (the longest provider timeout is 120 seconds), so a pending call this old is not
# still running in the server.
STALE_AFTER_SECONDS = 15 * 60


def resolve_unsettled(in_flight=(), min_age_seconds=STALE_AFTER_SECONDS, now=None):
    """Operator action: count pending calls at their reserved cost so paid calls can resume. Skips calls a running
    request owns, calls younger than min_age_seconds (they may still be in progress in the server, which a separate
    process cannot see), and calls whose settlement is held. Returns how many were resolved."""
    owned = set(in_flight)
    cutoff = (now or _now()).timestamp() - min_age_seconds
    resolved = 0
    with closing(_connect()) as db, db:
        for call_id, created_at in db.execute("SELECT call_id, created_at FROM ai_spend WHERE status='pending'").fetchall():
            if call_id in owned or (_held_dir() / (call_id + ".json")).exists(): continue
            if datetime.fromisoformat(created_at).timestamp() > cutoff: continue
            resolved += db.execute("UPDATE ai_spend SET status='resolved' WHERE call_id=? AND status='pending'", (call_id,)).rowcount
    return resolved


def month_total(billed="platform", month=None):
    """Estimated spend for one calendar month (UTC). Raises if the ledger cannot be read; callers decide how to fail."""
    with closing(_connect()) as db:
        row = db.execute("SELECT COALESCE(SUM(cost_usd),0), COUNT(*), COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0) "
                         "FROM ai_spend WHERE month=? AND billed=?", (month or month_key(), billed)).fetchone()
    return {"cost_usd": float(row[0]), "requests": int(row[1]), "prompt_tokens": int(row[2]), "completion_tokens": int(row[3])}


# ---- spend that could not be written ----------------------------------------------------------------------------
# If a platform-paid call cannot be written to the ledger, its cost is held until it can be. Each held call is its own
# small file, named by its call id, in a folder next to the database (a separate file, so a locked or damaged database
# does not prevent it). One file per call means concurrent holds never read and rewrite a shared file, so none can
# overwrite another. If even that fails, the call is held in memory as a last resort (lost on restart).
# While anything is held, the budget check stops platform-paid calls. Recovery writes each held call to the ledger by
# its call id (idempotent) and only then removes its file, so a failure part-way through, or a retry, never counts a
# call twice and never drops one.

_MEMORY_HELD = {}
_MEMORY_LOCK = threading.Lock()


def _held_dir():
    return archive_store.DB_PATH.parent / "ai_spend_unrecorded"


def hold(provider, model, prompt_tokens, completion_tokens, cost_usd, billed, caller, when=None, call_id=None):
    item = {"call_id": call_id or new_call_id(), "created_at": (when or _now()).isoformat(), "provider": str(provider or ""), "model": str(model or ""),
            "caller": str(caller or ""), "prompt_tokens": int(prompt_tokens or 0), "completion_tokens": int(completion_tokens or 0),
            "cost_usd": float(cost_usd or 0.0), "billed": "platform" if billed == "platform" else "own_key"}
    try:
        folder = _held_dir(); folder.mkdir(parents=True, exist_ok=True)
        target = folder / (item["call_id"] + ".json"); temp = folder / (item["call_id"] + ".tmp")
        temp.write_text(json.dumps(item), encoding="utf-8"); os.replace(temp, target)
    except OSError:
        with _MEMORY_LOCK:
            _MEMORY_HELD[item["call_id"]] = item
    return item["call_id"]


def _held_files():
    folder = _held_dir()
    return sorted(folder.glob("*.json")) if folder.exists() else []


def has_unrecorded():
    with _MEMORY_LOCK:
        if _MEMORY_HELD: return True
    return bool(_held_files())


def flush_held():
    """Write held calls into the ledger, one at a time, each by its call id. Returns True when nothing is held any more."""
    cleared = True
    for path in _held_files():
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            settle(item["call_id"], item["prompt_tokens"], item["completion_tokens"], item["cost_usd"], provider=item["provider"], model=item["model"],
                   billed=item["billed"], caller=item["caller"], when=datetime.fromisoformat(item["created_at"]))
        except FileNotFoundError:
            continue                                                    # another request recorded and removed it
        except Exception:
            cleared = False                                             # unreadable or not writable yet: keep the hold
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            cleared = False                                             # recorded, but the file remains; a retry is harmless
    with _MEMORY_LOCK:
        for call_id, item in list(_MEMORY_HELD.items()):
            try:
                settle(call_id, item["prompt_tokens"], item["completion_tokens"], item["cost_usd"], provider=item["provider"], model=item["model"],
                       billed=item["billed"], caller=item["caller"], when=datetime.fromisoformat(item["created_at"]))
            except Exception:
                cleared = False; continue
            del _MEMORY_HELD[call_id]
    return cleared and not has_unrecorded()
