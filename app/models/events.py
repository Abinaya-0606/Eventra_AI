"""Events and their saved schedules. All SQL uses ? placeholders."""
import calendar
from datetime import date

from app.db import get_db
from app.models.users import now_iso

_BASE = """SELECT e.*, u.name AS owner_name, u.email AS owner_email, u.department AS owner_department,
    rv.name AS reviewer_name,
    (SELECT GROUP_CONCAT(DISTINCT t.assignee_id) FROM tasks t WHERE t.event_id = e.id AND t.assignee_id IS NOT NULL) AS assignee_ids,
    (SELECT COUNT(*) FROM tasks t WHERE t.event_id = e.id) AS task_total,
    (SELECT COUNT(*) FROM tasks t WHERE t.event_id = e.id AND t.status = 'done') AS task_done,
    (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status = 'registered') AS registered_count
    FROM events e JOIN users u ON u.id = e.owner_id LEFT JOIN users rv ON rv.id = e.reviewed_by"""


class Event:
    def __init__(self, row):
        for key in row.keys():
            setattr(self, key, row[key])

    @property
    def progress(self) -> int:
        return round(100 * self.task_done / self.task_total) if self.task_total else 0


def _scope(user):
    """Admins see every event; everyone else sees only their own."""
    return ("", ()) if user.is_admin else (" WHERE e.owner_id = ?", (user.id,))


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get(event_id: int):
    row = get_db().execute(_BASE + " WHERE e.id = ?", (event_id,)).fetchone()
    return Event(row) if row else None


def create(owner_id: int, data: dict) -> int:
    now = now_iso()
    db = get_db()
    cur = db.execute(
        "INSERT INTO events (owner_id, name, event_type, description, participants, budget, duration_hours, "
        "venue, event_date, start_time, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (owner_id, data["name"], data["event_type"], data["description"], data["participants"], data["budget"],
         data["duration_hours"], data["venue"], data["event_date"], data["start_time"], now, now))
    db.commit()
    return cur.lastrowid


def update(event_id: int, data: dict, status: str | None = None) -> None:
    """Save edited fields. A new `status` is applied too (approved -> pending needs re-approval)."""
    db = get_db()
    now = now_iso()
    db.execute(
        "UPDATE events SET name=?, event_type=?, description=?, participants=?, budget=?, duration_hours=?, "
        "venue=?, event_date=?, start_time=?, status=COALESCE(?, status), "
        "submitted_at=CASE WHEN ? = 'pending' THEN ? ELSE submitted_at END, updated_at=? WHERE id=?",
        (data["name"], data["event_type"], data["description"], data["participants"], data["budget"],
         data["duration_hours"], data["venue"], data["event_date"], data["start_time"], status,
         status, now, now, event_id))
    db.commit()


def set_status(event_id: int, status: str, admin_note: str = "", reviewer_id: int | None = None) -> None:
    """Apply a workflow transition and keep the audit columns right.

    pending  -> submission time is recorded and the previous review is cleared
    approved -> reviewer + time recorded, rejection reason cleared
    rejected -> reviewer + time recorded, the reason is kept so the organizer can correct the event
    """
    db = get_db()
    now = now_iso()
    if status == "pending":
        db.execute("UPDATE events SET status='pending', submitted_at=?, reviewed_by=NULL, reviewed_at=NULL, updated_at=? WHERE id=?",
                   (now, now, event_id))
    elif status == "approved":
        db.execute("UPDATE events SET status='approved', admin_note='', reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
                   (reviewer_id, now, now, event_id))
    elif status == "rejected":
        db.execute("UPDATE events SET status='rejected', admin_note=?, reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
                   (admin_note, reviewer_id, now, now, event_id))
    else:
        db.execute("UPDATE events SET status=?, updated_at=? WHERE id=?", (status, now, event_id))
    db.commit()
    if status in ("approved", "rejected"):  # keep the full decision history (see models/reviews.py)
        from app.models import reviews
        reviews.record(event_id, reviewer_id, status, admin_note if status == "rejected" else "")


