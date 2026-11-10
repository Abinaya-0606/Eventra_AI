"""Phase 1 AI features. Each function: build prompt -> call Groq -> check and shape the result.

The AI writes the content. Python checks the structure and does ALL arithmetic
(totals, remaining budget) and time formatting, so numbers are never trusted from the model.
"""
from datetime import datetime

from app.services import llm, prompts
from app.services.validation import LETTER_RECIPIENTS


def _bad(message="The AI returned an incomplete answer. Please click Generate again."):
    return llm.LLMError(message, 502)


def _str_list(value, minimum=1, limit=20) -> list[str]:
    if not isinstance(value, list):
        raise _bad()
    items = [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
    if len(items) < minimum:
        raise _bad()
    return items[:limit]


def _number(value) -> float:
    try:
        number = float(str(value).replace(",", "").replace("₹", "").replace("INR", "").strip())
    except ValueError:
        return 0.0
    return round(number, 2) if number >= 0 else 0.0


# ---------- A. event planner ----------
def generate_plan(p: dict, language: str) -> dict:
    data = llm.complete_json(*prompts.plan(p), language=language, max_tokens=3000)
    team = [{"role": str(t.get("role", "")).strip(), "responsibilities": str(t.get("responsibilities", "")).strip()}
            for t in data.get("team", []) if isinstance(t, dict) and str(t.get("role", "")).strip()]
    expenses = [{"item": str(e.get("item", "")).strip(), "amount": _number(e.get("amount"))}
                for e in data.get("expenses", []) if isinstance(e, dict) and str(e.get("item", "")).strip()]
    if not team or not expenses:
        raise _bad()
    total = round(sum(e["amount"] for e in expenses), 2)
    return {
        "objectives": _str_list(data.get("objectives")),
        "arrangements": _str_list(data.get("arrangements")),
        "equipment": _str_list(data.get("equipment")),
        "team": team[:12],
        "expenses": expenses[:20],
        "preparation": _str_list(data.get("preparation")),
        # computed in Python, never by the model
        "estimated_total": total,
        "budget": p["budget"],
        "remaining_budget": round(p["budget"] - total, 2),
        "within_budget": total <= p["budget"],
    }


# ---------- B. names ----------
def generate_names(p: dict, language: str) -> dict:
    data = llm.complete_json(*prompts.names(p), language=language, temperature=0.9, max_tokens=1200)
    items = []
    for n in data.get("names", []):
        if isinstance(n, dict) and str(n.get("name", "")).strip():
            items.append({"name": str(n["name"]).strip(), "tagline": str(n.get("tagline", "")).strip()})
        elif isinstance(n, str) and n.strip():
            items.append({"name": n.strip(), "tagline": ""})
    if not items:
        raise _bad()
    return {"names": items[:p["count"]]}


# ---------- C. description ----------
def generate_description(p: dict, language: str) -> dict:
    data = llm.complete_json(*prompts.description(p), language=language, temperature=0.7)
    result = {k: str(data.get(k, "")).strip() for k in ("tagline", "short_description", "full_description")}
    if not result["short_description"] or not result["full_description"]:
        raise _bad()
    return result


# ---------- D. schedule ----------
def format_time(hhmm: str) -> str:
    return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p")


def _parse_time(value) -> str | None:
    """Accept '09:00', '9:00', '9:00 AM', '09:00 AM' and return 24h 'HH:MM' (or None)."""
    text = str(value).strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p", "%I %p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def generate_schedule(p: dict, language: str) -> dict:
    data = llm.complete_json(*prompts.schedule(p), language=language, temperature=0.4)
    items = []
    for row in data.get("items", []):
        if not isinstance(row, dict) or not str(row.get("title", "")).strip():
            continue
        t = _parse_time(row.get("time"))
        if t:
            items.append({"time": t, "title": str(row["title"]).strip(),
                          "description": str(row.get("description", "")).strip()})
    if len(items) < 3:
        raise _bad()
    items.sort(key=lambda r: r["time"])  # the display is always in time order
    for r in items:
        r["time_label"] = format_time(r["time"])
    return {"items": items[:20]}


# ---------- E. checklist ----------
def generate_checklist(p: dict, language: str) -> dict:
    data = llm.complete_json(*prompts.checklist(p), language=language, temperature=0.4)
    return {phase: _str_list(data.get(phase), limit=12) for phase in ("before", "during", "after")}


# ---------- F. permission letter ----------
def generate_letter(p: dict, language: str) -> dict:
    p = {**p, "recipient_label": LETTER_RECIPIENTS[p["recipient"]],
         "today": datetime.now().strftime("%d %B %Y")}
    data = llm.complete_json(*prompts.letter(p), language=language, temperature=0.3)
    subject, body = str(data.get("subject", "")).strip(), str(data.get("body", "")).strip()
    if not subject or len(body) < 40:
        raise _bad()
    return {"subject": subject, "body": body, "recipient": p["recipient"]}


# =====================================================================
# Phase 4
# =====================================================================
from app.services import insights  # noqa: E402


def generate_budget(p: dict, language: str) -> dict:
    """AI proposes percentages; Python turns them into amounts and the totals."""
    data = llm.complete_json(*prompts.budget(p), language=language, temperature=0.3)
    items = insights.normalise_allocations(data.get("allocations"), p["budget"])
    if not any(i["amount"] for i in items):
        raise _bad()
    return {"items": items, **insights.budget_summary(items, p["budget"])}


def generate_venues(facts: dict, candidates: list, excluded: list, required: list[str], language: str) -> dict:
    """Rank venues taken from the database. The AI cannot add venues: unknown ids are ignored."""
    note = "Availability is not checked. Confirm the date with the venue administrator."
    if not candidates:
        return {"recommendations": [], "excluded": excluded, "disclaimer": note,
                "message": "No venue in the college list can hold this many participants."}
    data = llm.complete_json(*prompts.venues(facts, candidates, required), language=language, temperature=0.3)
    by_id = {c["id"]: dict(c, reason="", tip="") for c in candidates}
    ordered = []
    for row in data.get("ranking", []):
        try:
            vid = int(row.get("id"))
        except (TypeError, ValueError, AttributeError):
            continue
        if vid in by_id and by_id[vid] not in ordered:
            by_id[vid]["reason"] = str(row.get("reason", "")).strip()
            by_id[vid]["tip"] = str(row.get("tip", "")).strip()
            ordered.append(by_id[vid])
    ordered += [c for c in by_id.values() if c not in ordered]  # anything the AI skipped keeps its computed order
    return {"recommendations": ordered, "excluded": excluded, "disclaimer": note, "message": ""}


def generate_risks(facts: dict, alerts: list, language: str) -> dict:
    data = llm.complete_json(*prompts.risks(facts, alerts), language=language, temperature=0.4)
    risks = []
    for r in data.get("risks", []):
        if not isinstance(r, dict) or not str(r.get("title", "")).strip():
            continue
        like, impact = str(r.get("likelihood", "")).lower(), str(r.get("impact", "")).lower()
        if like not in insights.LEVELS or impact not in insights.LEVELS:
            like, impact = "medium", "medium"
        risks.append({"category": str(r.get("category", "other")).lower()[:20], "title": str(r["title"]).strip(),
                      "likelihood": like, "impact": impact, "severity": insights.severity(like, impact),
                      "prevention": str(r.get("prevention", "")).strip()})
    if not risks:
        raise _bad()
    risks.sort(key=lambda r: -(insights.LEVELS[r["likelihood"]] * insights.LEVELS[r["impact"]]))
    return {"alerts": alerts, "risks": risks[:10], "overall": insights.risk_level(alerts, risks)}


def generate_improvements(facts: dict, language: str) -> dict:
    data = llm.complete_json(*prompts.improve(facts), language=language, temperature=0.6)
    items = [{"area": str(s.get("area", "General")).strip(), "suggestion": str(s["suggestion"]).strip(),
              "benefit": str(s.get("benefit", "")).strip()}
             for s in data.get("suggestions", []) if isinstance(s, dict) and str(s.get("suggestion", "")).strip()]
    if not items:
        raise _bad()
    return {"suggestions": items[:10]}


def generate_proposal_text(facts: dict, organizer: dict) -> dict:
    """The proposal PDF is English only (no Tamil font is bundled)."""
    data = llm.complete_json(*prompts.proposal(facts, organizer), language="en", temperature=0.4, max_tokens=3000)
    committee = [{"role": str(c.get("role", "")).strip(), "responsibilities": str(c.get("responsibilities", "")).strip()}
                 for c in data.get("committee", []) if isinstance(c, dict) and str(c.get("role", "")).strip()]
    out = {
        "introduction": str(data.get("introduction", "")).strip(),
        "objectives": _str_list(data.get("objectives")),
        "description": str(data.get("description", "")).strip(),
        "target_participants": str(data.get("target_participants", "")).strip(),
        "required_resources": _str_list(data.get("required_resources")),
        "committee": committee[:12],
        "expected_outcomes": _str_list(data.get("expected_outcomes")),
    }
    if not (out["introduction"] and out["description"] and out["target_participants"] and committee):
        raise _bad()
    return out
