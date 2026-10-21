"""Authentication/session storage shared by local, hosted, and enterprise modes."""
import base64, hashlib, hmac, secrets, sqlite3, time, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from archive_store import DB_PATH

def _now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

@contextmanager
def _connect():
    db=sqlite3.connect(DB_PATH,timeout=30); db.row_factory=sqlite3.Row
    try: yield db; db.commit()
    finally: db.close()

def initialize():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS runtime_workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,mode TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runtime_users(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES runtime_workspaces(id) ON DELETE CASCADE,
          email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,password_hash TEXT,role TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runtime_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES runtime_users(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runtime_auth_attempts(attempt_key TEXT NOT NULL,attempted_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS runtime_auth_attempts_window ON runtime_auth_attempts(attempt_key,attempted_at);
        """)
        db.execute("DELETE FROM runtime_sessions WHERE expires_at<=?",(_now(),))
        db.execute("INSERT OR IGNORE INTO runtime_workspaces VALUES('local','My Archive','local',?)",(_now(),))
        db.execute("INSERT OR IGNORE INTO runtime_users VALUES('local-owner','local',?,?,?,?,?)",
                   ('local@seedreflections.internal','Local Owner',None,'owner',_now()))

def consume_auth_attempt(key,limit,window_seconds):
    """Atomically consume an authentication attempt from a shared SQLite window."""
    initialize(); now=int(time.time()); cutoff=now-int(window_seconds)
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM runtime_auth_attempts WHERE attempted_at<=?",(cutoff,))
        count=db.execute("SELECT COUNT(*) FROM runtime_auth_attempts WHERE attempt_key=? AND attempted_at>?",
                         (str(key),cutoff)).fetchone()[0]
        if count>=int(limit): return False
        db.execute("INSERT INTO runtime_auth_attempts VALUES(?,?)",(str(key),now))
        return True

def _password_hash(password):
    salt=secrets.token_bytes(16); rounds=310000
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,rounds)
    return f"pbkdf2_sha256${rounds}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def _password_valid(password,encoded):
    try:
        _,rounds,salt,expected=encoded.split('$',3)
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.urlsafe_b64decode(salt),int(rounds))
        return hmac.compare_digest(base64.urlsafe_b64encode(actual).decode(),expected)
    except Exception: return False

def signup(name,email,password,mode):
    initialize(); name=str(name or '').strip(); email=str(email or '').strip().lower(); password=str(password or '')
    if not name or '@' not in email or '.' not in email.rsplit('@',1)[-1] or len(password)<12: raise ValueError('Name, valid email, and a password of at least 12 characters are required')
    workspace_id=uuid.uuid4().hex; user_id=uuid.uuid4().hex
    try:
        with _connect() as db:
            db.execute("INSERT INTO runtime_workspaces VALUES(?,?,?,?)",(workspace_id,f"{name}'s Archive",mode,_now()))
            db.execute("INSERT INTO runtime_users VALUES(?,?,?,?,?,?,?)",(user_id,workspace_id,email,name,_password_hash(password),'owner',_now()))
    except sqlite3.IntegrityError: raise ValueError('Account already exists')
    return issue_session(user_id) | {'workspace_id':workspace_id,'user':{'id':user_id,'name':name,'email':email}}

def issue_session(user_id,hours=24):
    token=secrets.token_urlsafe(40); digest=hashlib.sha256(token.encode()).hexdigest()
    expires=(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat()
    with _connect() as db:
        db.execute("DELETE FROM runtime_sessions WHERE expires_at<=?",(_now(),))
        db.execute("INSERT INTO runtime_sessions VALUES(?,?,?,?)",(digest,user_id,expires,_now()))
        db.execute("""DELETE FROM runtime_sessions WHERE user_id=? AND token_hash NOT IN
          (SELECT token_hash FROM runtime_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 10)""",(user_id,user_id))
    return {'access_token':token}

def login(email,password):
    initialize()
    with _connect() as db: user=db.execute("SELECT * FROM runtime_users WHERE email=?",(str(email or '').strip().lower(),)).fetchone()
    if not user or not _password_valid(str(password or ''),user['password_hash']): raise ValueError('Invalid credentials')
    return issue_session(user['id']) | {'workspace_id':user['workspace_id'],'user':{'id':user['id'],'name':user['name'],'email':user['email']}}

def authenticate(token):
    initialize(); digest=hashlib.sha256(str(token or '').encode()).hexdigest()
    with _connect() as db:
        row=db.execute("""SELECT u.* FROM runtime_sessions s JOIN runtime_users u ON u.id=s.user_id
          WHERE s.token_hash=? AND s.expires_at>?""",(digest,_now())).fetchone()
    return dict(row) if row else None

def logout(token):
    with _connect() as db: db.execute("DELETE FROM runtime_sessions WHERE token_hash=?",(hashlib.sha256(str(token or '').encode()).hexdigest(),))
