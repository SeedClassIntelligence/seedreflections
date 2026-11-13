"""Read-only Google Drive source: sign in with Google, choose a folder, review, import, re-sync.

Google's own consent screen does the sign-in; SeedReflections never sees the Google password.
It asks for read-only Drive access and an email address, keeps the refresh token encrypted in
the secret store (provider name "tool:google_drive"), and only reads the folder the person chose
after they reviewed the list. Disconnecting revokes the token at Google and removes this
workspace's Drive records; imported conversations and documents stay in the archive.
Every table here carries workspace_id, so account deletion clears it too.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

import archive_store
import secret_store

CREDENTIAL = "tool:google_drive"
SCOPES = "openid email https://www.googleapis.com/auth/drive.readonly"
ENDPOINTS = {  # fixed Google addresses; replaced only by tests running in the same process
    "auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token",
    "revoke": "https://oauth2.googleapis.com/revoke", "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
    "drive": "https://www.googleapis.com/drive/v3"}
MAX_FILES = 500
MAX_DEPTH = 3
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_SYNC_SECONDS = 90
STATE_MINUTES = 10
FOLDER = "application/vnd.google-apps.folder"
EXPORTS = {"application/vnd.google-apps.document": ("text/plain", ".txt"),
           "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
           "application/vnd.google-apps.presentation": ("text/plain", ".txt")}
DOWNLOADS = {"application/pdf": ".pdf", "text/plain": ".txt", "text/markdown": ".md", "text/csv": ".csv", "text/html": ".html",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"}
_ID = re.compile(r"^(root|[A-Za-z0-9_-]{5,120})$")


class DriveError(ValueError):
    """A reason, safe to show the person. Never contains a token or secret."""


def _now(): return datetime.now(timezone.utc).replace(microsecond=0)
def _iso(moment): return moment.isoformat()


def client():
    return (os.environ.get("SEED_REFLECTIONS_GOOGLE_CLIENT_ID", "").strip(), os.environ.get("SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET", "").strip())


def configured():
    return all(client())


def initialize():
    archive_store.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(archive_store.DB_PATH, timeout=30)) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS google_drive_states(state TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, verifier TEXT NOT NULL,
          created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_drive_connections(workspace_id TEXT PRIMARY KEY, account_email TEXT, status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_drive_previews(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, folder_id TEXT NOT NULL,
          folder_name TEXT NOT NULL, manifest_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_drive_sources(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, folder_id TEXT NOT NULL,
          folder_name TEXT NOT NULL, status TEXT NOT NULL, last_sync_at TEXT, last_error TEXT, created_at TEXT NOT NULL,
          UNIQUE(workspace_id, folder_id));
        CREATE TABLE IF NOT EXISTS google_drive_files(source_id TEXT NOT NULL, workspace_id TEXT NOT NULL, file_id TEXT NOT NULL,
          name TEXT NOT NULL, fingerprint TEXT NOT NULL, synced_at TEXT NOT NULL, PRIMARY KEY(source_id, file_id));""")


def _db():
    initialize()
    db = sqlite3.connect(archive_store.DB_PATH, timeout=30); db.row_factory = sqlite3.Row
    return db


# ---- talking to Google ------------------------------------------------------------------------------------------
def _call(method, url, *, form=None, token=None, accept_json=True, limit=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = {"User-Agent": "SeedReflections-Drive/1.0"}
    if token: headers["Authorization"] = "Bearer " + token
    if form is not None: headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=25) as response:
            body = response.read(limit + 1) if limit else response.read()
            if limit and len(body) > limit: raise DriveError("A file is too large to import (the limit is 25 MB).")
            return json.loads(body) if accept_json else body
    except urllib.error.HTTPError as exc:
        detail = {}
        try: detail = json.loads(exc.read() or b"{}")
        except Exception: pass
        code = detail.get("error") if isinstance(detail.get("error"), str) else ""
        if code == "invalid_grant": raise DriveError("Google access was removed or expired. Connect Google Drive again.") from None
        if exc.code in (401, 403): raise DriveError("Google refused the request. Check that Drive access is still allowed, then connect again.") from None
        if exc.code == 404: raise DriveError("That Drive item no longer exists.") from None
        raise DriveError(f"Google Drive answered with an error ({exc.code}).") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise DriveError("Google Drive could not be reached. Try again shortly.") from None


