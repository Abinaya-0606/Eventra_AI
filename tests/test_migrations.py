"""Database migrations: upgrading a database created by the previous version keeps every user and event."""
import sqlite3
from pathlib import Path

import pytest

from app import create_app
from app.db import MIGRATIONS_DIR, current_version, run_migrations

OLD = ["001_users.sql", "002_events_tasks.sql", "003_planning.sql"]
LATEST = max(int(p.stem.split("_")[0]) for p in MIGRATIONS_DIR.glob("*.sql"))


def make_legacy_db(path):
    """A database exactly as the previous release left it (schema versions 1-3) with real-looking data."""
    conn = sqlite3.connect(path)
    for name in OLD:
        conn.executescript((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
    conn.execute("PRAGMA user_version = 3")
    now = "2025-01-01T00:00:00+00:00"
    users = [("Old Student", "oldorganizer@example.com", "student"), ("Plain Student", "plain@example.com", "student"),
             ("Old Org", "oldorg@example.com", "organizer"), ("Old Admin", "oldadmin@example.com", "admin")]
    for name, email, role in users:
        conn.execute("INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                     (name, email, "hash-" + email, role, now))
    ev = "INSERT INTO events (owner_id, name, event_type, participants, budget, duration_hours, event_date, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
    conn.execute(ev, (1, "Legacy Student Event", "Workshop", 40, 5000, 3, "2099-01-01", "approved", now, "2025-02-02T00:00:00+00:00"))
    conn.execute(ev, (3, "Legacy Pending", "Seminar", 80, 9000, 2, "2099-02-01", "pending", now, "2025-03-03T00:00:00+00:00"))
    conn.execute(ev, (3, "Legacy Draft", "Hackathon", 100, 1000, 8, "2099-03-01", "draft", now, now))
    conn.execute("INSERT INTO tasks (event_id, title, created_at) VALUES (2, 'Old task', ?)", (now,))
    conn.execute("INSERT INTO activities (user_id, owner_id, event_id, message, created_at) VALUES (3, 3, 2, 'old activity', ?)", (now,))
    conn.commit()
    conn.close()


@pytest.fixture()
def legacy(tmp_path):
    path = tmp_path / "legacy.db"
    make_legacy_db(path)
    return path


def rows(path, sql, *p):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, p).fetchall()
    finally:
        conn.close()


def test_upgrade_preserves_all_existing_data(legacy):
    before_users = rows(legacy, "SELECT id, name, email, password_hash FROM users ORDER BY id")
    before_events = rows(legacy, "SELECT id, owner_id, name, status, budget, updated_at FROM events ORDER BY id")
    assert current_version(str(legacy)) == 3

    assert run_migrations(str(legacy)) == LATEST and current_version(str(legacy)) == LATEST

    assert rows(legacy, "SELECT id, name, email, password_hash FROM users ORDER BY id") == before_users
    assert rows(legacy, "SELECT id, owner_id, name, status, budget, updated_at FROM events ORDER BY id") == before_events
    assert rows(legacy, "SELECT COUNT(*) FROM tasks")[0][0] == 1 and rows(legacy, "SELECT COUNT(*) FROM activities")[0][0] == 1
    assert rows(legacy, "SELECT COUNT(*) FROM venues")[0][0] == 2


def test_upgrade_adds_new_tables_columns_and_keeps_relationships(legacy):
    run_migrations(str(legacy))
    tables = {r[0] for r in rows(legacy, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"registrations", "notifications"} <= tables
    cols = {r[1] for r in rows(legacy, "PRAGMA table_info(events)")}
    assert {"submitted_at", "reviewed_by", "reviewed_at"} <= cols
    conn = sqlite3.connect(legacy)
    conn.execute("PRAGMA foreign_keys = ON")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.execute("INSERT INTO registrations (event_id, user_id, created_at) VALUES (1, 2, 'now')")
    with pytest.raises(sqlite3.IntegrityError):  # duplicate registration
        conn.execute("INSERT INTO registrations (event_id, user_id, created_at) VALUES (1, 2, 'now')")
    with pytest.raises(sqlite3.IntegrityError):  # unknown event
        conn.execute("INSERT INTO registrations (event_id, user_id, created_at) VALUES (999, 2, 'now')")
    conn.rollback()
    conn.close()


def test_students_who_owned_events_become_organizers_nobody_else_changes(legacy):
    run_migrations(str(legacy))
    roles = dict(rows(legacy, "SELECT email, role FROM users"))
    assert roles == {"oldorganizer@example.com": "organizer", "plain@example.com": "student",
                     "oldorg@example.com": "organizer", "oldadmin@example.com": "admin"}


def test_pending_events_get_submission_time(legacy):
    run_migrations(str(legacy))
    assert rows(legacy, "SELECT submitted_at FROM events WHERE name = 'Legacy Pending'")[0][0] == "2025-03-03T00:00:00+00:00"
    assert rows(legacy, "SELECT submitted_at FROM events WHERE name = 'Legacy Draft'")[0][0] is None


def test_backup_is_written_before_upgrading(legacy):
    run_migrations(str(legacy))
    backup = Path(str(legacy) + ".pre-v3.bak")
    assert backup.exists()
    assert current_version(str(backup)) == 3  # the copy is the old schema, untouched
    assert rows(backup, "SELECT COUNT(*) FROM users")[0][0] == 4


def test_migrations_are_idempotent(legacy):
    run_migrations(str(legacy))
    snapshot = rows(legacy, "SELECT * FROM events ORDER BY id")
    assert run_migrations(str(legacy)) == LATEST
    assert rows(legacy, "SELECT * FROM events ORDER BY id") == snapshot


def test_fresh_database_reaches_latest_version_without_backup(tmp_path):
    path = tmp_path / "fresh.db"
    latest = max(int(p.stem.split("_")[0]) for p in MIGRATIONS_DIR.glob("*.sql"))
    assert run_migrations(str(path)) == latest
    assert not list(tmp_path.glob("*.bak"))


def test_failed_migration_rolls_back_completely(legacy, monkeypatch, tmp_path):
    bad_dir = tmp_path / "migrations"
    bad_dir.mkdir()
    for f in MIGRATIONS_DIR.glob("*.sql"):
        (bad_dir / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (bad_dir / "004_workflow.sql").write_text("ALTER TABLE events ADD COLUMN x TEXT;\nCREATE TABLE broken (;\n", encoding="utf-8")
    monkeypatch.setattr("app.db.MIGRATIONS_DIR", bad_dir)
    with pytest.raises(sqlite3.Error):
        run_migrations(str(legacy))
    assert current_version(str(legacy)) == 3
    assert "x" not in {r[1] for r in rows(legacy, "PRAGMA table_info(events)")}  # the ALTER was rolled back too
    assert rows(legacy, "SELECT COUNT(*) FROM events")[0][0] == 3


def test_app_starts_on_a_legacy_database_and_old_users_can_log_in(legacy, monkeypatch):
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(legacy)
    conn.execute("UPDATE users SET password_hash = ? WHERE email = 'oldorg@example.com'", (generate_password_hash("Passw0rd!x", method="pbkdf2:sha256:1000"),))
    conn.commit()
    conn.close()
    from conftest import CSRFClient
    app = create_app("testing", {"DATABASE": str(legacy)})
    app.test_client_class = CSRFClient
    c = app.test_client()
    assert c.post("/login", data={"email": "oldorg@example.com", "password": "Passw0rd!x"}).status_code == 302
    html = c.get("/events").get_data(as_text=True)
    assert "Legacy Pending" in html and "Legacy Draft" in html
    # and the upgraded organizer (formerly a student) still sees the event they created
    with app.app_context():
        from app.models import events, users
        u = users.get_by_email("oldorganizer@example.com")
        assert u.role == "organizer" and events.search(u)[1] == 1
