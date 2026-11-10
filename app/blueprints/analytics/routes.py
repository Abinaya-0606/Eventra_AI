from datetime import date, datetime

from flask import Response, abort, g, render_template, request

from app.blueprints.analytics import bp
from app.models import analytics, events, tasks
from app.models import planning as store
from app.services import events_logic as rules
from app.services import insights, pdf
from app.services.events_logic import TASK_LABELS
from app.services.insights import BUDGET_CATEGORIES


def _year() -> int:
    """?year=YYYY, falling back to this year for anything missing or silly."""
    value = request.args.get("year", type=int)
    return value if value and 2000 <= value <= 2100 else date.today().year


def _pdf_response(data: bytes, name: str) -> Response:
    safe = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-").lower()[:50] or "report"
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'})


@bp.get("/analytics")
def dashboard():
    year = _year()
    data = analytics.summary(g.user, year)
    return render_template("analytics/dashboard.html", data=data, years=analytics.years(g.user), year=year,
                           scope="all organizers" if g.user.is_admin else "your events")


@bp.get("/analytics/report.pdf")
def report_pdf():
    year = _year()
    data = analytics.summary(g.user, year)
    scope = "All organizers' events" if g.user.is_admin else "Your events only"
    return _pdf_response(pdf.build_analytics_pdf(data, g.user.name, date.today().strftime("%d %b %Y"), scope),
                         f"analytics-report-{year}")


@bp.get("/events/<int:event_id>/report.pdf")
def event_report_pdf(event_id):
    event = events.get(event_id)
    if event is None or not rules.can_view(g.user, event):
        abort(404)
    items = store.get_budget_items(event_id)
    saved = store.get_results(event_id).get("risks") or {}
    report = {
        "event": event, "owner": event.owner_name, "generated": datetime.now().strftime("%d %b %Y"),
        "schedule": [(_time(r["start_time"]), r["title"], r["description"]) for r in events.get_schedule(event_id)],
        "budget": {BUDGET_CATEGORIES[c]: items[c] for c in BUDGET_CATEGORIES if items.get(c)},
        "tasks": [(t.title, t.assignee_name, TASK_LABELS[t.status], t.deadline) for t in tasks.for_event(event_id)],
        "alerts": insights.rule_alerts(insights.event_facts(event, tasks.for_event(event_id), events.get_schedule(event_id),
                                                            items, store.find_venue_by_name(event.venue) if event.venue else None)),
        "risks": saved.get("risks", []),
    }
    return _pdf_response(pdf.build_event_report_pdf(report), f"report-{event.name}")


def _time(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h % 12 or 12:02d}:{m:02d} {'AM' if h < 12 else 'PM'}"
