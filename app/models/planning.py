"""Venues, budget breakdowns, saved AI results and proposals."""
import json

from app.db import get_db
from app.models.users import now_iso


# ---------- venues ----------
class Venue:
    def __init__(self, row):
        self.id, self.name, self.capacity = row["id"], row["name"], row["capacity"]
        self.cost_per_day, self.notes, self.is_active = row["cost_per_day"], row["notes"], bool(row["is_active"])
        self.facilities = [f for f in row["facilities"].split(",") if f]


def list_venues(active_only: bool = True) -> list[Venue]:
    sql = "SELECT * FROM venues" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY name"
    return [Venue(r) for r in get_db().execute(sql)]


def get_venue(venue_id: int):
    row = get_db().execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
    return Venue(row) if row else None


def find_venue_by_name(name: str):
    row = get_db().execute("SELECT * FROM venues WHERE name = ?", (name.strip(),)).fetchone()
    return Venue(row) if row else None


def save_venue(venue_id, name, capacity, cost, facilities, notes) -> int:
    """Insert (venue_id None) or update. Raises sqlite3.IntegrityError if the name is already used."""
    db = get_db()
    fac = ",".join(facilities)
    if venue_id is None:
        cur = db.execute("INSERT INTO venues (name, capacity, cost_per_day, facilities, notes) VALUES (?,?,?,?,?)",
                         (name, capacity, cost, fac, notes))
        venue_id = cur.lastrowid
    else:
        db.execute("UPDATE venues SET name=?, capacity=?, cost_per_day=?, facilities=?, notes=? WHERE id=?",
                   (name, capacity, cost, fac, notes, venue_id))
    db.commit()
    return venue_id


def set_venue_active(venue_id: int, active: bool) -> None:
    db = get_db()
    db.execute("UPDATE venues SET is_active = ? WHERE id = ?", (int(active), venue_id))
    db.commit()


# ---------- budget breakdown ----------
def get_budget_items(event_id: int) -> dict[str, float]:
    rows = get_db().execute("SELECT category, amount FROM event_budget_items WHERE event_id = ?", (event_id,))
    return {r["category"]: r["amount"] for r in rows}


def replace_budget_items(event_id: int, items: dict[str, float]) -> None:
    db = get_db()
    db.execute("DELETE FROM event_budget_items WHERE event_id = ?", (event_id,))
    db.executemany("INSERT INTO event_budget_items (event_id, category, amount) VALUES (?,?,?)",
                   [(event_id, c, a) for c, a in items.items()])
    db.commit()


# ---------- saved AI results ----------
def save_result(event_id: int, kind: str, content: dict) -> None:
    db = get_db()
    db.execute("INSERT INTO ai_results (event_id, kind, content, created_at) VALUES (?,?,?,?) "
               "ON CONFLICT(event_id, kind) DO UPDATE SET content = excluded.content, created_at = excluded.created_at",
               (event_id, kind, json.dumps(content, ensure_ascii=False), now_iso()))
    db.commit()


def get_results(event_id: int) -> dict[str, dict]:
    rows = get_db().execute("SELECT kind, content, created_at FROM ai_results WHERE event_id = ?", (event_id,))
    return {r["kind"]: {**json.loads(r["content"]), "created_at": r["created_at"]} for r in rows}


# ---------- proposal ----------
def save_proposal(event_id: int, content: dict) -> None:
    now = now_iso()
    db = get_db()
    db.execute("INSERT INTO proposals (event_id, content, created_at, updated_at) VALUES (?,?,?,?) "
               "ON CONFLICT(event_id) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
               (event_id, json.dumps(content, ensure_ascii=False), now, now))
    db.commit()


def get_proposal(event_id: int):
    row = get_db().execute("SELECT * FROM proposals WHERE event_id = ?", (event_id,)).fetchone()
    return {**json.loads(row["content"]), "updated_at": row["updated_at"]} if row else None
