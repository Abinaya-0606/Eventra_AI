"""Activity feed ("Recent activities" on the dashboard)."""
from app.db import get_db
from app.models.users import now_iso


def log(actor, message: str, owner_id: int, event_id=None) -> None:
    """Record something `actor` did. It shows in the feed of the event's owner (and of the actor)."""
    db = get_db()
    db.execute("INSERT INTO activities (user_id, owner_id, event_id, message, created_at) VALUES (?,?,?,?,?)",
               (actor.id, owner_id, event_id, message, now_iso()))
    db.commit()


def recent(user, limit: int = 8) -> list:
    if user.is_admin:
        sql, params = "SELECT a.*, u.name AS actor_name FROM activities a LEFT JOIN users u ON u.id = a.user_id ORDER BY a.id DESC LIMIT ?", (limit,)
    else:
        sql = ("SELECT a.*, u.name AS actor_name FROM activities a LEFT JOIN users u ON u.id = a.user_id "
               "WHERE a.owner_id = ? OR a.user_id = ? ORDER BY a.id DESC LIMIT ?")
        params = (user.id, user.id, limit)
    return get_db().execute(sql, params).fetchall()


def log_admin(actor, message: str) -> None:
    """Platform-level action (user or venue management). Shows in the admin's own feed and in the activity log."""
    log(actor, message, actor.id)


def search(q: str = "", page: int = 1, per_page: int = 25):
    """Admin activity log: (rows, total). Searches the action text and the person's name."""
    where, args = "", []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where = " WHERE (a.message LIKE ? ESCAPE '\\' OR u.name LIKE ? ESCAPE '\\')"
        args = [like, like]
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM activities a LEFT JOIN users u ON u.id = a.user_id" + where, args).fetchone()[0]
    rows = db.execute("SELECT a.*, u.name AS actor_name, u.role AS actor_role FROM activities a "
                      "LEFT JOIN users u ON u.id = a.user_id" + where + " ORDER BY a.id DESC LIMIT ? OFFSET ?",
                      args + [per_page, (max(page, 1) - 1) * per_page]).fetchall()
    return rows, total