def delete(event_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()


def search(user, q: str = "", status: str = "", event_type: str = "", page: int = 1, per_page: int = 10):
    """Return (events, total_count) for the My Events list."""
    where, params = _scope(user)
    clauses, args = ([where.replace(" WHERE ", "")] if where else []), list(params)
    if q:
        clauses.append("(e.name LIKE ? ESCAPE '\\' OR e.venue LIKE ? ESCAPE '\\')")
        args += [f"%{_escape_like(q)}%"] * 2
    if status:
        clauses.append("e.status = ?")
        args.append(status)
    if event_type:
        clauses.append("e.event_type = ?")
        args.append(event_type)
    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM events e" + where_sql, args).fetchone()[0]
    rows = db.execute(_BASE + where_sql + " ORDER BY e.event_date DESC, e.id DESC LIMIT ? OFFSET ?",
                      args + [per_page, (page - 1) * per_page]).fetchall()
    return [Event(r) for r in rows], total


def stats(user) -> dict:
    where, params = _scope(user)
    row = get_db().execute(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed,
                  COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS awaiting_approval,
                  COALESCE(SUM(CASE WHEN event_date >= ? AND status NOT IN ('completed', 'rejected') THEN 1 ELSE 0 END), 0) AS upcoming,
                  COALESCE(SUM(CASE WHEN status != 'rejected' THEN budget END), 0) AS budget
           FROM events e""" + where, (date.today().isoformat(),) + params).fetchone()
    return dict(row)


def upcoming(user, limit: int = 5) -> list[Event]:
    where, params = _scope(user)
    clause = (where + " AND" if where else " WHERE") + " e.event_date >= ? AND e.status NOT IN ('completed', 'rejected')"
    rows = get_db().execute(_BASE + clause + " ORDER BY e.event_date, e.start_time LIMIT ?",
                            params + (date.today().isoformat(), limit)).fetchall()
    return [Event(r) for r in rows]


def in_month(user, year: int, month: int) -> dict:
    """{date string: [events]} for the calendar grid. Students see every approved event, nothing else."""
    where, params = ((" WHERE e.status = 'approved'", ()) if user.role == "student" else _scope(user))
    last = calendar.monthrange(year, month)[1]
    clause = (where + " AND" if where else " WHERE") + " e.event_date BETWEEN ? AND ?"
    rows = get_db().execute(_BASE + clause + " ORDER BY e.start_time, e.id",
                            params + (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}")).fetchall()
    days: dict[str, list] = {}
    for r in rows:
        days.setdefault(r["event_date"], []).append(Event(r))
    return days


# ---------- saved schedule ----------
def get_schedule(event_id: int) -> list:
    return get_db().execute("SELECT * FROM event_schedule_items WHERE event_id = ? ORDER BY start_time, position",
                            (event_id,)).fetchall()


def replace_schedule(event_id: int, items: list[dict]) -> None:
    db = get_db()
    db.execute("DELETE FROM event_schedule_items WHERE event_id = ?", (event_id,))
    db.executemany("INSERT INTO event_schedule_items (event_id, position, start_time, title, description) VALUES (?,?,?,?,?)",
                   [(event_id, i, it["time"], it["title"], it["description"]) for i, it in enumerate(items)])
    db.commit()


# ---------- student side: only APPROVED events are ever returned ----------
def browse(user_id: int, q: str = "", event_type: str = "", date_from: str = "", date_to: str = "",
           open_only: bool = False, include_past: bool = False, page: int = 1, per_page: int = 9):
    """Approved events for students: (events, total). Each event has registered_count and is_registered."""
    clauses, args = ["e.status = 'approved'"], []
    if not include_past:
        clauses.append("e.event_date >= ?")
        args.append(date.today().isoformat())
    if q:
        like = f"%{_escape_like(q)}%"
        clauses.append("(e.name LIKE ? ESCAPE '\\' OR e.venue LIKE ? ESCAPE '\\' OR e.description LIKE ? ESCAPE '\\' OR e.event_type LIKE ? ESCAPE '\\')")
        args += [like] * 4
    if event_type:
        clauses.append("e.event_type = ?")
        args.append(event_type)
    if date_from:
        clauses.append("e.event_date >= ?")
        args.append(date_from)
    if date_to:
        clauses.append("e.event_date <= ?")
        args.append(date_to)
    if open_only:
        clauses.append("(SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status = 'registered') < e.participants")
    where = " WHERE " + " AND ".join(clauses)
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM events e" + where, args).fetchone()[0]
    sql = _BASE.replace("FROM events e JOIN", (
        ", EXISTS(SELECT 1 FROM registrations r WHERE r.event_id = e.id AND r.user_id = ? AND r.status = 'registered') AS is_registered "
        "FROM events e JOIN"), 1)
    rows = db.execute(sql + where + " ORDER BY e.event_date, e.start_time, e.id LIMIT ? OFFSET ?",
                      [user_id] + args + [per_page, (max(page, 1) - 1) * per_page]).fetchall()
    return [Event(r) for r in rows], total


# ---------- organizer / admin numbers ----------
def counts_by_status(owner_id: int | None = None) -> dict:
    """{status: count} for statuses that have at least one event (all events, or one organizer's)."""
    sql, params = "SELECT status, COUNT(*) AS n FROM events", ()
    if owner_id is not None:
        sql, params = sql + " WHERE owner_id = ?", (owner_id,)
    return {r["status"]: r["n"] for r in get_db().execute(sql + " GROUP BY status", params)}


def pending_review(limit: int | None = None) -> list:
    """Events waiting for an admin, oldest submission first."""
    sql = _BASE + " WHERE e.status = 'pending' ORDER BY COALESCE(e.submitted_at, e.updated_at), e.id"
    params: tuple = ()
    if limit:
        sql, params = sql + " LIMIT ?", (limit,)
    return [Event(r) for r in get_db().execute(sql, params)]


def rejected_for(owner_id: int, limit: int = 5) -> list:
    """The organizer's rejected events (newest first) so the dashboard can show the reasons."""
    rows = get_db().execute(_BASE + " WHERE e.owner_id = ? AND e.status = 'rejected' ORDER BY e.reviewed_at DESC, e.id DESC LIMIT ?",
                            (owner_id, limit)).fetchall()
    return [Event(r) for r in rows]


def reviewed_list(decision: str, page: int = 1, per_page: int = 10):
    """Events whose CURRENT status is a finished decision: 'approved' (approved + completed) or 'rejected'.

    Returns (events, total), most recently reviewed first.
    """
    statuses = ("approved", "completed") if decision == "approved" else ("rejected",)
    marks = ",".join("?" * len(statuses))
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM events e WHERE e.status IN ({marks})", statuses).fetchone()[0]
    rows = db.execute(_BASE + f" WHERE e.status IN ({marks}) ORDER BY COALESCE(e.reviewed_at, e.updated_at) DESC, e.id DESC LIMIT ? OFFSET ?",
                      statuses + (per_page, (max(page, 1) - 1) * per_page)).fetchall()
    return [Event(r) for r in rows], total
