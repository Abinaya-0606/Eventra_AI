import re

from flask import jsonify, render_template, request

from app.blueprints.budget import bp
from app.services.budget_tools import VENUES, estimate_event_budget


def _to_bool(value):
    """Accept real booleans only; map the strings 'true'/'false'. Anything else stays invalid."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return value


def _to_participants(value):
    """JSON numbers stay as-is; digit-only strings (from a text box) become int."""
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d+", text):
            return int(text)
        return text if text else None
    return value


@bp.get("/budget")
def calculator():
    venues = {k: {"label": v["label"], "capacity": v["capacity"], "cost": float(v["cost"])}
              for k, v in VENUES.items()}
    return render_template("budget/calculator.html", venues=venues)


@bp.post("/api/budget")
def budget():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send the budget details as JSON."}), 400
    result = estimate_event_budget(
        data.get("venue"),
        _to_participants(data.get("participants")),
        _to_bool(data.get("refreshments")),
        _to_bool(data.get("participation_kits")),
    )
    return jsonify(result), (400 if "error" in result else 200)
