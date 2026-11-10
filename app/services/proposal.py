"""Builds the full proposal (AI text + live schedule and budget from the database)."""
from app.services.insights import BUDGET_CATEGORIES


def _time_label(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h % 12 or 12:02d}:{m:02d} {'AM' if h < 12 else 'PM'}"


def build_view(event, organizer, content: dict, schedule_rows, budget_items: dict, college: str = "") -> dict:
    """Everything needed to show or print the proposal. Schedule and budget are facts from the database, never AI text."""
    if budget_items:
        lines = [{"label": BUDGET_CATEGORIES[c], "amount": budget_items[c]} for c in BUDGET_CATEGORIES if budget_items.get(c)]
        total, source = round(sum(budget_items.values()), 2), "breakdown"
    else:
        lines, total, source = [{"label": "Total estimated budget", "amount": event.budget}], event.budget, "event_budget"
    return {
        "cover": {"title": event.name, "event_type": event.event_type, "date": event.event_date,
                  "start_time": event.start_time, "venue": event.venue or "To be confirmed",
                  "participants": event.participants, "duration_hours": event.duration_hours,
                  "organizer": organizer.name, "department": organizer.department, "college": college,
                  "status": event.status},
        "introduction": content["introduction"], "objectives": content["objectives"], "description": content["description"],
        "target_participants": content["target_participants"],
        "schedule": [{"time_label": _time_label(r["start_time"]), "title": r["title"], "description": r["description"]}
                     for r in schedule_rows],
        "budget": {"lines": lines, "total": total, "source": source},
        "required_resources": content["required_resources"], "committee": content["committee"],
        "expected_outcomes": content["expected_outcomes"], "updated_at": content.get("updated_at", ""),
    }
