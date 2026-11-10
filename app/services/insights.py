"""Deterministic (non-AI) calculations used by the Phase 4 features.

The AI writes explanations and suggestions. Everything that is a number, a comparison or a
rule is computed here, so it is repeatable and can be tested.
"""
from datetime import date

BUDGET_CATEGORIES = {
    "venue": "Venue", "food": "Food & refreshments", "decoration": "Decoration", "equipment": "Equipment",
    "guest": "Guests & speakers", "transportation": "Transportation", "emergency": "Emergency reserve",
}
FACILITIES = {
    "projector": "Projector", "sound": "Sound system", "mics": "Microphones", "ac": "Air conditioning",
    "stage": "Stage", "wifi": "Wi-Fi", "power_backup": "Power backup", "parking": "Parking",
    "wheelchair": "Wheelchair access", "green_room": "Green room",
}
LEVELS = {"low": 1, "medium": 2, "high": 3}


# ---------- budget ----------
def normalise_allocations(raw, budget: float) -> list[dict]:
    """Turn the AI's percentages into rupee amounts that never exceed the budget.

    - every category is present (missing ones become 0)
    - negative / non-numeric values become 0
    - if the percentages add up to more than 100, they are scaled down to exactly 100
    """
    pct = {c: 0.0 for c in BUDGET_CATEGORIES}
    notes = {c: "" for c in BUDGET_CATEGORIES}
    for row in raw if isinstance(raw, list) else []:
        if isinstance(row, dict) and row.get("category") in pct:
            try:
                value = float(str(row.get("percent", 0)).replace("%", "").strip())
            except ValueError:
                value = 0.0
            pct[row["category"]] = max(value, 0.0)
            notes[row["category"]] = str(row.get("note", "")).strip()[:200]
    total = sum(pct.values())
    if total > 100:
        pct = {c: v * 100 / total for c, v in pct.items()}
    items = [{"category": c, "label": BUDGET_CATEGORIES[c], "percent": round(pct[c], 1),
              "amount": round(budget * pct[c] / 100, 2), "note": notes[c]} for c in BUDGET_CATEGORIES]
    return items


def budget_summary(items: list[dict], budget: float) -> dict:
    total = round(sum(i["amount"] for i in items), 2)
    return {"budget": budget, "total": total, "remaining": round(budget - total, 2), "within_budget": total <= budget}


# ---------- venues ----------
def score_venues(venues, participants: int, budget: float, required: list[str]):
    """Split venues into (candidates, excluded). Candidates are sorted best first.

    Excluded = too small for the participants. Score favours: facilities covered, affordable cost,
    and a venue that is not far bigger than needed. Availability is NOT known and never assumed.
    """
    candidates, excluded = [], []
    for v in venues:
        if v.capacity < participants:
            excluded.append({"id": v.id, "name": v.name, "reason": f"Capacity {v.capacity} is below {participants} participants."})
            continue
        have = [f for f in required if f in v.facilities]
        missing = [f for f in required if f not in v.facilities]
        share = (v.cost_per_day / budget) if budget else 1.0
        fill = participants / v.capacity
        score = 40 * (len(have) / len(required) if required else 1) + 35 * max(0.0, 1 - share) + 25 * min(fill, 1.0)
        candidates.append({
            "id": v.id, "name": v.name, "capacity": v.capacity, "cost_per_day": v.cost_per_day,
            "facilities": [FACILITIES.get(f, f) for f in v.facilities],
            "missing_facilities": [FACILITIES.get(f, f) for f in missing],
            "fills_percent": round(fill * 100), "budget_share_percent": round(share * 100),
            "over_budget": v.cost_per_day > budget, "score": round(score, 1), "notes": v.notes,
        })
    candidates.sort(key=lambda c: -c["score"])
    return candidates, excluded


# ---------- facts and rule-based alerts ----------
def event_facts(event, tasks, schedule, budget_items: dict, venue, today: date | None = None) -> dict:
    today = today or date.today()
    days_until = (date.fromisoformat(event.event_date) - today).days
    open_tasks = [t for t in tasks if t.status != "done"]
    overdue = [t for t in open_tasks if t.deadline and t.deadline < today.isoformat()]
    return {
        "name": event.name, "type": event.event_type, "date": event.event_date, "days_until": days_until,
        "participants": event.participants, "budget": event.budget, "duration_hours": event.duration_hours,
        "budget_per_participant": round(event.budget / event.participants, 2),
        "venue": event.venue or "not chosen", "venue_capacity": venue.capacity if venue else None,
        "status": event.status, "description": event.description,
        "tasks_total": len(tasks), "tasks_open": len(open_tasks), "tasks_overdue": len(overdue),
        "schedule_items": len(schedule), "breakdown_total": round(sum(budget_items.values()), 2) if budget_items else None,
    }


def rule_alerts(f: dict) -> list[dict]:
    """Clear-cut warnings found by simple rules (no AI). Each: {level, title, detail}."""
    out = []

    def add(level, title, detail):
        out.append({"level": level, "title": title, "detail": detail})

    if f["venue_capacity"] is not None and f["participants"] > f["venue_capacity"]:
        add("high", "Venue capacity exceeded",
            f"{f['participants']} participants but {f['venue']} holds {f['venue_capacity']}.")
    if f["breakdown_total"] is not None and f["breakdown_total"] > f["budget"]:
        add("high", "Budget breakdown is over budget",
            f"Breakdown totals Rs. {f['breakdown_total']:,.0f} against a budget of Rs. {f['budget']:,.0f}.")
    if f["budget_per_participant"] < 100:
        add("medium", "Very low budget per participant", f"Only Rs. {f['budget_per_participant']:,.0f} per participant.")
    if 0 <= f["days_until"] <= 7 and f["tasks_open"]:
        add("high" if f["days_until"] <= 3 else "medium", "Event is close and tasks are still open",
            f"{f['tasks_open']} open task(s) with {f['days_until']} day(s) to go.")
    if f["tasks_overdue"]:
        add("medium", "Overdue tasks", f"{f['tasks_overdue']} task(s) are past their deadline.")
    if f["tasks_total"] == 0:
        add("medium", "No tasks planned", "Nobody has been given any preparation work yet.")
    if f["schedule_items"] == 0:
        add("medium", "No schedule saved", "Participants and volunteers have no timetable to follow.")
    if f["days_until"] < 0 and f["status"] not in ("completed", "rejected"):
        add("low", "Event date has passed", "Mark the event as completed or update its date.")
    return out


def risk_level(alerts: list[dict], ai_risks: list[dict]) -> str:
    """Overall level: highest severity found by rules or AI."""
    levels = [LEVELS[a["level"]] for a in alerts] + [LEVELS[r["severity"]] for r in ai_risks]
    top = max(levels, default=1)
    return {1: "low", 2: "medium", 3: "high"}[top]


def severity(likelihood: str, impact: str) -> str:
    score = LEVELS[likelihood] * LEVELS[impact]
    return "high" if score >= 6 else "medium" if score >= 3 else "low"
