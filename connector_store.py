"""User-authorized local AI-work connectors with incremental synchronization."""
from __future__ import annotations

import hashlib, json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path

from archive_store import DB_PATH, import_json
from document_ingest import import_document_path

ARCHIVE_SUFFIXES={".json",".jsonl"}
DOCUMENT_SUFFIXES={".pdf",".docx",".xlsx",".xlsm",".html",".htm",".rtf",".txt",".md",".csv",".tsv",".log",".xml",".zip"}
SUPPORTED_SUFFIXES=ARCHIVE_SUFFIXES | DOCUMENT_SUFFIXES
ADAPTER_OPERATIONS=("discover","authorize","enumerate","preview","import","sync","reconcile","disconnect","health")
PROVIDERS={
    "claude_code":{"name":"Claude Code","paths":[Path.home()/".claude"/"projects"]},
    "claude_cowork":{"name":"Claude Cowork","paths":[Path(os.environ.get("APPDATA",""))/"Claude",Path(os.environ.get("LOCALAPPDATA",""))/"AnthropicClaude"]},
    "cursor":{"name":"Cursor","paths":[Path(os.environ.get("APPDATA",""))/"Cursor"/"User"/"workspaceStorage"]},
    "folder":{"name":"AI or work folder","paths":[]},
}

def _now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(DB_PATH,timeout=30); db.row_factory=sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL"); return db

