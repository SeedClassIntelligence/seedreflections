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
