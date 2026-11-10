"""User accounts: all database access for the users table lives here."""
import sqlite3
from datetime import datetime, timezone

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db

ROLES = ("student", "organizer", "admin")
# Used to spend the same time on unknown emails as on real ones (prevents account guessing by timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


class EmailTaken(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class User:
    def __init__(self, row: sqlite3.Row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.role = row["role"]
        self.language = row["language"]
        self.department = row["department"]
        self.session_version = row["session_version"]
        self.is_active = bool(row["is_active"])
        self.created_at = row["created_at"]
        self.password_hash = row["password_hash"]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def initials(self) -> str:
        parts = self.name.split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"


def _hash(password: str) -> str:
    return generate_password_hash(password, method=current_app.config["PASSWORD_HASH_METHOD"])


def _one(sql: str, params=()) -> User | None:
    row = get_db().execute(sql, params).fetchone()
    return User(row) if row else None


def get_by_id(user_id: int) -> User | None:
    return _one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_by_email(email: str) -> User | None:
    return _one("SELECT * FROM users WHERE email = ?", (email,))


def create_user(name: str, email: str, password: str, *, role: str = "student",
                department: str = "", language: str = "en") -> User:
    if role not in ROLES:
        raise ValueError("invalid role")
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, role, language, department, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, email, _hash(password), role, language, department, now_iso()))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise EmailTaken from None
    return get_by_id(cur.lastrowid)


def verify_password(user: User | None, password: str) -> bool:
    """True only for a real, active-or-not user with the right password. Always does one hash check."""
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return check_password_hash(user.password_hash, password)


def update_profile(user_id: int, name: str, department: str, language: str) -> None:
    db = get_db()
    db.execute("UPDATE users SET name = ?, department = ?, language = ? WHERE id = ?",
               (name, department, language, user_id))
    db.commit()


def set_password(user_id: int, password: str) -> None:
    """Change the password and bump session_version, which signs the user out everywhere else."""
    db = get_db()
    db.execute("UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?",
               (_hash(password), user_id))
    db.commit()


def set_role(user_id: int, role: str) -> None:
    if role not in ROLES:
        raise ValueError("invalid role")
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()


def set_active(user_id: int, active: bool) -> None:
    db = get_db()
    db.execute("UPDATE users SET is_active = ?, session_version = session_version + 1 WHERE id = ?",
               (int(active), user_id))
    db.commit()


def list_users(role: str | None = None) -> list[User]:
    if role:
        return [User(r) for r in get_db().execute("SELECT * FROM users WHERE role = ? ORDER BY created_at, id", (role,))]
    return [User(r) for r in get_db().execute("SELECT * FROM users ORDER BY created_at, id")]


def counts_by_role() -> dict:
    """{role: count} for roles that have at least one account."""
    return {r["role"]: r["n"] for r in get_db().execute("SELECT role, COUNT(*) AS n FROM users GROUP BY role")}


def list_with_counts(role: str | None = None) -> list:
    """Accounts (of one role, or all) with what they have done: events created or active registrations."""
    where, params = (" WHERE u.role = ?", (role,)) if role else ("", ())
    return get_db().execute(
        "SELECT u.*, "
        "(SELECT COUNT(*) FROM events e WHERE e.owner_id = u.id) AS event_count, "
        "(SELECT COUNT(*) FROM events e WHERE e.owner_id = u.id AND e.status = 'approved') AS approved_count, "
        "(SELECT COUNT(*) FROM registrations r WHERE r.user_id = u.id AND r.status = 'registered') AS registration_count "
        "FROM users u" + where + " ORDER BY u.created_at, u.id", params).fetchall()


def admin_exists() -> bool:
    return get_db().execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone() is not None
