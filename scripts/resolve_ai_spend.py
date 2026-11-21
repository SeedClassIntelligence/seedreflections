#!/usr/bin/env python3
"""Resolve AI calls whose cost was never confirmed, so platform-paid AI calls can resume.

A platform-paid AI call is written to the spending ledger as "pending" before it is sent and settled with its real cost
afterwards. If the server stopped (or could not write) in between, the call stays pending and paid AI calls are paused.
This counts each such call at its reserved cost (an upper estimate, so the budget is never understated) and lets paid
calls resume. Calls younger than 15 minutes are left alone, because they may still be running in the server; if a late
answer arrives for a resolved call, its real cost replaces the estimate. Check the AI provider's own usage page first if you want the exact figure.

    python scripts/resolve_ai_spend.py            # list pending calls
    python scripts/resolve_ai_spend.py --resolve  # resolve them

Run it where the server's data folder is (in the container: docker compose -f docker-compose.prod.yml exec seed-reflections python scripts/resolve_ai_spend.py)."""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import archive_store  # noqa: E402
import spend_ledger   # noqa: E402

spend_ledger.flush_held()
with closing(sqlite3.connect(archive_store.DB_PATH)) as db:
    rows = db.execute("SELECT created_at, provider, model, caller, cost_usd FROM ai_spend WHERE status='pending' ORDER BY created_at").fetchall()
if not rows:
    print("Nothing pending. Paid AI calls are not blocked by unrecorded spend."); sys.exit(0)
for created_at, provider, model, caller, cost in rows:
    print(f"{created_at}  {provider}:{model}  {caller}  reserved ${cost:.4f}")
if "--resolve" in sys.argv:
    resolved = spend_ledger.resolve_unsettled()
    print(f"Resolved {resolved} call(s) at their reserved cost.")
    if resolved < len(rows):
        print("Calls younger than 15 minutes were left pending; they may still be running. Run this again later.")
else:
    print("Run again with --resolve to count these at their reserved cost and resume paid AI calls.")
