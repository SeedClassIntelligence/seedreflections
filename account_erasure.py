"""Permanent erasure of a hosted workspace's data, and of a hosted account.

Erasure works from the data itself: every table in the data stores that carries a
`workspace_id` is cleared for that workspace, so a table added later is covered without
editing this file. Stored provider keys, agent tokens, work sessions and uploaded source
files are removed too. Nothing here is available for the local workspace, whose data
lives on the person's own device.
"""
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import agent_tokens
import archive_store
import secret_store
import tenant_archive_store
import work_sessions

_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Sign-in and membership tables are removed by auth_store.delete_account, not here.
_AUTH_PREFIX = "runtime_"


def _databases():
    seen, result = set(), []
    for module in (archive_store, tenant_archive_store, secret_store, agent_tokens, work_sessions):
        path = Path(getattr(module, "DB_PATH"))
        if path not in seen:
            seen.add(path); result.append(path)
    return result


def erase_workspace_data(workspace_id):
    """Delete everything stored for one hosted workspace. Safe to run again after a failure."""
    if workspace_id == "local" or not _ID.match(str(workspace_id or "")):
        raise ValueError("Only a hosted workspace can be erased")
    removed = {}
    for path in _databases():
        if not path.exists():
            continue
        with closing(sqlite3.connect(path, timeout=30)) as db:
            tables = [row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            if "model_credentials" in tables:
                for (provider,) in db.execute("SELECT provider FROM model_credentials WHERE workspace_id=?", (workspace_id,)).fetchall():
                    try: secret_store.delete_credential(workspace_id, provider)   # also clears any OS-keyring copy
                    except Exception: pass
            with db:
                for table in tables:
                    if table.startswith(_AUTH_PREFIX):
                        continue
                    if "workspace_id" in [col[1] for col in db.execute(f'PRAGMA table_info("{table}")')]:
                        count = db.execute(f'DELETE FROM "{table}" WHERE workspace_id=?', (workspace_id,)).rowcount
                        if count:
                            removed[table] = removed.get(table, 0) + count
    sources = Path(tenant_archive_store.DB_PATH).parent / "tenant_sources" / workspace_id
    if sources.is_dir():
        shutil.rmtree(sources, ignore_errors=False)
        removed["source_files_folder"] = 1
    return removed
