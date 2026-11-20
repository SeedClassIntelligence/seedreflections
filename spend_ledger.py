"""Durable record of estimated AI spend, kept in the archive database so it survives restarts, is included in backups,
and covers the whole calendar month (UTC).

Each row is one model call: when, provider, model, caller, token counts, estimated cost, and who pays ("platform" for
managed calls, "own_key" for calls made with a person's own key). No prompt or answer text and no account identity is
stored. Costs are estimates from per-model rates; the provider's own bill is the authority."""
import sqlite3
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
    return db


def month_key(when=None):
    return (when or _now()).strftime("%Y-%m")


def record(provider, model, prompt_tokens, completion_tokens, cost_usd, billed="platform", caller="", when=None):
    when = when or _now()
    with closing(_connect()) as db, db:
        db.execute("INSERT INTO ai_spend(created_at,month,provider,model,caller,prompt_tokens,completion_tokens,cost_usd,billed) VALUES(?,?,?,?,?,?,?,?,?)",
                   (when.isoformat(), month_key(when), str(provider or ""), str(model or ""), str(caller or ""), int(prompt_tokens or 0),
                    int(completion_tokens or 0), float(cost_usd or 0.0), "platform" if billed == "platform" else "own_key"))


def month_total(billed="platform", month=None):
    """Estimated spend for one calendar month (UTC). Raises if the ledger cannot be read; callers decide how to fail."""
    with closing(_connect()) as db:
        row = db.execute("SELECT COALESCE(SUM(cost_usd),0), COUNT(*), COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0) "
                         "FROM ai_spend WHERE month=? AND billed=?", (month or month_key(), billed)).fetchone()
    return {"cost_usd": float(row[0]), "requests": int(row[1]), "prompt_tokens": int(row[2]), "completion_tokens": int(row[3])}


# ---- spend that could not be written ----------------------------------------------------------------------------
# If a platform-paid call cannot be written to the ledger, its cost is held in a small file next to the database (a
# different file, so a damaged or locked database does not prevent it) and, as a last resort, in memory. While anything
# is held, the budget check stops platform-paid calls. Each check first tries to move held spend into the ledger; once
# that works the hold is gone and the cost counts toward the month like any other.
import json
import os

_MEMORY_HELD = []


def _held_path():
    return archive_store.DB_PATH.parent / "ai_spend_unrecorded.json"


def _read_held():
    path = _held_path()
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
        return items if isinstance(items, list) else [{"cost_usd": 0.0, "note": "unreadable hold file"}]
    except (OSError, ValueError):
        return [{"cost_usd": 0.0, "note": "unreadable hold file"}]      # still a hold: never treated as "nothing owed"


def hold(provider, model, prompt_tokens, completion_tokens, cost_usd, billed, caller, when=None):
    item = {"created_at": (when or _now()).isoformat(), "provider": str(provider or ""), "model": str(model or ""), "caller": str(caller or ""),
            "prompt_tokens": int(prompt_tokens or 0), "completion_tokens": int(completion_tokens or 0), "cost_usd": float(cost_usd or 0.0),
            "billed": "platform" if billed == "platform" else "own_key"}
    try:
        path = _held_path(); path.parent.mkdir(parents=True, exist_ok=True)
        items = _read_held() + [item]
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(items), encoding="utf-8"); os.replace(temp, path)
    except OSError:
        _MEMORY_HELD.append(item)                                       # last resort: lost on restart, so the file is preferred


def has_unrecorded():
    return bool(_MEMORY_HELD) or _held_path().exists()


def flush_held():
    """Try to write held spend into the ledger. Returns True when nothing is held any more."""
    items = _read_held() + list(_MEMORY_HELD)
    if not items:
        return True
    try:
        for item in items:
            if item.get("note"):
                return False                                            # a damaged hold file needs a person to look at it
            when = datetime.fromisoformat(item["created_at"])
            record(item["provider"], item["model"], item["prompt_tokens"], item["completion_tokens"], item["cost_usd"], item["billed"], item["caller"], when=when)
    except Exception:
        return False
    _MEMORY_HELD.clear()
    try:
        _held_path().unlink()
    except FileNotFoundError:
        pass
    return True
