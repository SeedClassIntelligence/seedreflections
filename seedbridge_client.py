"""SeedBridge desktop companion for authorized hosted synchronization.

The companion never discovers and uploads silently. Pairing validates a scoped
delivery token; `connect` records an explicitly authorized source; `sync`
delivers only changed JSON/JSONL conversation files.
"""
from __future__ import annotations

import argparse, base64, ctypes, hashlib, json, os, sqlite3, sys, urllib.error, urllib.parse, urllib.request
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

from connector_store import PROVIDERS, _candidate_files, _jsonl_conversation

VERSION="1.0"
MAX_FILE_BYTES=250*1024*1024


def _now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def bridge_home():
    explicit=os.environ.get("SEEDBRIDGE_HOME")
    if explicit: return Path(explicit).expanduser().resolve()
    if os.name=="nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"])/"SeedReflections"/"SeedBridge"
    return Path.home()/".seedreflections"/"seedbridge"


def _atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
    try: os.chmod(temporary,0o600)
    except OSError: pass
    temporary.replace(path)


class _Blob(ctypes.Structure):
    _fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi_functions():
    crypt32=ctypes.WinDLL("crypt32",use_last_error=True); kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
    protect=crypt32.CryptProtectData
    protect.argtypes=[ctypes.POINTER(_Blob),wintypes.LPCWSTR,ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    protect.restype=wintypes.BOOL
    unprotect=crypt32.CryptUnprotectData
    unprotect.argtypes=[ctypes.POINTER(_Blob),ctypes.POINTER(wintypes.LPWSTR),ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    unprotect.restype=wintypes.BOOL
    kernel32.LocalFree.argtypes=[ctypes.c_void_p]; kernel32.LocalFree.restype=ctypes.c_void_p
    return protect,unprotect,kernel32.LocalFree


def _windows_protect(raw):
    incoming=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw); source=_Blob(len(raw),incoming); output=_Blob()
    protect,_,local_free=_dpapi_functions()
    if not protect(ctypes.byref(source),"SeedBridge",None,None,None,1,ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    try: return bytes(ctypes.string_at(output.pbData,output.cbData))
    finally: local_free(output.pbData)


def _windows_unprotect(raw):
    incoming=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw); source=_Blob(len(raw),incoming); output=_Blob()
    _,unprotect,local_free=_dpapi_functions()
    if not unprotect(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    try: return bytes(ctypes.string_at(output.pbData,output.cbData))
    finally: local_free(output.pbData)


def protect_token(token):
    raw=token.encode("utf-8")
    return "dpapi:"+base64.b64encode(_windows_protect(raw)).decode() if os.name=="nt" else "file:"+base64.b64encode(raw).decode()


def unprotect_token(value):
    scheme,encoded=value.split(":",1); raw=base64.b64decode(encoded)
    if scheme=="dpapi": return _windows_unprotect(raw).decode("utf-8")
    if scheme=="file": return raw.decode("utf-8")
    raise ValueError("Unknown SeedBridge token protection scheme")


def _config_path(): return bridge_home()/"config.json"
def _state_path(): return bridge_home()/"state.db"


def load_config(required=True):
    path=_config_path()
    if not path.exists():
        if required: raise RuntimeError("SeedBridge is not paired. Run: seedbridge pair --server URL --token TOKEN")
        return {"sources":[]}
    data=json.loads(path.read_text(encoding="utf-8")); data.setdefault("sources",[]); return data


def _request(server,path,token,payload=None):
    url=server.rstrip("/")+path
    body=json.dumps(payload,ensure_ascii=False).encode("utf-8") if payload is not None else b"{}"
    request=urllib.request.Request(url,data=body,method="POST",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json","User-Agent":"SeedBridge/"+VERSION})
    try:
        with urllib.request.urlopen(request,timeout=30) as response: return response.status,json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try: detail=json.loads(exc.read().decode("utf-8"))
        except Exception: detail={"error":str(exc)}
        return exc.code,detail


def pair(server,token):
    parsed=urllib.parse.urlparse(server)
    if parsed.scheme not in {"http","https"} or not parsed.netloc: raise ValueError("SeedBridge server must be an http(s) URL")
    if parsed.scheme!="https" and parsed.hostname not in {"127.0.0.1","localhost"}: raise ValueError("Remote SeedBridge pairing requires HTTPS")
    if not str(token).startswith("sr_live_"): raise ValueError("A scoped Seed Reflections connection token is required")
    status,result=_request(server,"/api/v2/integrations/ping",token)
    if status!=200: raise RuntimeError(result.get("error") or "SeedBridge pairing validation failed")
    current=load_config(False)
    try:
        protected=protect_token(token); token_settings={"token":protected,"token_storage":"windows_dpapi" if os.name=="nt" else "restricted_file"}
    except OSError:
        token_settings={"token_env":"SEEDBRIDGE_TOKEN","token_storage":"environment_required"}
    current.pop("token",None); current.pop("token_env",None)
    current.update({"server":server.rstrip("/"),"paired_at":_now(),"integration":result,**token_settings})
    _atomic_json(_config_path(),current)
    return {"status":"paired","server":current["server"],"integration":result,"token_storage":current["token_storage"],
        "environment_required":current["token_storage"]=="environment_required"}


def discover():
    results=[]
    for provider,definition in PROVIDERS.items():
        if provider=="folder": continue
        paths=[]
        for candidate in definition["paths"]:
            try:
                if candidate.is_dir(): paths.append(str(candidate.resolve()))
            except OSError: pass
        results.append({"provider":provider,"name":definition["name"],"detected":bool(paths),"paths":paths})
    return results


def _safe_root(value):
    root=Path(value).expanduser().resolve()
    if not root.is_dir(): raise ValueError("The selected source folder does not exist")
    if root==Path(root.anchor) or root==Path.home().resolve(): raise ValueError("Choose a specific AI application data folder, not an entire drive or home folder")
    return root


def preview(provider,path):
    if provider not in PROVIDERS: raise ValueError("Unsupported SeedBridge provider")
    root=_safe_root(path); items=[]
    for source in _candidate_files(root):
        if source.suffix.lower() not in {".json",".jsonl"}: continue
        stat=source.stat()
        if stat.st_size>MAX_FILE_BYTES: continue
        items.append({"path":source.relative_to(root).as_posix(),"bytes":stat.st_size,
            "sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"modified_at":datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat()})
    return {"provider":provider,"root_path":str(root),"eligible":items,"count":len(items)}


def connect(provider,path,authorize=False):
    result=preview(provider,path)
    if not authorize: return {**result,"connected":False,"authorization_required":True}
    config=load_config(); source={"id":hashlib.sha256((provider+"\0"+result["root_path"]).encode()).hexdigest()[:24],
        "provider":provider,"root_path":result["root_path"],"authorized_at":_now(),"read_only":True}
    config["sources"]=[item for item in config["sources"] if item["id"]!=source["id"]]+[source]
    _atomic_json(_config_path(),config); return {**result,"connected":True,"source":source}


@contextmanager
def _state_db():
    path=_state_path(); path.parent.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS files(source_id TEXT,path TEXT,sha256 TEXT,synced_at TEXT,PRIMARY KEY(source_id,path))")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def _payload(path,root,provider):
    if path.suffix.lower()==".jsonl":
        conversation=_jsonl_conversation(path,root,provider)
        if not conversation: raise ValueError("No conversation messages found")
        return {"conversation":conversation}
    data=json.loads(path.read_text(encoding="utf-8-sig",errors="replace"))
    if isinstance(data,list): return {"conversations":data}
    if isinstance(data,dict) and any(key in data for key in ("conversations","conversation","messages")): return data
    raise ValueError("JSON does not contain conversations, conversation, or messages")


def sync(source_id=None):
    config=load_config()
    if config.get("token"): token=unprotect_token(config["token"])
    else:
        token=os.environ.get(config.get("token_env") or "SEEDBRIDGE_TOKEN")
        if not token: raise RuntimeError("Set SEEDBRIDGE_TOKEN for this paired bridge; protected OS token storage was unavailable")
    outcomes=[]
    sources=[item for item in config["sources"] if source_id in {None,item["id"]}]
    if source_id and not sources: raise KeyError("Authorized SeedBridge source not found")
    with _state_db() as db:
        for source in sources:
            root=_safe_root(source["root_path"]); changed=unchanged=failed=0; errors=[]
            for path in _candidate_files(root):
                if path.suffix.lower() not in {".json",".jsonl"} or path.stat().st_size>MAX_FILE_BYTES: continue
                relative=path.relative_to(root).as_posix(); digest=hashlib.sha256(path.read_bytes()).hexdigest()
                prior=db.execute("SELECT sha256 FROM files WHERE source_id=? AND path=?",(source["id"],relative)).fetchone()
                if prior and prior[0]==digest: unchanged+=1; continue
                try:
                    status,result=_request(config["server"],"/api/v2/integrations/import",token,_payload(path,root,source["provider"]))
                    if status not in {200,201,202}: raise RuntimeError(result.get("error") or f"Delivery failed ({status})")
                    db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?)",(source["id"],relative,digest,_now())); changed+=1
                except Exception as exc:
                    failed+=1
                    if len(errors)<20: errors.append({"path":relative,"error":str(exc)})
            outcomes.append({"source_id":source["id"],"provider":source["provider"],"files_synced":changed,"files_unchanged":unchanged,"files_failed":failed,"errors":errors})
    return {"status":"complete" if all(not item["files_failed"] for item in outcomes) else "attention","sources":outcomes,"synced_at":_now()}


def status():
    config=load_config(False)
    return {"name":"SeedBridge","version":VERSION,"paired":bool(config.get("server") and (config.get("token") or config.get("token_env"))),
        "server":config.get("server"),"integration":config.get("integration"),"sources":config.get("sources",[]),"home":str(bridge_home())}


def main(argv=None):
    parser=argparse.ArgumentParser(prog="seedbridge",description="Read-only Seed Reflections desktop companion")
    commands=parser.add_subparsers(dest="command",required=True)
    pair_cmd=commands.add_parser("pair"); pair_cmd.add_argument("--server",required=True); pair_cmd.add_argument("--token",required=True)
    commands.add_parser("discover"); commands.add_parser("status")
    preview_cmd=commands.add_parser("preview"); preview_cmd.add_argument("--provider",required=True); preview_cmd.add_argument("--path",required=True)
    connect_cmd=commands.add_parser("connect"); connect_cmd.add_argument("--provider",required=True); connect_cmd.add_argument("--path",required=True); connect_cmd.add_argument("--authorize",action="store_true")
    sync_cmd=commands.add_parser("sync"); sync_cmd.add_argument("--source-id")
    args=parser.parse_args(argv)
    try:
        result=(pair(args.server,args.token) if args.command=="pair" else discover() if args.command=="discover" else status() if args.command=="status" else
            preview(args.provider,args.path) if args.command=="preview" else connect(args.provider,args.path,args.authorize) if args.command=="connect" else sync(args.source_id))
        print(json.dumps(result,indent=2)); return 0
    except Exception as exc:
        print(json.dumps({"error":str(exc)}),file=sys.stderr); return 1


if __name__=="__main__": raise SystemExit(main())