# ---- sign-in -------------------------------------------------------------------------------------------------------
def begin_authorization(workspace_id, redirect_uri):
    client_id, _ = client()
    if not client_id: raise DriveError("Google Drive has not been set up for this deployment.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    now = _now()
    with closing(_db()) as db, db:
        db.execute("DELETE FROM google_drive_states WHERE expires_at<?", (_iso(now),))
        db.execute("INSERT INTO google_drive_states VALUES(?,?,?,?,?)", (state, workspace_id, verifier, _iso(now), _iso(now + timedelta(minutes=STATE_MINUTES))))
    query = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPES,
                                    "access_type": "offline", "prompt": "consent", "include_granted_scopes": "false", "state": state,
                                    "code_challenge": challenge, "code_challenge_method": "S256"})
    return ENDPOINTS["auth"] + "?" + query


def _store(workspace_id, blob, deployment_mode):
    value = json.dumps(blob)
    try:
        secret_store.set_credential(workspace_id, CREDENTIAL, value, deployment_mode)
    except RuntimeError:
        if deployment_mode != "local": raise
        secret_store.set_credential(workspace_id, CREDENTIAL, value, deployment_mode, temporary=True)   # no keychain: lasts until restart


def complete_authorization(state, code, redirect_uri, deployment_mode):
    """Finish the Google redirect. The one-time `state` ties the browser back to the workspace that started it."""
    if not state or not code: raise DriveError("Google did not return an authorization code.")
    with closing(_db()) as db, db:
        row = db.execute("SELECT * FROM google_drive_states WHERE state=? AND expires_at>=?", (str(state), _iso(_now()))).fetchone()
        db.execute("DELETE FROM google_drive_states WHERE state=?", (str(state),))          # single use, even on failure
    if not row: raise DriveError("This sign-in link expired or was already used. Start again from Tools.")
    client_id, secret = client()
    token = _call("POST", ENDPOINTS["token"], form={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                  "client_id": client_id, "client_secret": secret, "code_verifier": row["verifier"]})
    if "https://www.googleapis.com/auth/drive.readonly" not in str(token.get("scope", "")): raise DriveError("Drive read access was not granted.")
    if not token.get("refresh_token"): raise DriveError("Google did not allow ongoing access. Remove SeedReflections from your Google account's connected apps and try again.")
    email = None
    try: email = _call("GET", ENDPOINTS["userinfo"], token=token["access_token"]).get("email")
    except DriveError: pass
    blob = {"access_token": token["access_token"], "refresh_token": token["refresh_token"], "scope": token.get("scope"),
            "expires_at": time.time() + int(token.get("expires_in") or 3000), "email": email}
    _store(row["workspace_id"], blob, deployment_mode)
    now = _iso(_now())
    with closing(_db()) as db, db:
        db.execute("""INSERT INTO google_drive_connections VALUES(?,?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET
                      account_email=excluded.account_email,status='connected',updated_at=excluded.updated_at""", (row["workspace_id"], email, "connected", now, now))
    return {"workspace_id": row["workspace_id"], "email": email}


def _access_token(workspace_id, deployment_mode):
    raw = secret_store.get_credential(workspace_id, CREDENTIAL)
    if not raw: raise DriveError("Google Drive is not connected.")
    blob = json.loads(raw)
    if blob.get("expires_at", 0) - time.time() > 60: return blob["access_token"]
    client_id, secret = client()
    try:
        fresh = _call("POST", ENDPOINTS["token"], form={"grant_type": "refresh_token", "refresh_token": blob["refresh_token"], "client_id": client_id, "client_secret": secret})
    except DriveError:
        _forget(workspace_id); raise                                                       # revoked at Google: stop pretending to be connected
    blob.update({"access_token": fresh["access_token"], "expires_at": time.time() + int(fresh.get("expires_in") or 3000)})
    _store(workspace_id, blob, deployment_mode)
    return blob["access_token"]


def _forget(workspace_id):
    secret_store.delete_credential(workspace_id, CREDENTIAL)
    with closing(_db()) as db, db:
        db.execute("UPDATE google_drive_connections SET status='disconnected',updated_at=? WHERE workspace_id=?", (_iso(_now()), workspace_id))


