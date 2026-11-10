"""Student registrations for events.

The capacity check and the insert happen inside one write transaction (BEGIN IMMEDIATE), so two students
cannot both take the last seat. UNIQUE (event_id, user_id) is a second line of defence against duplicates.
"""
from app.db import get_db
from app.models.users import now_iso

OK, DUPLICATE, FULL = "ok", "duplicate", "full"


def count_active(event_id: int) -> int:
    return get_db().execute("SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status = 'registered'",
                            (event_id,)).fetchone()[0]


def is_registered(event_id: int, user_id: int) -> bool:
    return get_db().execute("SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'registered'",
                            (event_id, user_id)).fetchone() is not None


def register(event_id: int, user_id: int, capacity: int) -> str:
    """Returns OK, DUPLICATE or FULL. Re-registering after a cancellation re-activates the old row."""
    db = get_db()
    if db.in_transaction:
        db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT status FROM registrations WHERE event_id = ? AND user_id = ?", (event_id, user_id)).fetchone()
        if row and row["status"] == "registered":
            db.rollback()
            return DUPLICATE
        taken = db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status = 'registered'", (event_id,)).fetchone()[0]
        if taken >= capacity:
            db.rollback()
            return FULL
        if row:
            db.execute("UPDATE registrations SET status = 'registered', created_at = ?, cancelled_at = NULL "
                       "WHERE event_id = ? AND user_id = ?", (now_iso(), event_id, user_id))
        else:
            db.execute("INSERT INTO registrations (event_id, user_id, created_at) VALUES (?,?,?)", (event_id, user_id, now_iso()))
        db.commit()
        return OK
    except Exception:
        db.rollback()
        raise


def cancel(event_id: int, user_id: int) -> bool:
    db = get_db()
    cur = db.execute("UPDATE registrations SET status = 'cancelled', cancelled_at = ? "
                     "WHERE event_id = ? AND user_id = ? AND status = 'registered'", (now_iso(), event_id, user_id))
    db.commit()
    return cur.rowcount > 0


def for_user(user_id: int, upcoming: bool | None = None, today: str = ""):
    """The student's active registrations with event details. upcoming=True/False filters by date."""
    sql = ("SELECT r.id AS registration_id, r.created_at AS registered_at, e.*, o.name AS owner_name "
           "FROM registrations r JOIN events e ON e.id = r.event_id JOIN users o ON o.id = e.owner_id "
           "WHERE r.user_id = ? AND r.status = 'registered'")
    params: list = [user_id]
    if upcoming is True:
        sql += " AND e.event_date >= ?"
        params.append(today)
    elif upcoming is False:
        sql += " AND e.event_date < ?"
        params.append(today)
    sql += " ORDER BY e.event_date" + (" DESC" if upcoming is False else "") + ", e.start_time, e.id"
    return get_db().execute(sql, params).fetchall()


def for_event(event_id: int):
    """Active registrations of one event with the student's details (organizer view)."""
    return get_db().execute(
        "SELECT r.id, r.created_at, u.id AS user_id, u.name, u.email, u.department FROM registrations r "
        "JOIN users u ON u.id = r.user_id WHERE r.event_id = ? AND r.status = 'registered' ORDER BY r.created_at, r.id",
        (event_id,)).fetchall()


def active_user_ids(event_id: int) -> list[int]:
    return [r["user_id"] for r in get_db().execute(
        "SELECT user_id FROM registrations WHERE event_id = ? AND status = 'registered'", (event_id,))]


def total_active() -> int:
    return get_db().execute("SELECT COUNT(*) FROM registrations WHERE status = 'registered'").fetchone()[0]
