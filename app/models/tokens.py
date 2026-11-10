"""Password-reset tokens. Only a SHA-256 hash is stored, tokens expire and work exactly once."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.models.users import now_iso


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_reset_token(user_id: int, minutes: int) -> str:
    """Create a new token (and cancel the user's older unused ones). Returns the RAW token for the email."""
    raw = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    db = get_db()
    db.execute("DELETE FROM password_reset_tokens WHERE user_id = ? AND used = 0", (user_id,))
    db.execute("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
               (user_id, _hash(raw), expires, now_iso()))
    db.commit()
    return raw


def _valid_row(raw: str):
    row = get_db().execute("SELECT * FROM password_reset_tokens WHERE token_hash = ? AND used = 0",
                           (_hash(raw or ""),)).fetchone()
    if row and datetime.fromisoformat(row["expires_at"]) > datetime.now(timezone.utc):
        return row
    return None


def is_valid(raw: str) -> bool:
    return _valid_row(raw) is not None


def consume(raw: str) -> int | None:
    """Mark the token used and return its user id; None if it is unknown, used or expired."""
    row = _valid_row(raw)
    if row is None:
        return None
    db = get_db()
    # "AND used = 0" makes this safe even if two requests race with the same token
    cur = db.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = ? AND used = 0", (row["id"],))
    db.commit()
    return row["user_id"] if cur.rowcount == 1 else None
