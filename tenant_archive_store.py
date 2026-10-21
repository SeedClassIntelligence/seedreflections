"""Workspace-scoped archive persistence for hosted Seed Reflections runtimes."""
import base64, hashlib, hmac, itertools, json, mimetypes, re, shutil, sqlite3, tempfile, uuid, zipfile
from contextlib import contextmanager
from pathlib import Path

from archive_store import DB_PATH, _messages, _now, _platform, _timestamp, iter_json_array
from workspace_store import load_workspace, save_workspace, save_workspace_in_transaction


@contextmanager
def _connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tenant_imports(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, filename TEXT NOT NULL,
          platform TEXT NOT NULL, sha256 TEXT NOT NULL, conversation_count INTEGER NOT NULL,
          message_count INTEGER NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(workspace_id,sha256));
        CREATE TABLE IF NOT EXISTS tenant_conversations(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, import_id TEXT NOT NULL,
          source_id TEXT NOT NULL, platform TEXT NOT NULL, title TEXT NOT NULL,
          snippet TEXT NOT NULL, created_at TEXT, updated_at TEXT,
          message_count INTEGER NOT NULL, raw_json TEXT NOT NULL,
          analysis_status TEXT NOT NULL DEFAULT 'not_analyzed',
          UNIQUE(workspace_id,platform,source_id));
        CREATE INDEX IF NOT EXISTS tenant_conversations_workspace
          ON tenant_conversations(workspace_id,updated_at);
        CREATE TABLE IF NOT EXISTS tenant_messages(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
          source_id TEXT, parent_source_id TEXT, ordinal INTEGER NOT NULL,
          role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT);
        CREATE INDEX IF NOT EXISTS tenant_messages_conversation
          ON tenant_messages(workspace_id,conversation_id,ordinal);
        CREATE TABLE IF NOT EXISTS tenant_candidates(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
          message_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
          interpretation TEXT NOT NULL, confidence REAL NOT NULL, rationale TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', reviewed_at TEXT, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS tenant_candidates_review
          ON tenant_candidates(workspace_id,status,created_at);
        CREATE TABLE IF NOT EXISTS tenant_import_jobs(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, filename TEXT NOT NULL,
          status TEXT NOT NULL, stage TEXT NOT NULL, progress INTEGER NOT NULL,
          result_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tenant_analysis_jobs(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, status TEXT NOT NULL,
          total INTEGER NOT NULL, processed INTEGER NOT NULL, candidates_created INTEGER NOT NULL,
          error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tenant_candidate_links(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, left_candidate_id TEXT NOT NULL,
          right_candidate_id TEXT NOT NULL, shared_terms_json TEXT NOT NULL, score REAL NOT NULL,
          status TEXT NOT NULL, created_at TEXT NOT NULL, reviewed_at TEXT);
        CREATE INDEX IF NOT EXISTS tenant_links_review ON tenant_candidate_links(workspace_id,status,created_at);
        CREATE TABLE IF NOT EXISTS tenant_source_files(
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, import_id TEXT NOT NULL,
          filename TEXT NOT NULL, media_type TEXT NOT NULL, sha256 TEXT NOT NULL,
          byte_count INTEGER NOT NULL, source_path TEXT NOT NULL, coverage_json TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(workspace_id,sha256));
        """)


def import_json(workspace_id, content, filename="export.json"):
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
        prior = db.execute("SELECT * FROM tenant_imports WHERE workspace_id=? AND sha256=?", (workspace_id, digest)).fetchone()
        if prior:
            return {"import_id": prior["id"], "platform": prior["platform"],
                    "conversations": prior["conversation_count"], "messages": prior["message_count"], "duplicate": True}
        import_id = uuid.uuid4().hex
        normalized, message_total = [], 0
        db.execute("INSERT INTO tenant_imports VALUES(?,?,?,?,?,?,?,?)",
                   (import_id, workspace_id, Path(filename).name, platform, digest, 0, 0, _now()))
        for index, raw in enumerate(data):
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("id") or raw.get("uuid") or raw.get("conversation_id") or f"conversation-{index+1}")
            title = str(raw.get("title") or raw.get("name") or raw.get("subject") or f"Conversation {index+1}")
            messages = _messages(raw, source_id)
            existing = db.execute("SELECT id FROM tenant_conversations WHERE workspace_id=? AND platform=? AND source_id=?",
                                  (workspace_id, platform, source_id)).fetchone()
            conversation_id = existing["id"] if existing else uuid.uuid4().hex
            snippet = " ".join(next((m["content"] for m in messages if m["role"].lower() in {"user","human","customer"}), "").split())[:240]
            values = (import_id, title, snippet, _timestamp(raw.get("create_time") or raw.get("created_at")),
                      _timestamp(raw.get("update_time") or raw.get("updated_at")), len(messages),
                      json.dumps(raw, ensure_ascii=False, sort_keys=True), conversation_id, workspace_id)
            if existing:
                db.execute("DELETE FROM tenant_messages WHERE workspace_id=? AND conversation_id=?", (workspace_id, conversation_id))
                db.execute("DELETE FROM tenant_candidates WHERE workspace_id=? AND conversation_id=?", (workspace_id, conversation_id))
                db.execute("UPDATE tenant_conversations SET import_id=?,title=?,snippet=?,created_at=?,updated_at=?,message_count=?,raw_json=?,analysis_status='not_analyzed' WHERE id=? AND workspace_id=?", values)
            else:
                db.execute("INSERT INTO tenant_conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (conversation_id, workspace_id, import_id, source_id, platform, title, snippet,
                            values[3], values[4], len(messages), values[6], "not_analyzed"))
            for message in messages:
                db.execute("INSERT INTO tenant_messages VALUES(?,?,?,?,?,?,?,?,?)",
                           (uuid.uuid4().hex, workspace_id, conversation_id, message["source_id"], message["parent_source_id"],
                            message["ordinal"], message["role"], message["content"], message["created_at"]))
            message_total += len(messages)
            normalized.append({"id": conversation_id, "source_id": source_id, "title": title, "snippet": snippet,
                               "depth": len(messages), "platform": platform, "import_id": import_id})
        db.execute("UPDATE tenant_imports SET conversation_count=?,message_count=? WHERE id=? AND workspace_id=?",
                   (len(normalized), message_total, import_id, workspace_id))
    return {"import_id": import_id, "platform": platform, "conversations": len(normalized),
            "messages": message_total, "items": normalized, "duplicate": False}


def overview(workspace_id):
    initialize()
    with _connect() as db:
        result = {}
        for key, table in (("imports","tenant_imports"),("conversations","tenant_conversations"),("messages","tenant_messages")):
            result[key] = db.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", (workspace_id,)).fetchone()[0]
        result["pending"] = db.execute("SELECT COUNT(*) FROM tenant_candidates WHERE workspace_id=? AND status='pending'", (workspace_id,)).fetchone()[0]
        result["mapped"] = db.execute("SELECT COUNT(*) FROM tenant_conversations WHERE workspace_id=? AND analysis_status='analyzed'",(workspace_id,)).fetchone()[0]
        result["unmapped"] = result["conversations"]-result["mapped"]
    return result


def usage(workspace_id):
    initialize()
    with _connect() as db:
        return {
            "source_bytes":db.execute("SELECT COALESCE(SUM(byte_count),0) FROM tenant_source_files WHERE workspace_id=?",(workspace_id,)).fetchone()[0],
            "conversations":db.execute("SELECT COUNT(*) FROM tenant_conversations WHERE workspace_id=?",(workspace_id,)).fetchone()[0],
            "analysis_jobs":db.execute("SELECT COUNT(*) FROM tenant_analysis_jobs WHERE workspace_id=?",(workspace_id,)).fetchone()[0],
        }


def list_conversations(workspace_id, query="", limit=500, offset=0):
    initialize()
    with _connect() as db:
        if query.strip():
            like = f"%{query.strip()}%"
            rows = db.execute("""SELECT DISTINCT c.* FROM tenant_conversations c LEFT JOIN tenant_messages m
              ON m.conversation_id=c.id AND m.workspace_id=c.workspace_id
              WHERE c.workspace_id=? AND (c.title LIKE ? OR m.content LIKE ?)
              ORDER BY COALESCE(c.updated_at,c.created_at) DESC LIMIT ? OFFSET ?""", (workspace_id, like, like,limit,offset)).fetchall()
        else:
            rows = db.execute("SELECT * FROM tenant_conversations WHERE workspace_id=? ORDER BY COALESCE(updated_at,created_at) DESC LIMIT ? OFFSET ?", (workspace_id,limit,offset)).fetchall()
    return [dict(row) for row in rows]


def count_conversations(workspace_id,query=""):
    initialize()
    with _connect() as db:
        if query.strip():
            like=f"%{query.strip()}%"
            return db.execute("""SELECT COUNT(DISTINCT c.id) FROM tenant_conversations c LEFT JOIN tenant_messages m
              ON m.conversation_id=c.id AND m.workspace_id=c.workspace_id
              WHERE c.workspace_id=? AND (c.title LIKE ? OR m.content LIKE ?)""",(workspace_id,like,like)).fetchone()[0]
        return db.execute("SELECT COUNT(*) FROM tenant_conversations WHERE workspace_id=?",(workspace_id,)).fetchone()[0]


def get_conversation(workspace_id, conversation_id):
    initialize()
    with _connect() as db:
        row = db.execute("SELECT * FROM tenant_conversations WHERE id=? AND workspace_id=?", (conversation_id, workspace_id)).fetchone()
        if not row:
            return None
        messages = db.execute("SELECT * FROM tenant_messages WHERE conversation_id=? AND workspace_id=? ORDER BY ordinal", (conversation_id, workspace_id)).fetchall()
    return {"conversation": dict(row), "messages": [dict(item) for item in messages]}


def analyze(workspace_id, conversation_id):
    detail = get_conversation(workspace_id, conversation_id)
    if not detail:
        raise KeyError("Conversation not found")
    created = 0
    with _connect() as db:
        db.execute("DELETE FROM tenant_candidates WHERE workspace_id=? AND conversation_id=? AND status='pending'", (workspace_id, conversation_id))
        for message in detail["messages"]:
            if message["role"].lower() not in {"user","human","customer"}:
                continue
            text = " ".join(message["content"].split())
            lowered = text.lower()
            if len(text) < 35 or not any(marker in lowered for marker in ("i want", "we should", "we need", "decision:", "must ", "idea")):
                continue
            title = text[:120].rstrip(" .")
            kind = "decision" if "decision:" in lowered else "idea"
            db.execute("INSERT INTO tenant_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex, workspace_id, conversation_id, message["id"], kind, title, text,
                        .70, "Explicit user-authored intent language found in source message.", "pending", None, _now()))
            created += 1
        db.execute("UPDATE tenant_conversations SET analysis_status='analyzed' WHERE id=? AND workspace_id=?", (conversation_id, workspace_id))
    return {"conversation_id": conversation_id, "candidates_created": created, "abstained": created == 0}


def list_candidates(workspace_id, status="pending"):
    initialize()
    with _connect() as db:
        rows = db.execute("""SELECT c.*,m.content excerpt,v.title conversation_title,v.platform
          FROM tenant_candidates c JOIN tenant_messages m ON m.id=c.message_id AND m.workspace_id=c.workspace_id
          JOIN tenant_conversations v ON v.id=c.conversation_id AND v.workspace_id=c.workspace_id
          WHERE c.workspace_id=? AND c.status=? ORDER BY c.created_at DESC""", (workspace_id, status)).fetchall()
    return [dict(row) for row in rows]


def review(workspace_id, candidate_id, action):
    mapped = {"accept":"accepted", "reject":"rejected", "defer":"deferred"}
    if action not in mapped:
        raise ValueError("Action must be accept, reject, or defer")
    with _connect() as db:
        candidate = db.execute("SELECT * FROM tenant_candidates WHERE id=? AND workspace_id=?", (candidate_id, workspace_id)).fetchone()
        if not candidate or candidate["status"] != "pending":
            raise KeyError("Pending candidate not found")
        db.execute("UPDATE tenant_candidates SET status=?,reviewed_at=? WHERE id=? AND workspace_id=?",
                   (mapped[action], _now(), candidate_id, workspace_id))
    result = dict(candidate)
    result["status"] = mapped[action]
    return result


def create_import_job(workspace_id, filename):
    initialize(); job_id=uuid.uuid4().hex; now=_now()
    with _connect() as db:
        db.execute("INSERT INTO tenant_import_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (job_id,workspace_id,Path(filename).name,"queued","queued",0,None,None,now,now))
    return {"id":job_id,"status":"queued","stage":"queued","progress":0}


def update_import_job(workspace_id, job_id, **changes):
    allowed={"status","stage","progress","result_json","error"}; fields=[]; values=[]
    for key,value in changes.items():
        if key in allowed:
            fields.append(f"{key}=?"); values.append(json.dumps(value) if key=="result_json" and value is not None else value)
    fields.append("updated_at=?"); values.append(_now()); values.extend([job_id,workspace_id])
    with _connect() as db:
        changed=db.execute(f"UPDATE tenant_import_jobs SET {','.join(fields)} WHERE id=? AND workspace_id=?",values).rowcount
    if not changed: raise KeyError("Import job not found")


def get_import_job(workspace_id, job_id):
    initialize()
    with _connect() as db: row=db.execute("SELECT * FROM tenant_import_jobs WHERE id=? AND workspace_id=?",(job_id,workspace_id)).fetchone()
    if not row: return None
    item=dict(row); item["result"]=json.loads(item.pop("result_json")) if item.get("result_json") else None
    return item


def list_import_jobs(workspace_id):
    initialize()
    with _connect() as db: rows=db.execute("SELECT * FROM tenant_import_jobs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100",(workspace_id,)).fetchall()
    return [get_import_job(workspace_id,row["id"]) for row in rows]


def import_document_path(workspace_id, path, filename):
    source=Path(path)
    if Path(filename).suffix.lower()==".json":
        result=import_json_path(workspace_id,source,filename)
        result["coverage"]={"unit":"archive","detected":result["conversations"],"processed":result["conversations"],"unreadable":[],"status":"complete"}
        return result
    from document_ingest import extract_document
    extracted=extract_document(source.read_bytes(),filename)
    payload=[{"id":uuid.uuid4().hex,"title":Path(filename).stem,"created_at":_now(),
              "messages":[{"role":"user","content":extracted["text"]}]}]
    result=import_json(workspace_id,json.dumps(payload,ensure_ascii=False),filename)
    result["coverage"]=extracted["coverage"]
    return result


def preserve_source(workspace_id, import_id, staged_path, filename, coverage):
    initialize(); source=Path(staged_path); digest_builder=hashlib.sha256(); byte_count=0
    with source.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest_builder.update(chunk); byte_count+=len(chunk)
    digest=digest_builder.hexdigest(); source_id=uuid.uuid4().hex
    destination_dir=DB_PATH.parent/"tenant_sources"/workspace_id
    destination_dir.mkdir(parents=True,exist_ok=True)
    destination=destination_dir/f"{source_id}{Path(filename).suffix.lower()}"
    with _connect() as db:
        prior=db.execute("SELECT * FROM tenant_source_files WHERE workspace_id=? AND sha256=?",(workspace_id,digest)).fetchone()
        if prior: return dict(prior)
        shutil.copyfile(source,destination)
        media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream"
        db.execute("INSERT INTO tenant_source_files VALUES(?,?,?,?,?,?,?,?,?,?)",(source_id,workspace_id,import_id,Path(filename).name,media_type,digest,byte_count,str(destination),json.dumps(coverage,ensure_ascii=False),_now()))
    return {"id":source_id,"workspace_id":workspace_id,"import_id":import_id,"filename":Path(filename).name,
            "media_type":media_type,"sha256":digest,"byte_count":byte_count,"source_path":str(destination),"coverage_json":json.dumps(coverage),"created_at":_now()}


def list_sources(workspace_id):
    initialize()
    with _connect() as db: rows=db.execute("SELECT * FROM tenant_source_files WHERE workspace_id=? ORDER BY created_at DESC",(workspace_id,)).fetchall()
    result=[]
    for row in rows:
        item=dict(row); item["coverage"]=json.loads(item.pop("coverage_json")); item.pop("source_path",None); result.append(item)
    return result


def get_source(workspace_id,source_id,include_path=False):
    initialize()
    with _connect() as db: row=db.execute("SELECT * FROM tenant_source_files WHERE id=? AND workspace_id=?",(source_id,workspace_id)).fetchone()
    if not row: return None
    item=dict(row); item["coverage"]=json.loads(item.pop("coverage_json"))
    if not include_path: item.pop("source_path",None)
    return item


_BACKUP_TABLES=("tenant_imports","tenant_conversations","tenant_messages","tenant_candidates",
                "tenant_import_jobs","tenant_analysis_jobs","tenant_candidate_links")


def export_backup(workspace_id):
    initialize(); payload={"format":"seed-reflections-tenant-backup","version":1,"origin_workspace_id":workspace_id,"created_at":_now(),
                           "workspace":load_workspace(workspace_id=workspace_id),"tables":{},"sources":[]}
    with _connect() as db:
        for table in _BACKUP_TABLES:
            payload["tables"][table]=[dict(row) for row in db.execute(f"SELECT * FROM {table} WHERE workspace_id=?",(workspace_id,))]
        rows=db.execute("SELECT * FROM tenant_source_files WHERE workspace_id=?",(workspace_id,)).fetchall()
    for row in rows:
        item=dict(row); source_path=Path(item.pop("source_path")); item["content_base64"]=base64.b64encode(source_path.read_bytes()).decode() if source_path.is_file() else ""
        payload["sources"].append(item)
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return {"payload":payload,"sha256":hashlib.sha256(canonical).hexdigest()}


def export_backup_archive(workspace_id):
    """Create a disk-backed ZIP backup without base64-expanding source files in memory."""
    initialize(); payload={"format":"seed-reflections-tenant-backup","version":2,"origin_workspace_id":workspace_id,
        "created_at":_now(),"workspace":load_workspace(workspace_id=workspace_id),"tables":{},"sources":[]}
    with _connect() as db:
        for table in _BACKUP_TABLES:
            payload["tables"][table]=[dict(row) for row in db.execute(f"SELECT * FROM {table} WHERE workspace_id=?",(workspace_id,))]
        rows=db.execute("SELECT * FROM tenant_source_files WHERE workspace_id=?",(workspace_id,)).fetchall()
    handle,path=tempfile.mkstemp(prefix="seed-reflections-backup-",suffix=".zip",dir=DB_PATH.parent); __import__('os').close(handle)
    try:
        with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
            for row in rows:
                item=dict(row); source_path=Path(item.pop("source_path")); archive_name=f"sources/{item['id']}{source_path.suffix.lower()}"
                item["archive_path"]=archive_name; payload["sources"].append(item)
                if source_path.is_file(): archive.write(source_path,archive_name)
            canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
            manifest={"payload":payload,"sha256":hashlib.sha256(canonical).hexdigest()}
            archive.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,separators=(",",":")))
        return Path(path)
    except Exception:
        Path(path).unlink(missing_ok=True); raise


def _apply_verified_restore(workspace_id,payload,staged):
    tables=payload["tables"]; workspace=payload["workspace"]; sources=payload["sources"]
    replaced=[]; destination_dir=DB_PATH.parent/"tenant_sources"/workspace_id; destination_dir.mkdir(parents=True,exist_ok=True)
    rollback_dir=destination_dir/(".restore-rollback-"+uuid.uuid4().hex); rollback_dir.mkdir()
    try:
        for temporary,destination,_ in staged:
            prior=rollback_dir/destination.name
            if destination.exists(): destination.replace(prior)
            temporary.replace(destination); replaced.append((destination,prior))
        with _connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for table in reversed(_BACKUP_TABLES): db.execute(f"DELETE FROM {table} WHERE workspace_id=?",(workspace_id,))
            db.execute("DELETE FROM tenant_source_files WHERE workspace_id=?",(workspace_id,))
            for table in _BACKUP_TABLES:
                columns=[row[1] for row in db.execute(f"PRAGMA table_info({table})")]
                for item in tables.get(table,[]):
                    row=dict(item); row["workspace_id"]=workspace_id
                    db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",[row.get(column) for column in columns])
            columns=[row[1] for row in db.execute("PRAGMA table_info(tenant_source_files)")]
            for _,destination,item in staged:
                row={key:value for key,value in item.items() if key not in {"content_base64","archive_path"}}
                row["workspace_id"]=workspace_id; row["source_path"]=str(destination)
                db.execute(f"INSERT INTO tenant_source_files({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",[row.get(column) for column in columns])
            save_workspace_in_transaction(db,workspace,workspace_id,"verified_backup_restore")
        shutil.rmtree(rollback_dir)
    except Exception:
        for temporary,_,_ in staged: temporary.unlink(missing_ok=True)
        for destination,prior in reversed(replaced):
            destination.unlink(missing_ok=True)
            if prior.exists(): prior.replace(destination)
        shutil.rmtree(rollback_dir,ignore_errors=True); raise
    return {"status":"restored","imports":len(tables.get("tenant_imports",[])),"sources":len(sources)}


def restore_backup(workspace_id, package):
    if not isinstance(package,dict) or not isinstance(package.get("payload"),dict) or not package.get("sha256"):
        raise ValueError("Backup package is invalid")
    payload=package["payload"]
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    if not hmac.compare_digest(hashlib.sha256(canonical).hexdigest(),str(package["sha256"])):
        raise ValueError("Backup checksum verification failed")
    if payload.get("format")!="seed-reflections-tenant-backup" or payload.get("version")!=1:
        raise ValueError("Backup format is unsupported")
    if payload.get("origin_workspace_id")!=workspace_id:
        raise ValueError("Backup belongs to a different workspace")
    tables=payload.get("tables"); workspace=payload.get("workspace"); sources=payload.get("sources")
    if not isinstance(tables,dict) or not isinstance(workspace,dict) or not isinstance(sources,list):
        raise ValueError("Backup payload is incomplete")
    staged=[]; destination_dir=DB_PATH.parent/"tenant_sources"/workspace_id; destination_dir.mkdir(parents=True,exist_ok=True)
    try:
        for source in sources:
            content=base64.b64decode(source.get("content_base64") or "",validate=True)
            if hashlib.sha256(content).hexdigest()!=source.get("sha256") or len(content)!=source.get("byte_count"):
                raise ValueError("Preserved source integrity verification failed")
            destination=destination_dir/f"{source['id']}{Path(source['filename']).suffix.lower()}"
            temporary=destination_dir/("."+destination.name+"."+uuid.uuid4().hex+".restore")
            temporary.write_bytes(content); staged.append((temporary,destination,source))
        return _apply_verified_restore(workspace_id,payload,staged)
    except Exception:
        for temporary,_,_ in staged: temporary.unlink(missing_ok=True)
        raise


def restore_backup_archive(workspace_id,archive_path):
    """Verify and restore a version-2 ZIP backup using bounded file streams."""
    destination_dir=DB_PATH.parent/"tenant_sources"/workspace_id; destination_dir.mkdir(parents=True,exist_ok=True); staged=[]
    try:
        with zipfile.ZipFile(archive_path,"r") as archive:
            package=json.loads(archive.read("manifest.json"))
            payload=package.get("payload") if isinstance(package,dict) else None
            if not isinstance(payload,dict) or not package.get("sha256"): raise ValueError("Backup manifest is invalid")
            canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
            if not hmac.compare_digest(hashlib.sha256(canonical).hexdigest(),str(package["sha256"])): raise ValueError("Backup checksum verification failed")
            if payload.get("format")!="seed-reflections-tenant-backup" or payload.get("version")!=2: raise ValueError("Backup format is unsupported")
            if payload.get("origin_workspace_id")!=workspace_id: raise ValueError("Backup belongs to a different workspace")
            if not isinstance(payload.get("tables"),dict) or not isinstance(payload.get("workspace"),dict) or not isinstance(payload.get("sources"),list): raise ValueError("Backup payload is incomplete")
            for source in payload["sources"]:
                member=str(source.get("archive_path") or "")
                if not member.startswith("sources/"): raise ValueError("Backup source path is invalid")
                destination=destination_dir/f"{source['id']}{Path(source['filename']).suffix.lower()}"
                temporary=destination_dir/("."+destination.name+"."+uuid.uuid4().hex+".restore")
                digest=hashlib.sha256(); count=0
                with archive.open(member) as incoming,temporary.open("wb") as outgoing:
                    for chunk in iter(lambda:incoming.read(1024*1024),b""): digest.update(chunk); count+=len(chunk); outgoing.write(chunk)
                if digest.hexdigest()!=source.get("sha256") or count!=source.get("byte_count"): raise ValueError("Preserved source integrity verification failed")
                staged.append((temporary,destination,source))
        return _apply_verified_restore(workspace_id,payload,staged)
    except Exception:
        for temporary,_,_ in staged: temporary.unlink(missing_ok=True)
        raise


def import_json_path(workspace_id, path, filename="export.json"):
    """Incrementally normalize a top-level or wrapped conversation array."""
    initialize(); source=Path(path); digest_builder=hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest_builder.update(chunk)
    digest=digest_builder.hexdigest()
    with _connect() as db:
        prior=db.execute("SELECT * FROM tenant_imports WHERE workspace_id=? AND sha256=?",(workspace_id,digest)).fetchone()
        if prior:
            return {"import_id":prior["id"],"platform":prior["platform"],"conversations":prior["conversation_count"],"messages":prior["message_count"],"duplicate":True}
    iterator=iter_json_array(source)
    try: first=next(iterator)
    except StopIteration: raise ValueError("The JSON archive contains no conversations")
    platform=_platform([first],filename); import_id=uuid.uuid4().hex; normalized=[]; message_total=0
    with _connect() as db:
        db.execute("INSERT INTO tenant_imports VALUES(?,?,?,?,?,?,?,?)",(import_id,workspace_id,Path(filename).name,platform,digest,0,0,_now()))
        for index,raw in enumerate(itertools.chain([first],iterator)):
            if not isinstance(raw,dict): continue
            source_id=str(raw.get("id") or raw.get("uuid") or raw.get("conversation_id") or f"conversation-{index+1}")
            title=str(raw.get("title") or raw.get("name") or raw.get("subject") or f"Conversation {index+1}")
            messages=_messages(raw,source_id); existing=db.execute(
                "SELECT id FROM tenant_conversations WHERE workspace_id=? AND platform=? AND source_id=?",(workspace_id,platform,source_id)).fetchone()
            conversation_id=existing["id"] if existing else uuid.uuid4().hex
            snippet=" ".join(next((m["content"] for m in messages if m["role"].lower() in {"user","human","customer"}),"").split())[:240]
            created=_timestamp(raw.get("create_time") or raw.get("created_at")); updated=_timestamp(raw.get("update_time") or raw.get("updated_at")); raw_json=json.dumps(raw,ensure_ascii=False,sort_keys=True)
            if existing:
                db.execute("DELETE FROM tenant_messages WHERE workspace_id=? AND conversation_id=?",(workspace_id,conversation_id))
                db.execute("DELETE FROM tenant_candidates WHERE workspace_id=? AND conversation_id=?",(workspace_id,conversation_id))
                db.execute("UPDATE tenant_conversations SET import_id=?,title=?,snippet=?,created_at=?,updated_at=?,message_count=?,raw_json=?,analysis_status='not_analyzed' WHERE id=? AND workspace_id=?",
                           (import_id,title,snippet,created,updated,len(messages),raw_json,conversation_id,workspace_id))
            else:
                db.execute("INSERT INTO tenant_conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (conversation_id,workspace_id,import_id,source_id,platform,title,snippet,created,updated,len(messages),raw_json,"not_analyzed"))
            for message in messages:
                db.execute("INSERT INTO tenant_messages VALUES(?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,workspace_id,conversation_id,message["source_id"],message["parent_source_id"],message["ordinal"],message["role"],message["content"],message["created_at"]))
            message_total+=len(messages); normalized.append({"id":conversation_id,"source_id":source_id,"title":title,"snippet":snippet,"depth":len(messages),"platform":platform,"import_id":import_id})
        db.execute("UPDATE tenant_imports SET conversation_count=?,message_count=? WHERE id=? AND workspace_id=?",(len(normalized),message_total,import_id,workspace_id))
    return {"import_id":import_id,"platform":platform,"conversations":len(normalized),"messages":message_total,"items":normalized,"duplicate":False,"streamed":True}


def create_analysis_job(workspace_id):
    initialize(); job_id=uuid.uuid4().hex; now=_now()
    with _connect() as db:
        total=db.execute("SELECT COUNT(*) FROM tenant_conversations WHERE workspace_id=?",(workspace_id,)).fetchone()[0]
        db.execute("INSERT INTO tenant_analysis_jobs VALUES(?,?,?,?,?,?,?,?,?)",(job_id,workspace_id,"queued",total,0,0,None,now,now))
    return {"id":job_id,"status":"queued","total":total,"processed":0,"candidates_created":0}


def get_analysis_job(workspace_id, job_id):
    initialize()
    with _connect() as db: row=db.execute("SELECT * FROM tenant_analysis_jobs WHERE id=? AND workspace_id=?",(job_id,workspace_id)).fetchone()
    return dict(row) if row else None


def run_analysis_job(workspace_id, job_id):
    try:
        with _connect() as db:
            ids=[row[0] for row in db.execute("SELECT id FROM tenant_conversations WHERE workspace_id=? ORDER BY created_at",(workspace_id,))]
            db.execute("UPDATE tenant_analysis_jobs SET status='running',total=?,updated_at=? WHERE id=? AND workspace_id=?",(len(ids),_now(),job_id,workspace_id))
        created=0
        for index,conversation_id in enumerate(ids,1):
            created += analyze(workspace_id,conversation_id)["candidates_created"]
            with _connect() as db:
                db.execute("UPDATE tenant_analysis_jobs SET processed=?,candidates_created=?,updated_at=? WHERE id=? AND workspace_id=?",(index,created,_now(),job_id,workspace_id))
        with _connect() as db: db.execute("UPDATE tenant_analysis_jobs SET status='complete',updated_at=? WHERE id=? AND workspace_id=?",(_now(),job_id,workspace_id))
    except Exception as exc:
        with _connect() as db: db.execute("UPDATE tenant_analysis_jobs SET status='failed',error=?,updated_at=? WHERE id=? AND workspace_id=?",(str(exc),_now(),job_id,workspace_id))
    return get_analysis_job(workspace_id,job_id)


_STOP={"that","this","with","from","have","will","your","about","should","would","could","their","there","into","build","want","need","idea"}
def _terms(text): return {word for word in re.findall(r"[a-z0-9]{4,}",str(text).lower()) if word not in _STOP}


def generate_links(workspace_id):
    candidates=list_candidates(workspace_id,"pending"); created=0
    with _connect() as db:
        for index,left in enumerate(candidates):
            for right in candidates[index+1:]:
                if left["conversation_id"]==right["conversation_id"]: continue
                shared=sorted(_terms(left["interpretation"]) & _terms(right["interpretation"]))
                if len(shared)<2: continue
                pair=sorted([left["id"],right["id"]])
                exists=db.execute("SELECT 1 FROM tenant_candidate_links WHERE workspace_id=? AND left_candidate_id=? AND right_candidate_id=?",(workspace_id,pair[0],pair[1])).fetchone()
                if exists: continue
                score=min(.95,len(shared)/10)
                db.execute("INSERT INTO tenant_candidate_links VALUES(?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,workspace_id,pair[0],pair[1],json.dumps(shared),score,"pending",_now(),None)); created+=1
    return {"links_created":created}


def list_links(workspace_id,status="pending"):
    initialize()
    with _connect() as db: rows=db.execute("SELECT * FROM tenant_candidate_links WHERE workspace_id=? AND status=? ORDER BY created_at DESC",(workspace_id,status)).fetchall()
    items=[]
    for row in rows:
        item=dict(row); item["shared_terms"]=json.loads(item.pop("shared_terms_json")); items.append(item)
    return items


def review_link(workspace_id,link_id,action):
    mapped={"accept":"accepted","reject":"rejected","defer":"deferred"}
    if action not in mapped: raise ValueError("Action must be accept, reject, or defer")
    with _connect() as db:
        row=db.execute("SELECT * FROM tenant_candidate_links WHERE id=? AND workspace_id=? AND status='pending'",(link_id,workspace_id)).fetchone()
        if not row: raise KeyError("Pending relationship proposal not found")
        db.execute("UPDATE tenant_candidate_links SET status=?,reviewed_at=? WHERE id=? AND workspace_id=?",(mapped[action],_now(),link_id,workspace_id))
    return {"id":link_id,"status":mapped[action]}