def status(workspace_id):
    with closing(_db()) as db:
        conn = db.execute("SELECT * FROM google_drive_connections WHERE workspace_id=?", (workspace_id,)).fetchone()
        sources = [dict(r) for r in db.execute("SELECT id,folder_id,folder_name,status,last_sync_at,last_error FROM google_drive_sources WHERE workspace_id=? ORDER BY created_at", (workspace_id,))]
    connected = bool(conn and conn["status"] == "connected" and secret_store.credential_status(workspace_id, CREDENTIAL).get("credential_configured"))
    return {"configured": configured(), "connected": connected, "account": conn["account_email"] if conn else None, "sources": sources}


def disconnect(workspace_id):
    """Revoke at Google (best effort), forget the token, remove this workspace's Drive records. Imported items stay."""
    raw = secret_store.get_credential(workspace_id, CREDENTIAL)
    if raw:
        try: _call("POST", ENDPOINTS["revoke"], form={"token": json.loads(raw).get("refresh_token", "")}, accept_json=False)
        except DriveError: pass
    secret_store.delete_credential(workspace_id, CREDENTIAL)
    with closing(_db()) as db, db:
        for table in ("google_drive_connections", "google_drive_previews", "google_drive_files", "google_drive_sources", "google_drive_states"):
            db.execute(f"DELETE FROM {table} WHERE workspace_id=?", (workspace_id,))


# ---- browsing and importing ----------------------------------------------------------------------------------------
def _check_id(value):
    if not _ID.match(str(value or "")): raise DriveError("That Drive folder is not valid.")
    return str(value)


def _list(token, parent):
    out, page = [], None
    while len(out) < MAX_FILES + 50:
        query = {"q": f"'{parent}' in parents and trashed=false", "pageSize": "100", "orderBy": "name",
                 "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,version,md5Checksum)"}
        if page: query["pageToken"] = page
        reply = _call("GET", ENDPOINTS["drive"] + "/files?" + urllib.parse.urlencode(query), token=token)
        out += reply.get("files", [])
        page = reply.get("nextPageToken")
        if not page: break
    return out


def list_folders(workspace_id, parent, deployment_mode):
    token = _access_token(workspace_id, deployment_mode); parent = _check_id(parent or "root")
    items = _list(token, parent)
    return {"parent": parent, "folders": [{"id": i["id"], "name": i["name"]} for i in items if i.get("mimeType") == FOLDER]}


def _walk(token, folder_id, prefix="", depth=0, found=None, skipped=None):
    found = [] if found is None else found; skipped = {"unsupported": 0, "too_large": 0, "over_limit": 0} if skipped is None else skipped
    for item in _list(token, folder_id):
        mime = item.get("mimeType")
        if mime == FOLDER:
            if depth < MAX_DEPTH: _walk(token, item["id"], prefix + item["name"] + "/", depth + 1, found, skipped)
            continue
        if mime not in EXPORTS and mime not in DOWNLOADS: skipped["unsupported"] += 1; continue
        if int(item.get("size") or 0) > MAX_FILE_BYTES: skipped["too_large"] += 1; continue
        if len(found) >= MAX_FILES: skipped["over_limit"] += 1; continue
        found.append({"id": item["id"], "name": item["name"], "path": prefix + item["name"], "mime": mime, "bytes": int(item.get("size") or 0),
                      "modified": item.get("modifiedTime"), "fingerprint": f"{item.get('version')}:{item.get('md5Checksum') or item.get('modifiedTime')}"})
    return found, skipped


def preview(workspace_id, folder_id, folder_name, deployment_mode):
    token = _access_token(workspace_id, deployment_mode); folder_id = _check_id(folder_id)
    files, skipped = _walk(token, folder_id)
    manifest = {"files": files, "skipped": skipped, "folder_name": str(folder_name or "Drive folder")[:200]}
    preview_id, now = uuid.uuid4().hex, _now()
    with closing(_db()) as db, db:
        db.execute("DELETE FROM google_drive_previews WHERE expires_at<?", (_iso(now),))
        db.execute("INSERT INTO google_drive_previews VALUES(?,?,?,?,?,?,?)", (preview_id, workspace_id, folder_id, manifest["folder_name"], json.dumps(manifest), _iso(now), _iso(now + timedelta(minutes=30))))
    return {"preview_id": preview_id, "folder_id": folder_id, **manifest, "expires_in_seconds": 1800}


