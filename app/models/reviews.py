"""Approve / reject history of events (one row per admin decision)."""
from app.db import get_db
from app.models.users import now_iso


def record(event_id: int, reviewer_id: int | None, decision: str, reason: str = "") -> None:
    db = get_db()
    db.execute("INSERT INTO event_reviews (event_id, reviewer_id, decision, reason, created_at) VALUES (?,?,?,?,?)",
               (event_id, reviewer_id, decision, reason, now_iso()))
    db.commit()


def for_event(event_id: int) -> list:
    """Newest first, with the reviewer's name."""
    return get_db().execute(
        "SELECT r.*, u.name AS reviewer_name FROM event_reviews r LEFT JOIN users u ON u.id = r.reviewer_id "
        "WHERE r.event_id = ? ORDER BY r.id DESC", (event_id,)).fetchall()
