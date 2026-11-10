
from flask import Response, abort, current_app, g, jsonify, render_template, request

from app.blueprints.planning import bp
from app.models import activity, events, tasks
from app.models import planning as store
from app.services import ai_features as features
from app.services import events_logic as rules
from app.services import insights, pdf, proposal
from app.services.llm import LLMError
from app.services.validation import ValidationError, clean_amount, clean_language


def _load(event_id: int):
    """The event if this user may see it, otherwise 404 (we do not reveal that it exists)."""
    event = events.get(event_id)
    if event is None or not rules.can_view(g.user, event):
        abort(404)
    return event


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send the details as JSON.")
    return data


def _venue_for(event):
    return store.find_venue_by_name(event.venue) if event.venue else None


def _facts(event):
    return insights.event_facts(event, tasks.for_event(event.id), events.get_schedule(event.id),
                                store.get_budget_items(event.id), _venue_for(event))


def _proposal_view(event, content):
    return proposal.build_view(event, g.user if g.user.id == event.owner_id else _owner(event), content,
                               events.get_schedule(event.id), store.get_budget_items(event.id),
                               current_app.config.get("COLLEGE_NAME", ""))


def _owner(event):
    from app.models import users
    return users.get_by_id(event.owner_id)


def _run(event_id: int, work):
    """Shared flow for every generator: only the owner may generate; errors become JSON."""
    event = _load(event_id)
    if not rules.can_manage_content(g.user, event):
        return jsonify({"error": "Only the organizer can use AI tools on this event, and not after it is completed."}), 403
    try:
        data = _json_body() if request.data else {}
        return jsonify(work(event, data, clean_language(data)))
    except ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    except LLMError as exc:
        return jsonify({"error": exc.message}), exc.status


# ---------- page ----------
@bp.get("/events/<int:event_id>/ai")
def tools(event_id):
    event = _load(event_id)
    saved = store.get_results(event_id)
    items = store.get_budget_items(event_id)
    content = store.get_proposal(event_id)
    alerts = insights.rule_alerts(_facts(event))
    state = {
        "eventId": event.id, "budget": event.budget,
        "canGenerate": rules.can_manage_content(g.user, event),
        "budgetItems": items or None,
        "venues": saved.get("venues"), "risks": saved.get("risks"), "improve": saved.get("improve"),
        "proposal": _proposal_view(event, content) if content else None,
        "alerts": alerts, "overall": insights.risk_level(alerts, []),
        "categories": [[key, label] for key, label in insights.BUDGET_CATEGORIES.items()],  # a list: JSON object keys get re-sorted
    }
    return render_template("planning/tools.html", event=event, state=state, facilities=insights.FACILITIES,
                           can_generate=state["canGenerate"], has_proposal=content is not None)


# ---------- budget ----------
@bp.post("/api/events/<int:event_id>/ai/budget")
def ai_budget(event_id):
    def work(event, data, language):
        venue = _venue_for(event)
        params = {"event_type": event.event_type, "participants": event.participants, "budget": event.budget,
                  "duration_hours": event.duration_hours, "venue": event.venue, "description": event.description,
                  "venue_cost": venue.cost_per_day if venue else None}
        result = features.generate_budget(params, language)
        activity.log(g.user, f'Generated a budget suggestion for "{event.name}"', event.owner_id, event.id)
        return result
    return _run(event_id, work)


@bp.post("/api/events/<int:event_id>/budget")
def save_budget(event_id):
    event = _load(event_id)
    if not rules.can_manage_content(g.user, event):
        return jsonify({"error": "You cannot change this event."}), 403
    try:
        data = _json_body()
        raw = data.get("items")
        if not isinstance(raw, dict):
            raise ValidationError("Send the budget items as an object.")
        items = {c: clean_amount(raw, c, label, max_value=100_000_000) if c in raw else 0.0
                 for c, label in insights.BUDGET_CATEGORIES.items()}
    except ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    store.replace_budget_items(event_id, items)
    activity.log(g.user, f'Saved the budget breakdown of "{event.name}"', event.owner_id, event_id)
    return jsonify({"saved": True, **insights.budget_summary(
        [{"amount": a} for a in items.values()], event.budget)})


# ---------- venues ----------
@bp.post("/api/events/<int:event_id>/ai/venues")
def ai_venues(event_id):
    def work(event, data, language):
        required = data.get("facilities", [])
        if not isinstance(required, list) or any(f not in insights.FACILITIES for f in required):
            raise ValidationError("Choose facilities from the list.", "facilities")
        required = list(dict.fromkeys(required))
        candidates, excluded = insights.score_venues(store.list_venues(), event.participants, event.budget, required)
        result = features.generate_venues(_facts(event), candidates, excluded, required, language)
        store.save_result(event.id, "venues", result)
        activity.log(g.user, f'Ran venue recommendation for "{event.name}"', event.owner_id, event.id)
        return result
    return _run(event_id, work)


# ---------- risks / improvements ----------
@bp.post("/api/events/<int:event_id>/ai/risks")
def ai_risks(event_id):
    def work(event, data, language):
        facts = _facts(event)
        result = features.generate_risks(facts, insights.rule_alerts(facts), language)
        store.save_result(event.id, "risks", result)
        activity.log(g.user, f'Ran risk analysis for "{event.name}"', event.owner_id, event.id)
        return result
    return _run(event_id, work)


@bp.post("/api/events/<int:event_id>/ai/improve")
def ai_improve(event_id):
    def work(event, data, language):
        result = features.generate_improvements(_facts(event), language)
        store.save_result(event.id, "improve", result)
        activity.log(g.user, f'Generated improvement suggestions for "{event.name}"', event.owner_id, event.id)
        return result
    return _run(event_id, work)


# ---------- proposal ----------
@bp.post("/api/events/<int:event_id>/ai/proposal")
def ai_proposal(event_id):
    def work(event, data, language):
        content = features.generate_proposal_text(_facts(event), {"organizer": g.user.name, "department": g.user.department})
        store.save_proposal(event.id, content)
        activity.log(g.user, f'Generated a proposal for "{event.name}"', event.owner_id, event.id)
        return _proposal_view(event, store.get_proposal(event.id))
    return _run(event_id, work)


@bp.get("/events/<int:event_id>/proposal.pdf")
def proposal_pdf(event_id):
    event = _load(event_id)
    content = store.get_proposal(event_id)
    if content is None:
        abort(404)
    data = pdf.build_proposal_pdf(_proposal_view(event, content))
    name = "".join(ch if ch.isalnum() else "-" for ch in event.name).strip("-").lower() or "event"
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="proposal-{name[:40]}.pdf"'})
