"""Tasks belong to an event and can be assigned to a user."""
from app.db import get_db
from app.models.users import now_iso

_BASE = """SELECT t.*, e.name AS event_name, e.owner_id AS event_owner_id, a.name AS assignee_name
    FROM tasks t JOIN events e ON e.id = t.event_id LEFT JOIN users a ON a.id = t.assignee_id"""


class Task:
    def __init__(self, row):
        for key in row.keys():
            setattr(self, key, row[key])


def _all(rows) -> list[Task]:
    return [Task(r) for r in rows]


def get(task_id: int):
    row = get_db().execute(_BASE + " WHERE t.id = ?", (task_id,)).fetchone()
    return Task(row) if row else None


def create(event_id: int, title: str, assignee_id, deadline, phase=None) -> int:
    db = get_db()
    cur = db.execute("INSERT INTO tasks (event_id, title, assignee_id, deadline, phase, created_at) VALUES (?,?,?,?,?,?)",
                     (event_id, title, assignee_id, deadline or None, phase, now_iso()))
    db.commit()
    return cur.lastrowid


def create_many(event_id: int, rows: list[tuple]) -> None:
    """rows: (title, assignee_id, phase)"""
    db = get_db()
    now = now_iso()
    db.executemany("INSERT INTO tasks (event_id, title, assignee_id, phase, created_at) VALUES (?,?,?,?,?)",
                   [(event_id, t, a, p, now) for t, a, p in rows])
    db.commit()


def update(task_id: int, title: str, assignee_id, deadline) -> None:
    db = get_db()
    db.execute("UPDATE tasks SET title = ?, assignee_id = ?, deadline = ? WHERE id = ?",
               (title, assignee_id, deadline or None, task_id))
    db.commit()


def set_status(task_id: int, status: str) -> None:
    db = get_db()
    db.execute("UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
               (status, now_iso() if status == "done" else None, task_id))
    db.commit()


def delete(task_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()


def for_event(event_id: int) -> list[Task]:
    return _all(get_db().execute(
        _BASE + " WHERE t.event_id = ? ORDER BY t.status = 'done', t.deadline IS NULL, t.deadline, t.id", (event_id,)))


def _scope(user):
    """Admins see all tasks; others see tasks on their own events or assigned to them."""
    return ("", ()) if user.is_admin else (" WHERE (e.owner_id = ? OR t.assignee_id = ?)", (user.id, user.id))


def list_for_user(user, status: str = "", page: int = 1, per_page: int = 20, q: str = ""):
    where, params = _scope(user)
    args = list(params)
    if status:
        where = (where + " AND" if where else " WHERE") + " t.status = ?"
        args.append(status)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where = (where + " AND" if where else " WHERE") + " (t.title LIKE ? ESCAPE '\\' OR e.name LIKE ? ESCAPE '\\')"
        args += [like, like]
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM tasks t JOIN events e ON e.id = t.event_id" + where, args).fetchone()[0]
    rows = db.execute(_BASE + where + " ORDER BY t.status = 'done', t.deadline IS NULL, t.deadline, t.id LIMIT ? OFFSET ?",
                      args + [per_page, (page - 1) * per_page]).fetchall()
    return _all(rows), total


def pending_count(user) -> int:
    where, params = _scope(user)
    where = (where + " AND" if where else " WHERE") + " t.status != 'done'"
    return get_db().execute("SELECT COUNT(*) FROM tasks t JOIN events e ON e.id = t.event_id" + where, params).fetchone()[0]


def pending_list(user, limit: int = 5) -> list[Task]:
    where, params = _scope(user)
    where = (where + " AND" if where else " WHERE") + " t.status != 'done'"
    return _all(get_db().execute(_BASE + where + " ORDER BY t.deadline IS NULL, t.deadline, t.id LIMIT ?", params + (limit,)))