def initialize():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS source_connectors(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, provider TEXT NOT NULL,
          root_path TEXT NOT NULL, auto_sync INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL, last_sync_at TEXT, last_error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(workspace_id,provider,root_path));
        CREATE TABLE IF NOT EXISTS source_connector_files(
          connector_id TEXT NOT NULL, relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
          byte_count INTEGER NOT NULL, modified_ns INTEGER NOT NULL, synced_at TEXT NOT NULL,
          PRIMARY KEY(connector_id,relative_path));
        CREATE TABLE IF NOT EXISTS source_connector_previews(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, provider TEXT NOT NULL,
          root_path TEXT NOT NULL, manifest_json TEXT NOT NULL,
          created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
        """)
        columns={row[1] for row in db.execute("PRAGMA table_info(source_connectors)")}
        if "scope_json" not in columns: db.execute("ALTER TABLE source_connectors ADD COLUMN scope_json TEXT NOT NULL DEFAULT '{\"mode\":\"all\",\"paths\":[]}'")

def adapter_catalog():
    return [{"provider":provider,"name":definition["name"],"transport":"local_filesystem",
        "operations":list(ADAPTER_OPERATIONS),"formats":[suffix.lstrip(".") for suffix in sorted(SUPPORTED_SUFFIXES)],"read_only":True,
        "canonical_contract_version":"1.0","availability":"operational"} for provider,definition in PROVIDERS.items()]

def discover():
    found=[]
    for provider,definition in PROVIDERS.items():
        if provider=="folder": continue
        paths=[]
        for candidate in definition["paths"]:
            try:
                if str(candidate) not in {".",""} and candidate.is_dir(): paths.append(str(candidate.resolve()))
            except OSError: pass
        found.append({"provider":provider,"name":definition["name"],"detected":bool(paths),"paths":paths})
    return found

def list_connectors(workspace_id="local"):
    initialize()
    with _connect() as db: rows=db.execute("SELECT * FROM source_connectors WHERE workspace_id=? ORDER BY created_at",(workspace_id,)).fetchall()
    result=[]
    for row in rows:
        item={**dict(row),"auto_sync":bool(row["auto_sync"])}
        item["scope"]=json.loads(item.pop("scope_json") or '{"mode":"all","paths":[]}')
        result.append(item)
    return result

def add_connector(provider,root_path,auto_sync=True,workspace_id="local",scope=None):
    initialize()
    if provider not in PROVIDERS: raise ValueError("Unsupported connector provider")
    root=Path(str(root_path or "")).expanduser().resolve()
    if not root.is_dir(): raise ValueError("The selected source folder does not exist")
    if root==Path(root.anchor) or root==Path.home().resolve(): raise ValueError("Choose the specific AI application data folder, not an entire drive or home folder")
    connector_id=uuid.uuid4().hex; now=_now(); scope=scope or {"mode":"all","paths":[]}; encoded_scope=json.dumps(scope,sort_keys=True)
    with _connect() as db:
        prior=db.execute("SELECT id FROM source_connectors WHERE workspace_id=? AND provider=? AND root_path=?",(workspace_id,provider,str(root))).fetchone()
        if prior: connector_id=prior["id"]; db.execute("UPDATE source_connectors SET auto_sync=?,scope_json=?,status='connected',last_error=NULL,updated_at=? WHERE id=?",(int(bool(auto_sync)),encoded_scope,now,connector_id))
        else: db.execute("""INSERT INTO source_connectors
          (id,workspace_id,provider,root_path,auto_sync,status,last_sync_at,last_error,created_at,updated_at,scope_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(connector_id,workspace_id,provider,str(root),int(bool(auto_sync)),"connected",None,None,now,now,encoded_scope))
    return next(item for item in list_connectors(workspace_id) if item["id"]==connector_id)

def remove_connector(connector_id,workspace_id="local"):
    initialize()
    with _connect() as db:
        changed=db.execute("DELETE FROM source_connectors WHERE id=? AND workspace_id=?",(connector_id,workspace_id)).rowcount
        db.execute("DELETE FROM source_connector_files WHERE connector_id=?",(connector_id,))
    if not changed: raise KeyError("Connector not found")
    return {"status":"disconnected"}

def _text(value):
    if isinstance(value,str): return value
    if isinstance(value,list): return "\n".join(filter(None,(_text(item.get("text") if isinstance(item,dict) else item) for item in value)))
    if isinstance(value,dict): return _text(value.get("content") or value.get("text") or "")
    return ""

def _jsonl_conversation(path,root,provider):
    messages=[]; session_id=None; title=None; cwd=None
    with path.open("r",encoding="utf-8-sig",errors="replace") as stream:
        for line_number,line in enumerate(stream):
            line=line.strip()
            if not line: continue
            try: record=json.loads(line)
            except json.JSONDecodeError: continue
            if not isinstance(record,dict): continue
            session_id=session_id or record.get("sessionId") or record.get("session_id")
            cwd=cwd or record.get("cwd")
            message=record.get("message") if isinstance(record.get("message"),dict) else record
            role=message.get("role") or record.get("type") or "unknown"
            if role in {"human"}: role="user"
            if role not in {"user","assistant","system","tool"}: continue
            content=_text(message.get("content") or record.get("content"))
            if not content.strip(): continue
            messages.append({"id":record.get("uuid") or record.get("id") or f"line-{line_number+1}","parent_id":record.get("parentUuid") or record.get("parent_id"),
                "role":role,"content":content,"created_at":record.get("timestamp") or record.get("created_at")})
            if not title and role=="user": title=" ".join(content.split())[:100]
    if not messages: return None
    relative=path.relative_to(root).as_posix()
    return {"id":str(session_id or f"{provider}:{relative}"),"title":title or path.stem,"source_platform":provider,
        "source_path":relative,"project_path":cwd,"messages":messages,"updated_at":datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()}

def _candidate_files(root):
    files=[]
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(path)
            if len(files)>=10000: break
    return files

def preview_source(provider,root_path,workspace_id="local"):
    if provider not in PROVIDERS: raise ValueError("Unsupported connector provider")
    root=Path(str(root_path or "")).expanduser().resolve()
    if not root.is_dir(): raise ValueError("The selected source folder does not exist")
    if root==Path(root.anchor) or root==Path.home().resolve(): raise ValueError("Choose the specific AI application data folder, not an entire drive or home folder")
    items=[]; total_bytes=0; unreadable=[]
    for path in _candidate_files(root):
        try:
            stat=path.stat(); relative=path.relative_to(root).as_posix(); total_bytes+=stat.st_size
            if stat.st_size>250*1024*1024:
                unreadable.append(relative); continue
            title=path.stem; conversation_count=1; message_count=None
            if path.suffix.lower()==".jsonl":
                conversation=_jsonl_conversation(path,root,provider)
                if not conversation: unreadable.append(relative); continue
                title=conversation["title"]; message_count=len(conversation["messages"])
            elif path.suffix.lower()==".json":
                data=json.loads(path.read_text(encoding="utf-8-sig",errors="replace"))
                records=(data.get("conversations") or data.get("data") or [data]) if isinstance(data,dict) else data
                conversation_count=len(records) if isinstance(records,list) else 0
                if conversation_count==0: unreadable.append(relative); continue
            else:
                conversation_count=1
            items.append({"path":relative,"title":title,"format":path.suffix.lower().lstrip("."),"byte_count":stat.st_size,
                "modified_at":datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(),"conversation_count":conversation_count,
                "message_count":message_count,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
        except Exception: unreadable.append(str(path.relative_to(root)))
    preview_id=uuid.uuid4().hex; created=datetime.now(timezone.utc); expires=created.timestamp()+1800
    manifest={"items":items,"unreadable":unreadable,"total_bytes":total_bytes}
    initialize()
    with _connect() as db:
        db.execute("DELETE FROM source_connector_previews WHERE expires_at<?",(_now(),))
        db.execute("INSERT INTO source_connector_previews VALUES(?,?,?,?,?,?,?)",(preview_id,workspace_id,provider,str(root),json.dumps(manifest),created.replace(microsecond=0).isoformat(),datetime.fromtimestamp(expires,timezone.utc).replace(microsecond=0).isoformat()))
    return {"preview_id":preview_id,"provider":provider,"root_path":str(root),**manifest,"expires_in_seconds":1800}

def connect_preview(preview_id,selected_paths=None,include_new=True,auto_sync=True,workspace_id="local"):
    initialize()
    with _connect() as db: row=db.execute("SELECT * FROM source_connector_previews WHERE id=? AND workspace_id=? AND expires_at>=?",(preview_id,workspace_id,_now())).fetchone()
    if not row: raise KeyError("Source preview expired or was not found")
    manifest=json.loads(row["manifest_json"]); allowed={item["path"] for item in manifest["items"]}; selected=list(dict.fromkeys(selected_paths or []))
    if any(path not in allowed for path in selected): raise ValueError("Selection contains a file that was not in the source preview")
    root=Path(row["root_path"]); authorized=manifest["items"] if include_new else [item for item in manifest["items"] if item["path"] in selected]
    for item in authorized:
        candidate=(root/item["path"]).resolve()
        if root not in candidate.parents or not candidate.is_file(): raise ValueError("A previewed source item is no longer available; review the source again")
        if hashlib.sha256(candidate.read_bytes()).hexdigest()!=item["sha256"]: raise ValueError("Source content changed after preview; review it again before importing")
    scope={"mode":"all" if include_new else "selected","paths":selected}
    connector=add_connector(row["provider"],row["root_path"],auto_sync,workspace_id,scope)
    return {"connector":connector,"sync":sync_connector(connector["id"],workspace_id)}

def sync_connector(connector_id,workspace_id="local"):
    initialize()
    with _connect() as db: row=db.execute("SELECT * FROM source_connectors WHERE id=? AND workspace_id=?",(connector_id,workspace_id)).fetchone()
    if not row: raise KeyError("Connector not found")
    root=Path(row["root_path"]); provider=row["provider"]; scope=json.loads(row["scope_json"] or '{"mode":"all","paths":[]}')
    if not root.is_dir(): raise ValueError("Connected source folder is unavailable")
    scanned=changed=conversations=messages=skipped=0; errors=[]; reconciliation={"added":0,"updated":0,"unchanged":0}
    files=_candidate_files(root)
    if scope.get("mode")=="selected":
        selected=set(scope.get("paths") or []); files=[path for path in files if path.relative_to(root).as_posix() in selected]
    for path in files:
        scanned+=1
        try:
            stat=path.stat()
            if stat.st_size>250*1024*1024: skipped+=1; continue
            relative=path.relative_to(root).as_posix()
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with _connect() as db: prior=db.execute("SELECT sha256 FROM source_connector_files WHERE connector_id=? AND relative_path=?",(connector_id,relative)).fetchone()
            if prior and prior["sha256"]==digest: continue
            if path.suffix.lower()==".jsonl":
                conversation=_jsonl_conversation(path,root,provider)
                if not conversation: skipped+=1; continue
                result=import_json(json.dumps([conversation],ensure_ascii=False),f"{provider}-{path.stem}.json")
            elif path.suffix.lower()==".json":
                result=import_json(path.read_text(encoding="utf-8-sig",errors="replace"),path.name)
            else:
                result=import_document_path(path,path.name)
            changed+=1; conversations+=len(result.get("conversations",[])); messages+=int(result.get("message_count",result.get("messages",0)) or 0)
            for outcome in reconciliation: reconciliation[outcome]+=int(result.get("reconciliation",{}).get(outcome,0) or 0)
            with _connect() as db: db.execute("INSERT OR REPLACE INTO source_connector_files VALUES(?,?,?,?,?,?)",(connector_id,relative,digest,stat.st_size,stat.st_mtime_ns,_now()))
        except Exception as exc:
            skipped+=1
            if len(errors)<20: errors.append({"file":str(path.relative_to(root)),"error":str(exc)})
    now=_now(); status="attention" if errors else "synced"
    with _connect() as db: db.execute("UPDATE source_connectors SET status=?,last_sync_at=?,last_error=?,updated_at=? WHERE id=? AND workspace_id=?",(status,now,json.dumps(errors) if errors else None,now,connector_id,workspace_id))
    return {"connector_id":connector_id,"status":status,"files_scanned":scanned,"files_changed":changed,"files_skipped":skipped,
        "conversations":conversations,"messages":messages,"reconciliation":reconciliation,"errors":errors,"synced_at":now}

def connector_health(connector_id,workspace_id="local"):
    connector=next((item for item in list_connectors(workspace_id) if item["id"]==connector_id),None)
    if not connector: raise KeyError("Connector not found")
    root=Path(connector["root_path"]); available=root.is_dir()
    with _connect() as db:
        tracked=db.execute("SELECT COUNT(*) FROM source_connector_files WHERE connector_id=?",(connector_id,)).fetchone()[0]
    return {"connector_id":connector_id,"healthy":available and connector["status"]!="attention",
        "source_available":available,"status":connector["status"],"last_sync_at":connector["last_sync_at"],
        "tracked_files":tracked,"last_error":connector["last_error"]}

def sync_automatic(workspace_id="local"):
    results=[]
    for item in list_connectors(workspace_id):
        if item["auto_sync"]:
            try: results.append(sync_connector(item["id"],workspace_id))
            except Exception as exc: results.append({"connector_id":item["id"],"status":"error","error":str(exc)})
    return results
