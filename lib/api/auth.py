from __future__ import annotations
import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

SECRETS_DIR = Path.home() / ".config" / "agentbox-v5" / "secrets"
TOKEN_PATH = SECRETS_DIR / "admin.token"
COOKIE_NAME = "agentbox_session"

def _now() -> datetime:
    return datetime.now(timezone.utc)

def ensure_admin_token() -> str:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        t = TOKEN_PATH.read_text().strip()
        if t:
            return t
    t = secrets.token_urlsafe(48)
    TOKEN_PATH.write_text(t + "\n")
    os.chmod(TOKEN_PATH, 0o600)
    return t

def read_admin_token() -> Optional[str]:
    if not TOKEN_PATH.is_file():
        return None
    t = TOKEN_PATH.read_text().strip()
    return t or None

def rotate_admin_token() -> str:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    t = secrets.token_urlsafe(48)
    TOKEN_PATH.write_text(t + "\n")
    os.chmod(TOKEN_PATH, 0o600)
    return t

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def verify_admin_token(token: str) -> bool:
    exp = read_admin_token()
    if not exp or not token:
        return False
    return hmac.compare_digest(token.strip(), exp.strip())

def create_session(conn, role: str = "admin", timeout_minutes: int = 120) -> tuple[str, str]:
    sid = "ses_" + secrets.token_hex(12)
    raw = secrets.token_urlsafe(32)
    exp = _now() + timedelta(minutes=timeout_minutes)
    conn.execute(
        "INSERT INTO web_sessions (id, user_role, token_hash, expires_at) VALUES (?,?,?,?)",
        (sid, role, hash_token(raw), exp.strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()
    return sid, raw

def lookup_session(conn, raw: str) -> Optional[dict]:
    if not raw:
        return None
    row = conn.execute(
        "SELECT * FROM web_sessions WHERE token_hash=? AND revoked_at IS NULL",
        (hash_token(raw),),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        exp = datetime.strptime(d["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    if exp < _now():
        return None
    return d

def revoke_session(conn, session_id: str) -> bool:
    cur = conn.execute(
        "UPDATE web_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
        (_now().strftime("%Y-%m-%dT%H:%M:%SZ"), session_id),
    )
    conn.commit()
    return cur.rowcount > 0

def list_sessions(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, user_role, created_at, expires_at, revoked_at FROM web_sessions ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    return [dict(r) for r in rows]

def role_allows(role: str, needed: str) -> bool:
    order = {"viewer": 1, "operator": 2, "admin": 3}
    return order.get(role, 0) >= order.get(needed, 99)