def _filename(name, extension):
    stem = re.sub(r"[^\w\- .()]+", "_", name).strip(" .")[:80] or "file"
    stem = re.sub(r"\.(pdf|txt|md|csv|html|docx|xlsx)$", "", stem, flags=re.I)
    return "drive-" + stem + extension


def _fetch(token, entry):
    if entry["mime"] in EXPORTS:
        kind, extension = EXPORTS[entry["mime"]]
        content = _call("GET", f"{ENDPOINTS['drive']}/files/{urllib.parse.quote(entry['id'], safe='')}/export?" + urllib.parse.urlencode({"mimeType": kind}), token=token, accept_json=False, limit=MAX_FILE_BYTES)
    else:
        extension = DOWNLOADS[entry["mime"]]
        content = _call("GET", f"{ENDPOINTS['drive']}/files/{urllib.parse.quote(entry['id'], safe='')}?alt=media", token=token, accept_json=False, limit=MAX_FILE_BYTES)
    if extension in (".txt", ".md"):   # keep where it came from inside the text itself
        content = f"Source: Google Drive: {entry['path']}\nModified: {entry.get('modified')}\n\n".encode() + content
    return _filename(entry["name"], extension), content


def sync(workspace_id, source_id, importer, deployment_mode):
    """Import new and changed files of a connected folder. `importer(filename, bytes)` runs the normal document import."""
    with closing(_db()) as db:
        source = db.execute("SELECT * FROM google_drive_sources WHERE id=? AND workspace_id=?", (source_id, workspace_id)).fetchone()
        if not source: raise DriveError("That Drive source was not found.")
        known = {r["file_id"]: r["fingerprint"] for r in db.execute("SELECT file_id,fingerprint FROM google_drive_files WHERE source_id=?", (source_id,))}
    token = _access_token(workspace_id, deployment_mode)
    files, skipped = _walk(token, source["folder_id"])
    started = time.monotonic(); imported = unchanged = failed = 0; errors = []; partial = False
    for entry in files:
        if known.get(entry["id"]) == entry["fingerprint"]: unchanged += 1; continue
        if time.monotonic() - started > MAX_SYNC_SECONDS: partial = True; break
        try:
            token = _access_token(workspace_id, deployment_mode)
            filename, content = _fetch(token, entry)
            importer(filename, content)
            with closing(_db()) as db, db:
                db.execute("INSERT OR REPLACE INTO google_drive_files VALUES(?,?,?,?,?,?)", (source_id, workspace_id, entry["id"], entry["name"], entry["fingerprint"], _iso(_now())))
            imported += 1
        except (DriveError, ValueError) as exc:
            failed += 1
            if len(errors) < 10: errors.append({"file": entry["path"], "error": str(exc)})
    state = "attention" if failed else ("partial" if partial else "synced")
    with closing(_db()) as db, db:
        db.execute("UPDATE google_drive_sources SET status=?,last_sync_at=?,last_error=? WHERE id=?", (state, _iso(_now()), errors[0]["error"] if errors else None, source_id))
    return {"source_id": source_id, "status": state, "files_seen": len(files), "files_imported": imported, "files_unchanged": unchanged,
            "files_failed": failed, "skipped": skipped, "errors": errors}


def connect_preview(workspace_id, preview_id, consent, importer, deployment_mode):
    if consent is not True: raise DriveError("Confirm that SeedReflections may read the listed files before importing.")
    with closing(_db()) as db:
        row = db.execute("SELECT * FROM google_drive_previews WHERE id=? AND workspace_id=? AND expires_at>=?", (str(preview_id), workspace_id, _iso(_now()))).fetchone()
    if not row: raise DriveError("The review expired. Choose the folder again.")
    source_id = uuid.uuid4().hex
    with closing(_db()) as db, db:
        existing = db.execute("SELECT id FROM google_drive_sources WHERE workspace_id=? AND folder_id=?", (workspace_id, row["folder_id"])).fetchone()
        if existing: source_id = existing["id"]
        else: db.execute("INSERT INTO google_drive_sources VALUES(?,?,?,?,?,?,?,?)", (source_id, workspace_id, row["folder_id"], row["folder_name"], "connected", None, None, _iso(_now())))
        db.execute("DELETE FROM google_drive_previews WHERE id=?", (row["id"],))
    return sync(workspace_id, source_id, importer, deployment_mode)
