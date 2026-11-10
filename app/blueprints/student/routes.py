from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from app.blueprints.student import bp
from app.models import events, registrations
from app.security import role_required, safe_next
from app.services import events_logic as rules
from app.services import workflow
from app.services.validation import EVENT_TYPES, ValidationError, clean_date

PER_PAGE = 9


def _approved_or_404(event_id: int):
    """Students only ever see approved events; anything else answers 404 (its existence is not revealed)."""
    event = events.get(event_id)
    if event is None or event.status != "approved":
        abort(404)
    return event


@bp.get("/browse")
def browse():
    q = (request.args.get("q") or "").strip()[:100]
    etype = request.args.get("type", "")
    etype = etype if etype in EVENT_TYPES else ""
    error = None
    try:
        date_from = clean_date(request.args, "from", "From date")
        date_to = clean_date(request.args, "to", "To date")
    except ValidationError as exc:
        date_from = date_to = ""
        error = exc.message
    open_only = request.args.get("open") == "1"
    include_past = request.args.get("past") == "1"
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    items, total = events.browse(g.user.id, q, etype, date_from, date_to, open_only, include_past, page, PER_PAGE)
    return render_template("student/browse.html", events=items, total=total, page=page,
                           pages=max((total + PER_PAGE - 1) // PER_PAGE, 1), q=q, etype=etype, date_from=date_from,
                           date_to=date_to, open_only=open_only, include_past=include_past, event_types=EVENT_TYPES,
                           error=error)


@bp.get("/browse/<int:event_id>")
def event_detail(event_id):
    event = _approved_or_404(event_id)
    registered = registrations.is_registered(event_id, g.user.id)
    today = date.today().isoformat()
    block = rules.registration_block_reason(g.user, event, already_registered=registered,
                                            registered_count=event.registered_count, today=today)
    return render_template(
        "student/event.html", event=event, registered=registered, block_reason=block,
        can_register=block is None and g.user.role == "student", can_cancel=registered and event.event_date >= today,
        schedule=[[r["start_time"], r["title"], r["description"]] for r in events.get_schedule(event_id)])


@bp.post("/browse/<int:event_id>/register")
@role_required("student")
def register(event_id):
    event = _approved_or_404(event_id)
    block = rules.registration_block_reason(
        g.user, event, already_registered=registrations.is_registered(event_id, g.user.id),
        registered_count=event.registered_count, today=date.today().isoformat())
    if block:
        flash(block, "error")
        return redirect(url_for("student.event_detail", event_id=event_id))
    # The capacity is checked again inside the write transaction, so two students cannot take the last seat.
    result = registrations.register(event_id, g.user.id, event.participants)
    if result == registrations.OK:
        workflow.registered(g.user, event)
        flash(f'You are registered for "{event.name}". A confirmation was added to your notifications.', "success")
    elif result == registrations.FULL:
        flash("This event is full.", "error")
    else:
        flash("You are already registered for this event.", "error")
    return redirect(url_for("student.event_detail", event_id=event_id))


@bp.post("/registrations/<int:event_id>/cancel")
@role_required("student")
def cancel(event_id):
    event = events.get(event_id)
    if event is None or not registrations.is_registered(event_id, g.user.id):
        flash("You are not registered for that event.", "error")
    elif event.event_date < date.today().isoformat() or event.status == "completed":
        flash("A past event cannot be cancelled.", "error")
    elif registrations.cancel(event_id, g.user.id):
        workflow.registration_cancelled(g.user, event)
        flash(f'Your registration for "{event.name}" was cancelled.', "success")
    nxt = request.form.get("next", "")
    return redirect(safe_next(nxt) if nxt else url_for("student.my_registrations"))


@bp.get("/my-registrations")
@role_required("student")
def my_registrations():
    today = date.today().isoformat()
    return render_template("student/registrations.html", upcoming=registrations.for_user(g.user.id, True, today),
                           past=registrations.for_user(g.user.id, False, today), today=today)
