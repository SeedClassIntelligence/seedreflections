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
        CREATE TABLE IF NOT EXISTS runtime_memberships(workspace_id TEXT NOT NULL REFERENCES runtime_workspaces(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL REFERENCES runtime_users(id) ON DELETE CASCADE,role TEXT NOT NULL,created_at TEXT NOT NULL,
          PRIMARY KEY(workspace_id,user_id));
        CREATE TABLE IF NOT EXISTS runtime_invitations(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES runtime_workspaces(id) ON DELETE CASCADE,
          email TEXT NOT NULL,role TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,invited_by TEXT NOT NULL,
          expires_at TEXT NOT NULL,accepted_at TEXT,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS runtime_auth_attempts_window ON runtime_auth_attempts(attempt_key,attempted_at);
        CREATE INDEX IF NOT EXISTS runtime_invitations_email ON runtime_invitations(email,accepted_at);
        """)
        db.execute("DELETE FROM runtime_sessions WHERE expires_at<=?",(_now(),))
        db.execute("INSERT OR IGNORE INTO runtime_workspaces VALUES('local','My Archive','local',?)",(_now(),))
        db.execute("INSERT OR IGNORE INTO runtime_users VALUES('local-owner','local',?,?,?,?,?)",
                   ('local@seedreflections.internal','Local Owner',None,'owner',_now()))
        db.execute("INSERT OR IGNORE INTO runtime_memberships SELECT workspace_id,id,role,created_at FROM runtime_users")

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
            db.execute("INSERT INTO runtime_memberships VALUES(?,?,?,?)",(workspace_id,user_id,'owner',_now()))
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


def list_members(workspace_id):
    initialize()
    with _connect() as db:
        rows=db.execute("""SELECT u.id,u.email,u.name,m.role,m.created_at FROM runtime_memberships m
          JOIN runtime_users u ON u.id=m.user_id WHERE m.workspace_id=? ORDER BY m.created_at,u.email""",(workspace_id,)).fetchall()
    return [dict(row) for row in rows]


def list_workspaces(user_id):
    initialize()
    with _connect() as db:
        rows=db.execute("""SELECT w.id,w.name,w.mode,m.role,u.workspace_id=w.id AS active FROM runtime_memberships m
          JOIN runtime_workspaces w ON w.id=m.workspace_id JOIN runtime_users u ON u.id=m.user_id
          WHERE m.user_id=? ORDER BY w.created_at""",(user_id,)).fetchall()
    return [dict(row) for row in rows]


def create_invitation(workspace_id,email,role,invited_by,hours=168):
    initialize(); email=str(email or '').strip().lower(); role=str(role or 'editor').strip().lower()
    if '@' not in email or '.' not in email.rsplit('@',1)[-1]: raise ValueError('A valid email is required')
    if role not in {'editor','viewer'}: raise ValueError('Invitation role must be editor or viewer')
    token=secrets.token_urlsafe(40); digest=hashlib.sha256(token.encode()).hexdigest(); invitation_id=uuid.uuid4().hex
    expires=(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat()
    with _connect() as db:
        existing=db.execute("SELECT id FROM runtime_memberships m JOIN runtime_users u ON u.id=m.user_id WHERE m.workspace_id=? AND u.email=?",(workspace_id,email)).fetchone()
        if existing: raise ValueError('That person is already a workspace member')
        db.execute("DELETE FROM runtime_invitations WHERE workspace_id=? AND email=? AND accepted_at IS NULL",(workspace_id,email))
        db.execute("INSERT INTO runtime_invitations VALUES(?,?,?,?,?,?,?,?,?)",(invitation_id,workspace_id,email,role,digest,invited_by,expires,None,_now()))
    return {'id':invitation_id,'email':email,'role':role,'expires_at':expires,'token':token}


def list_invitations(workspace_id):
    initialize()
    with _connect() as db:
        rows=db.execute("SELECT id,email,role,expires_at,accepted_at,created_at FROM runtime_invitations WHERE workspace_id=? ORDER BY created_at DESC",(workspace_id,)).fetchall()
    return [dict(row) for row in rows]


def accept_invitation(token,user_id):
    initialize(); digest=hashlib.sha256(str(token or '').encode()).hexdigest()
    with _connect() as db:
        invitation=db.execute("SELECT * FROM runtime_invitations WHERE token_hash=?",(digest,)).fetchone()
        user=db.execute("SELECT * FROM runtime_users WHERE id=?",(user_id,)).fetchone()
        if not invitation or invitation['accepted_at'] or invitation['expires_at']<=_now(): raise ValueError('Invitation is invalid or expired')
        if not user or user['email'].lower()!=invitation['email'].lower(): raise ValueError('Invitation email does not match the authenticated account')
        db.execute("INSERT OR REPLACE INTO runtime_memberships VALUES(?,?,?,?)",(invitation['workspace_id'],user_id,invitation['role'],_now()))
        db.execute("UPDATE runtime_users SET workspace_id=?,role=? WHERE id=?",(invitation['workspace_id'],invitation['role'],user_id))
        db.execute("UPDATE runtime_invitations SET accepted_at=? WHERE id=?",(_now(),invitation['id']))
    return {'workspace_id':invitation['workspace_id'],'role':invitation['role']}


def switch_workspace(user_id,workspace_id):
    initialize()
    with _connect() as db:
        membership=db.execute("SELECT role FROM runtime_memberships WHERE user_id=? AND workspace_id=?",(user_id,workspace_id)).fetchone()
        if not membership: raise ValueError('Workspace membership not found')
        db.execute("UPDATE runtime_users SET workspace_id=?,role=? WHERE id=?",(workspace_id,membership['role'],user_id))
    return {'workspace_id':workspace_id,'role':membership['role']}


def update_member_role(workspace_id,user_id,role):
    initialize(); role=str(role or '').lower()
    if role not in {'owner','editor','viewer'}: raise ValueError('Role must be owner, editor, or viewer')
    with _connect() as db:
        current=db.execute("SELECT role FROM runtime_memberships WHERE workspace_id=? AND user_id=?",(workspace_id,user_id)).fetchone()
        if not current: raise ValueError('Workspace member not found')
        owners=db.execute("SELECT COUNT(*) FROM runtime_memberships WHERE workspace_id=? AND role='owner'",(workspace_id,)).fetchone()[0]
        if current['role']=='owner' and role!='owner' and owners<=1: raise ValueError('A workspace must retain at least one owner')
        db.execute("UPDATE runtime_memberships SET role=? WHERE workspace_id=? AND user_id=?",(role,workspace_id,user_id))
        db.execute("UPDATE runtime_users SET role=? WHERE id=? AND workspace_id=?",(role,user_id,workspace_id))
    return {'user_id':user_id,'role':role}


def remove_member(workspace_id,user_id):
    initialize()
    with _connect() as db:
        current=db.execute("SELECT role FROM runtime_memberships WHERE workspace_id=? AND user_id=?",(workspace_id,user_id)).fetchone()
        if not current: raise ValueError('Workspace member not found')
        owners=db.execute("SELECT COUNT(*) FROM runtime_memberships WHERE workspace_id=? AND role='owner'",(workspace_id,)).fetchone()[0]
        if current['role']=='owner' and owners<=1: raise ValueError('The last workspace owner cannot be removed')
        db.execute("DELETE FROM runtime_memberships WHERE workspace_id=? AND user_id=?",(workspace_id,user_id))
        replacement=db.execute("SELECT workspace_id,role FROM runtime_memberships WHERE user_id=? ORDER BY created_at LIMIT 1",(user_id,)).fetchone()
        if replacement: db.execute("UPDATE runtime_users SET workspace_id=?,role=? WHERE id=?",(replacement['workspace_id'],replacement['role'],user_id))
    return {'removed':True,'user_id':user_id}

def logout(token):
    with _connect() as db: db.execute("DELETE FROM runtime_sessions WHERE token_hash=?",(hashlib.sha256(str(token or '').encode()).hexdigest(),))


def delete_account(user_id,password):
    """Permanently delete a hosted account after re-checking its password.

    A workspace the person is the only member of is erased completely. In a shared workspace
    they only leave, unless they are its only owner, in which case they must hand it over or
    remove the other members first. Returns what was done."""
    from account_erasure import erase_workspace_data
    initialize()
    with _connect() as db:
        user=db.execute("SELECT * FROM runtime_users WHERE id=?",(str(user_id),)).fetchone()
        if not user or user['id']=='local-owner': raise ValueError('Account deletion is only available for hosted accounts')
        if not _password_valid(str(password or ''),user['password_hash']): raise ValueError('The password is not correct')
        erase,leave=[],[]
        for membership in db.execute("SELECT workspace_id,role FROM runtime_memberships WHERE user_id=?",(user['id'],)).fetchall():
            workspace=membership['workspace_id']
            members=db.execute("SELECT COUNT(*) FROM runtime_memberships WHERE workspace_id=?",(workspace,)).fetchone()[0]
            owners=db.execute("SELECT COUNT(*) FROM runtime_memberships WHERE workspace_id=? AND role='owner'",(workspace,)).fetchone()[0]
            if members<=1: erase.append(workspace)
            elif membership['role']=='owner' and owners<=1:
                name=db.execute("SELECT name FROM runtime_workspaces WHERE id=?",(workspace,)).fetchone()['name']
                raise ValueError(f'You are the only owner of the shared workspace "{name}". Make someone else an owner or remove its other members first.')
            else: leave.append(workspace)
    erased={}
    for workspace in erase:
        erased[workspace]=erase_workspace_data(workspace)
    with _connect() as db:
        for workspace in leave:
            try: db.execute("DELETE FROM workspace_accounts WHERE workspace_id=? AND lower(email)=?",(workspace,user['email'].lower()))
            except sqlite3.OperationalError: pass   # that table exists only once a workspace document has been saved
        db.execute("DELETE FROM runtime_sessions WHERE user_id=?",(user['id'],))
        db.execute("DELETE FROM runtime_invitations WHERE invited_by=? OR lower(email)=?",(user['id'],user['email'].lower()))
        db.execute("DELETE FROM runtime_memberships WHERE user_id=?",(user['id'],))
        db.execute("DELETE FROM runtime_users WHERE id=?",(user['id'],))
        for workspace in erase:
            db.execute("DELETE FROM runtime_workspaces WHERE id=?",(workspace,))
    return {'deleted':True,'workspaces_erased':len(erase),'workspaces_left':len(leave),'records_removed':sum(sum(v.values()) for v in erased.values())}
