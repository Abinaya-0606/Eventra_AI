"""In-app notifications. Every function is scoped to one user, so nobody can read another user's inbox."""
from app.db import get_db
from app.models.users import now_iso


def notify(user_id: int, kind: str, message: str, link: str = "") -> None:
    db = get_db()
    db.execute("INSERT INTO notifications (user_id, kind, message, link, created_at) VALUES (?,?,?,?,?)",
               (user_id, kind, message[:300], link, now_iso()))
    db.commit()


def notify_many(user_ids, kind: str, message: str, link: str = "") -> int:
    ids = sorted(set(user_ids))
    if ids:
        db = get_db()
        now = now_iso()
        db.executemany("INSERT INTO notifications (user_id, kind, message, link, created_at) VALUES (?,?,?,?,?)",
                       [(i, kind, message[:300], link, now) for i in ids])
        db.commit()
    return len(ids)


def notify_admins(kind: str, message: str, link: str = "", exclude_id: int | None = None) -> int:
    """Notify every active admin (except `exclude_id`, normally the person who caused it)."""
    rows = get_db().execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1").fetchall()
    return notify_many([r["id"] for r in rows if r["id"] != exclude_id], kind, message, link)


def unread_count(user_id: int) -> int:
    return get_db().execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,)).fetchone()[0]


def list_for(user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False):
    where = " AND is_read = 0" if unread_only else ""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ?" + where, (user_id,)).fetchone()[0]
    rows = db.execute("SELECT * FROM notifications WHERE user_id = ?" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                      (user_id, per_page, (page - 1) * per_page)).fetchall()
    return rows, total


def recent(user_id: int, limit: int = 5):
    return get_db().execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()


def mark_read(user_id: int, notification_id: int):
    """Mark one of THIS user's notifications read. Returns its row, or None if it is not theirs."""
    db = get_db()
    row = db.execute("SELECT * FROM notifications WHERE id = ? AND user_id = ?", (notification_id, user_id)).fetchone()
    if row:
        db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        db.commit()
    return row


def mark_all_read(user_id: int) -> None:
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))
    db.commit()
