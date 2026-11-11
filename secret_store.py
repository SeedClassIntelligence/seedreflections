"""Encrypted, tenant-scoped model credentials.

Local Windows deployments use DPAPI. Hosted deployments use per-credential data
keys wrapped by an AES-GCM master key supplied through the deployment secret
manager. Plaintext secrets are never stored or returned by metadata APIs.
"""
from __future__ import annotations

import base64, ctypes, json, os, secrets, sqlite3, uuid
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from archive_store import DB_PATH

def _now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(DB_PATH)
    try: yield db; db.commit()
    finally: db.close()

class _Blob(ctypes.Structure):
    _fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_ubyte))]

def _dpapi(raw, protect=True):
    crypt32=ctypes.WinDLL("crypt32",use_last_error=True); kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
    function=crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect: function.argtypes=[ctypes.POINTER(_Blob),wintypes.LPCWSTR,ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    else: function.argtypes=[ctypes.POINTER(_Blob),ctypes.POINTER(wintypes.LPWSTR),ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    function.restype=wintypes.BOOL; kernel32.LocalFree.argtypes=[ctypes.c_void_p]
    incoming=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw); source=_Blob(len(raw),incoming); output=_Blob()
    arguments=(ctypes.byref(source),"SeedReflections model credential",None,None,None,1,ctypes.byref(output)) if protect else (ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    if not function(*arguments): raise ctypes.WinError(ctypes.get_last_error())
    try: return bytes(ctypes.string_at(output.pbData,output.cbData))
    finally: kernel32.LocalFree(output.pbData)

def _master_key():
    encoded=os.environ.get("SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY","").strip()
    if not encoded: raise RuntimeError("Hosted BYOK requires SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY from the deployment secret manager")
    try: key=base64.urlsafe_b64decode(encoded+"="*(-len(encoded)%4))
    except Exception as exc: raise RuntimeError("Credential master key is not valid base64") from exc
    if len(key)!=32: raise RuntimeError("Credential master key must decode to exactly 32 bytes")
    return key

KEYRING_SERVICE = "SeedReflections model credential"
_SESSION_KEYS = {}  # (workspace_id, provider) -> key; memory only, never persisted, cleared on restart


def _keyring_module():
    """Return the keyring module only when it has a real OS-backed backend."""
    try:
        import keyring
        from keyring.backends import fail
    except Exception:
        return None
    backend = keyring.get_keyring()
    if isinstance(backend, fail.Keyring) or getattr(backend, "priority", 0) <= 0:
        return None
    return keyring


def local_backend_status():
    """Describe how a local model key can be stored on this machine."""
    if os.name == "nt":
        return {"saved_keys": True, "backend": "windows_dpapi", "session_only_keys": True,
                "detail": "Saved keys are protected by Windows (DPAPI) for the current user."}
    keyring = _keyring_module()
    if keyring is not None:
        kind = "macos_keychain" if os.uname().sysname == "Darwin" else "os_keyring"
        return {"saved_keys": True, "backend": kind, "session_only_keys": True,
                "detail": "Saved keys are held by the operating system keychain; the database stores no key material."}
    return {"saved_keys": False, "backend": None, "session_only_keys": True,
            "detail": "No operating-system keychain is available, so saved keys are disabled. A key can be used for this session only and is forgotten when SeedReflections restarts."}


def _keyring_name(workspace_id, provider): return f"{workspace_id}:{provider}"

def _encrypt(value, mode):
    raw=value.encode("utf-8")
    if mode=="local":
        if os.name!="nt": raise RuntimeError("Saved keys are unavailable: this computer has no operating-system keychain. Use a session-only key instead.")
        return "windows_dpapi",base64.b64encode(_dpapi(raw,True)).decode(),""
    master=_master_key(); data_key=secrets.token_bytes(32); data_nonce=secrets.token_bytes(12); wrap_nonce=secrets.token_bytes(12)
    ciphertext=AESGCM(data_key).encrypt(data_nonce,raw,b"SeedReflections:model-key")
    wrapped=AESGCM(master).encrypt(wrap_nonce,data_key,b"SeedReflections:data-key")
    payload={"v":1,"n":base64.b64encode(data_nonce).decode(),"c":base64.b64encode(ciphertext).decode(),"wn":base64.b64encode(wrap_nonce).decode()}
    return "aes256gcm_envelope",base64.b64encode(json.dumps(payload,separators=(",",":")).encode()).decode(),base64.b64encode(wrapped).decode()

def _decrypt(scheme,ciphertext,wrapped_key):
    if scheme=="windows_dpapi": return _dpapi(base64.b64decode(ciphertext),False).decode("utf-8")
    if scheme!="aes256gcm_envelope": raise RuntimeError("Unsupported credential protection scheme")
    payload=json.loads(base64.b64decode(ciphertext)); master=_master_key()
    data_key=AESGCM(master).decrypt(base64.b64decode(payload["wn"]),base64.b64decode(wrapped_key),b"SeedReflections:data-key")
    return AESGCM(data_key).decrypt(base64.b64decode(payload["n"]),base64.b64decode(payload["c"]),b"SeedReflections:model-key").decode("utf-8")

def initialize():
    with _connect() as db: db.execute("""CREATE TABLE IF NOT EXISTS model_credentials(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, provider TEXT NOT NULL, scheme TEXT NOT NULL,
      ciphertext TEXT NOT NULL, wrapped_key TEXT NOT NULL, key_hint TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_used_at TEXT,
      UNIQUE(workspace_id,provider))""")

def set_credential(workspace_id,provider,value,deployment_mode="local",temporary=False):
    value=str(value or "").strip()
    if not value: raise ValueError("API key is required")
    if temporary:
        if deployment_mode!="local": raise ValueError("Session-only keys are available only in local mode")
        _SESSION_KEYS[(workspace_id,provider)]=value
        return credential_status(workspace_id,provider)
    now=_now(); initialize()
    if deployment_mode=="local" and os.name!="nt":
        keyring=_keyring_module()
        if keyring is None: raise RuntimeError("Saved keys are unavailable: this computer has no operating-system keychain. Use a session-only key instead.")
        try: keyring.set_password(KEYRING_SERVICE,_keyring_name(workspace_id,provider),value)
        except Exception as exc: raise RuntimeError("The operating-system keychain refused the key: "+str(exc)) from exc
        scheme,ciphertext,wrapped="os_keyring","keychain",""
    else:
        scheme,ciphertext,wrapped=_encrypt(value,deployment_mode)
    _SESSION_KEYS.pop((workspace_id,provider),None)
    with _connect() as db:
        db.execute("""INSERT INTO model_credentials(id,workspace_id,provider,scheme,ciphertext,wrapped_key,key_hint,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,provider) DO UPDATE SET scheme=excluded.scheme,ciphertext=excluded.ciphertext,
          wrapped_key=excluded.wrapped_key,key_hint=excluded.key_hint,updated_at=excluded.updated_at""",
          (uuid.uuid4().hex,workspace_id,provider,scheme,ciphertext,wrapped,value[-4:],now,now))
    return credential_status(workspace_id,provider)

def get_credential(workspace_id,provider):
    if (workspace_id,provider) in _SESSION_KEYS: return _SESSION_KEYS[(workspace_id,provider)]
    initialize()
    with _connect() as db:
        db.row_factory=sqlite3.Row; row=db.execute("SELECT * FROM model_credentials WHERE workspace_id=? AND provider=?",(workspace_id,provider)).fetchone()
        if not row: return ""
        if row["scheme"]=="os_keyring":
            keyring=_keyring_module()
            value=(keyring.get_password(KEYRING_SERVICE,_keyring_name(workspace_id,provider)) if keyring else None) or ""
            if value: db.execute("UPDATE model_credentials SET last_used_at=? WHERE id=?",(_now(),row["id"]))
            return value
        value=_decrypt(row["scheme"],row["ciphertext"],row["wrapped_key"])
        db.execute("UPDATE model_credentials SET last_used_at=? WHERE id=?",(_now(),row["id"])); return value

def credential_status(workspace_id,provider):
    if (workspace_id,provider) in _SESSION_KEYS:
        return {"credential_configured":True,"provider":provider,"scheme":"session_only","key_hint":_SESSION_KEYS[(workspace_id,provider)][-4:],
                "persisted":False,"note":"Held in memory for this session only; forgotten when SeedReflections restarts."}
    initialize()
    with _connect() as db:
        db.row_factory=sqlite3.Row; row=db.execute("SELECT provider,key_hint,scheme,created_at,updated_at,last_used_at FROM model_credentials WHERE workspace_id=? AND provider=?",(workspace_id,provider)).fetchone()
    return ({"credential_configured":False,"provider":provider} if not row else {"credential_configured":True,**dict(row)})

def delete_credential(workspace_id,provider):
    initialize()
    removed_session=_SESSION_KEYS.pop((workspace_id,provider),None) is not None
    with _connect() as db:
        row=db.execute("SELECT scheme FROM model_credentials WHERE workspace_id=? AND provider=?",(workspace_id,provider)).fetchone()
        changed=db.execute("DELETE FROM model_credentials WHERE workspace_id=? AND provider=?",(workspace_id,provider)).rowcount
    if row and row[0]=="os_keyring":
        keyring=_keyring_module()
        if keyring is not None:
            try: keyring.delete_password(KEYRING_SERVICE,_keyring_name(workspace_id,provider))
            except Exception: pass
    return bool(changed) or removed_session
