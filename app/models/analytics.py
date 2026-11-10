"""Read-only numbers for the analytics dashboard and PDF reports.

Everything is scoped like the rest of the app: admins see all events, everyone else only their own.
Rejected events are left out of money and participant totals (same rule as the dashboard).
Every query is for one calendar year of event_date.
"""
import calendar
from datetime import date

from app.db import get_db
from app.services.events_logic import STATUSES, STATUS_LABELS
from app.services.insights import BUDGET_CATEGORIES

MONTHS = [calendar.month_abbr[m] for m in range(1, 13)]


def _where(user, year: int, extra: str = ""):
    sql = " WHERE substr(e.event_date, 1, 4) = ?" + extra
    params = [f"{year:04d}"]
    if not user.is_admin:
        sql += " AND e.owner_id = ?"
        params.append(user.id)
    return sql, params


def years(user) -> list[int]:
    """Years that have events (newest first), always including the current year."""
    sql, params = ("", ()) if user.is_admin else (" WHERE e.owner_id = ?", (user.id,))
    rows = get_db().execute("SELECT DISTINCT substr(e.event_date, 1, 4) AS y FROM events e" + sql, params)
    found = {int(r["y"]) for r in rows} | {date.today().year}
    return sorted(found, reverse=True)


def summary(user, year: int) -> dict:
    db = get_db()
    where, p = _where(user, year)
    live, lp = _where(user, year, " AND e.status != 'rejected'")

    row = db.execute("SELECT COUNT(*) AS total FROM events e" + where, p).fetchone()
    by_status = {r["status"]: r["n"] for r in db.execute("SELECT e.status, COUNT(*) AS n FROM events e" + where + " GROUP BY e.status", p)}
    money = db.execute("SELECT COALESCE(SUM(e.budget), 0) AS budget, COALESCE(SUM(e.participants), 0) AS people FROM events e" + live, lp).fetchone()

    monthly = [{"month": MONTHS[i], "events": 0, "budget": 0.0} for i in range(12)]
    for r in db.execute("SELECT CAST(substr(e.event_date, 6, 2) AS INTEGER) AS m, COUNT(*) AS n, "
                        "COALESCE(SUM(CASE WHEN e.status != 'rejected' THEN e.budget END), 0) AS b FROM events e" + where + " GROUP BY m", p):
        monthly[r["m"] - 1].update(events=r["n"], budget=round(r["b"], 2))

    types = [{"label": r["event_type"], "count": r["n"]} for r in db.execute(
        "SELECT e.event_type, COUNT(*) AS n FROM events e" + where + " GROUP BY e.event_type ORDER BY n DESC, e.event_type", p)]

    # planned = saved budget breakdown (if any) against the event's estimated budget
    comparison = [{"name": r["name"], "budget": r["budget"], "planned": r["planned"]} for r in db.execute(
        "SELECT e.name, e.budget, (SELECT SUM(b.amount) FROM event_budget_items b WHERE b.event_id = e.id) AS planned "
        "FROM events e" + live + " ORDER BY e.budget DESC, e.id LIMIT 8", lp)]

    cats = {r["category"]: r["t"] for r in db.execute(
        "SELECT b.category, SUM(b.amount) AS t FROM event_budget_items b JOIN events e ON e.id = b.event_id" + live + " GROUP BY b.category", lp)}
    categories = [{"key": k, "label": label, "amount": round(cats.get(k, 0.0), 2)} for k, label in BUDGET_CATEGORIES.items()]

    t = {r["status"]: r["n"] for r in db.execute(
        "SELECT t.status, COUNT(*) AS n FROM tasks t JOIN events e ON e.id = t.event_id" + where + " GROUP BY t.status", p)}

    total_budget = round(money["budget"], 2)
    return {
        "year": year,
        "totals": {"events": row["total"], "completed": by_status.get("completed", 0), "pending": by_status.get("pending", 0),
                   "approved": by_status.get("approved", 0), "budget": total_budget, "participants": money["people"],
                   "average_budget": round(total_budget / max(row["total"] - by_status.get("rejected", 0), 1), 2) if row["total"] else 0.0,
                   "planned": round(sum(c["amount"] for c in categories), 2)},
        "status": [{"key": s, "label": STATUS_LABELS[s], "count": by_status.get(s, 0)} for s in STATUSES],
        "monthly": monthly, "types": types, "comparison": comparison, "categories": categories,
        "tasks": {"todo": t.get("todo", 0), "in_progress": t.get("in_progress", 0), "done": t.get("done", 0)},
    }
