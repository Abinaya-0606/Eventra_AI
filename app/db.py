"""SQLite connection handling and a safe migration runner.

Every query in the app uses '?' placeholders (never string formatting), so user input
cannot change the SQL.

Migrations are numbered files in app/migrations/ and each one runs once, in order:
  * Before an existing database is upgraded, a consistent copy is written next to it
    (``<db>.pre-v<N>.bak``, N = the version it was at), so nothing can be lost.
  * Every migration runs inside ONE transaction together with the version bump. If any
    statement fails, the whole migration is rolled back and the database stays at the
    previous version with all its users and events intact.
"""
import sqlite3
from pathlib import Path

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db() -> sqlite3.Connection:
    """One connection per request, closed automatically when the request ends."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_version(database_path: str) -> int:
    """Schema version stored in the database file (0 for a new/empty one)."""
    conn = sqlite3.connect(database_path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _backup(path: Path, version: int) -> None:
    """Consistent copy of the database (SQLite online-backup API) taken before an upgrade."""
    target = Path(f"{path}.pre-v{version}.bak")
    if target.exists():  # keep the oldest copy if an upgrade is retried
        return
    source, copy = sqlite3.connect(path), sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()


def run_migrations(database_path: str) -> int:
    """Apply every migration newer than the database's stored version. Returns the version reached."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scripts = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: int(p.stem.split("_")[0]))
    conn = sqlite3.connect(path, timeout=15)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        pending = [s for s in scripts if int(s.stem.split("_")[0]) > version]
        if pending and version > 0:
            _backup(path, version)
        for script in pending:
            number = int(script.stem.split("_")[0])  # comes from a file name we control
            try:
                conn.executescript(f"BEGIN;\n{script.read_text(encoding='utf-8')}\nPRAGMA user_version = {number};\nCOMMIT;")
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.rollback()
                raise
            version = number
        return version
    finally:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    run_migrations(app.config["DATABASE"])
