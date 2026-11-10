import calendar as cal
import csv
import io
import re
from datetime import date

from flask import Response, abort, flash, g, jsonify, redirect, render_template, request, url_for

from app.blueprints.events import bp
from app.models import activity, events, registrations, tasks
from app.security import safe_next
from app.services import events_logic as rules
from app.services import workflow
from app.services.validation import (EVENT_TYPES, ValidationError, clean_amount, clean_choice, clean_date,
                                     clean_int, clean_text, clean_time)

PER_PAGE = 10


def _parse_event(form) -> dict:
    data = {
        "name": clean_text(form, "name", "Event name", max_len=100),
        "event_type": clean_choice(form, "event_type", "Event type", EVENT_TYPES),
        "description": clean_text(form, "description", "Description", max_len=1000, required=False, multiline=True),
        "participants": clean_int(form, "participants", "Number of participants", min_value=1, max_value=10000),
        "budget": clean_amount(form, "budget", "Estimated budget"),
        "duration_hours": clean_int(form, "duration_hours", "Duration (hours)", min_value=1, max_value=72),
        "venue": clean_text(form, "venue", "Venue", max_len=100, required=False),
        "event_date": clean_date(form, "event_date", "Event date", required=True),
        "start_time": clean_time(form, "start_time", "Start time"),
    }
    if not 2000 <= int(data["event_date"][:4]) <= 2100:
        raise ValidationError("Event date must be between the years 2000 and 2100.", "event_date")
    return data


def _load(event_id: int):
    """The event if it exists AND this user may see it; otherwise 404 (we do not reveal that it exists)."""
    event = events.get(event_id)
    if event is None or not rules.can_view(g.user, event):
        abort(404)
    return event


# ---------- list ----------
@bp.get("/events")
def list_events():
    q = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status", "")
    status = status if status in rules.STATUSES else ""
    etype = request.args.get("type", "")
    etype = etype if etype in EVENT_TYPES else ""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    items, total = events.search(g.user, q, status, etype, page, PER_PAGE)
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    return render_template("events/list.html", events=items, total=total, page=page, pages=pages, q=q,
                           status=status, etype=etype, statuses=rules.STATUS_LABELS, event_types=EVENT_TYPES)


# ---------- create / edit / delete ----------
@bp.route("/events/new", methods=["GET", "POST"])
def create_event():
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("events/form.html", form={"start_time": "09:00", **request.args.to_dict()},
                               event_types=EVENT_TYPES, editing=False)
    try:
        data = _parse_event(request.form)
    except ValidationError as exc:
        return render_template("events/form.html", form=request.form, error=exc.message, field=exc.field,
                               event_types=EVENT_TYPES, editing=False), 400
    event_id = events.create(g.user.id, data)
    activity.log(g.user, f'Created event "{data["name"]}"', g.user.id, event_id)
    flash("Event created as a draft. Add a schedule and tasks, then submit it for approval.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
def edit_event(event_id):
    event = _load(event_id)
    if not rules.can_edit(g.user, event):
        flash("This event cannot be edited right now. Withdraw it from approval first if it is pending.", "error")
        return redirect(url_for("events.detail", event_id=event_id))
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("events/form.html", form=vars(event), event_types=EVENT_TYPES, editing=True, event=event)
    try:
        data = _parse_event(request.form)
    except ValidationError as exc:
        return render_template("events/form.html", form=request.form, error=exc.message, field=exc.field,
                               event_types=EVENT_TYPES, editing=True, event=event), 400
    if data["participants"] < event.registered_count:
        return render_template("events/form.html", form=request.form, field="participants", event_types=EVENT_TYPES,
                               editing=True, event=event,
                               error=f"Participants cannot be lower than the {event.registered_count} students already registered."), 400
    new_status = {"approved": "pending", "rejected": "draft"}.get(event.status)  # approved events need re-approval
    events.update(event_id, data, new_status)
    activity.log(g.user, f'Updated event "{data["name"]}"' + (" (sent back for approval)" if new_status == "pending" else ""),
                 event.owner_id, event_id)
    if new_status == "pending":  # an approved event changed: it left the student view, admins must approve again
        workflow.event_submitted(g.user, events.get(event_id), resubmitted_edit=True)
    flash("Event updated." + (" Because it was approved, it needs approval again." if new_status == "pending" else ""), "success")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.post("/events/<int:event_id>/delete")
def delete_event(event_id):
    event = _load(event_id)
    if not rules.can_delete(g.user, event):
        abort(403)
    workflow.event_deleted(event)  # tell registered students first: their registrations vanish with the event
    events.delete(event_id)
    activity.log(g.user, f'Deleted event "{event.name}"', event.owner_id)
    flash(f'Event "{event.name}" deleted.', "success")
    return redirect(url_for("events.list_events"))


# ---------- details & status ----------
@bp.get("/events/<int:event_id>")
def detail(event_id):
    event = _load(event_id)
    return render_template(
        "events/detail.html", event=event, tasks=tasks.for_event(event_id),
        schedule=[[r["start_time"], r["title"], r["description"]] for r in events.get_schedule(event_id)],
        status_label=rules.STATUS_LABELS[event.status], task_labels=rules.TASK_LABELS,
        actions=[(a, rules.ACTION_LABELS[a]) for a in rules.available_actions(g.user, event)],
        can_edit=rules.can_edit(g.user, event), can_delete=rules.can_delete(g.user, event),
        can_manage=rules.can_manage_content(g.user, event), today=date.today().isoformat(),
        reg_preview=registrations.for_event(event_id)[:5], can_announce=rules.can_announce(g.user, event))


@bp.post("/events/<int:event_id>/status")
def change_status(event_id):
    """Every workflow move goes through here: rules.allowed_action decides who may do what.

    Organizer: submit / withdraw / complete their own event. Admin: approve / reject events of OTHER people.
    """
    event = _load(event_id)
    action = request.form.get("action", "")
    back = safe_next(request.form.get("next")) if request.form.get("next") else url_for("events.detail", event_id=event_id)
    new_status = rules.allowed_action(g.user, event, action)
    if new_status is None:
        flash("That status change is not allowed.", "error")
        return redirect(back)
    note = ""
    if action == "reject":
        note = clean_text(request.form, "note", "Reason", max_len=300, required=False, multiline=True)
        if not note:
            flash("Please tell the organizer why the event was rejected.", "error")
            return redirect(back)
    if action in ("approve", "reject"):
        workflow.review_event(g.user, event, action, note)
    else:
        events.set_status(event_id, new_status, note)
        activity.log(g.user, f'Event "{event.name}" {rules.ACTION_MESSAGES[action]}', event.owner_id, event_id)
    if action == "submit":
        workflow.event_submitted(g.user, event)
    elif action == "complete":
        workflow.event_completed(event)
    flash(f"Event {rules.ACTION_MESSAGES[action]}.", "success")
    return redirect(back)


# ---------- registered students (organizer of the event, or an admin) ----------
@bp.get("/events/<int:event_id>/registrations")
def event_registrations(event_id):
    event = _load(event_id)
    return render_template("events/registrations.html", event=event, students=registrations.for_event(event_id),
                           can_announce=rules.can_announce(g.user, event))


def _csv_safe(value) -> str:
    """Spreadsheet programs run cells that start with = + - @ as formulas; a leading quote makes them plain text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.get("/events/<int:event_id>/registrations.csv")
def event_registrations_csv(event_id):
    event = _load(event_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Name", "Email", "Department", "Registered at (UTC)"])
    for r in registrations.for_event(event_id):
        writer.writerow([_csv_safe(r["name"]), _csv_safe(r["email"]), _csv_safe(r["department"]), r["created_at"]])
    safe = re.sub(r"[^a-z0-9]+", "-", event.name.lower()).strip("-")[:40] or "event"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="registrations-{safe}.csv"'})


@bp.post("/events/<int:event_id>/announce")
def announce(event_id):
    event = _load(event_id)
    if not rules.can_announce(g.user, event):
        abort(403)
    message = clean_text(request.form, "message", "Message", max_len=250, required=False, multiline=True)
    if not message:
        flash("Write a message first.", "error")
    else:
        sent = workflow.announced(g.user, event, message)
        flash(f"Update sent to {sent} registered student{'' if sent == 1 else 's'}.", "success")
    return redirect(url_for("events.event_registrations", event_id=event_id))


# ---------- calendar ----------
@bp.get("/calendar")
def calendar_view():
    today = date.today()
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", request.args.get("month", ""))
    year, month = (int(match.group(1)), int(match.group(2))) if match and 2000 <= int(match.group(1)) <= 2100 else (today.year, today.month)
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    return render_template(
        "events/calendar.html", weeks=cal.Calendar(firstweekday=6).monthdatescalendar(year, month),
        days=events.in_month(g.user, year, month), year=year, month=month, month_name=cal.month_name[month],
        prev=f"{prev_y:04d}-{prev_m:02d}", next=f"{next_y:04d}-{next_m:02d}", today=today,
        statuses=rules.STATUS_LABELS, public=g.user.role == "student")


# ---------- JSON API used by the event page ----------
def _api_event(event_id: int):
    event = _load(event_id)
    if not rules.can_manage_content(g.user, event):
        return event, (jsonify({"error": "You cannot change this event."}), 403)
    return event, None


@bp.post("/api/events/<int:event_id>/schedule")
def save_schedule(event_id):
    event, denied = _api_event(event_id)
    if denied:
        return denied
    payload = request.get_json(silent=True)
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > 30:
        return jsonify({"error": "Send between 0 and 30 schedule rows."}), 400
    items = []
    try:
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError("Each schedule row must be an object.")
            items.append({"time": clean_time(row, "time", "Time"),
                          "title": clean_text(row, "title", "Activity", max_len=120),
                          "description": clean_text(row, "description", "Details", max_len=200, required=False)})
    except ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    events.replace_schedule(event_id, items)
    activity.log(g.user, f'Saved the schedule of "{event.name}" ({len(items)} items)', event.owner_id, event_id)
    return jsonify({"saved": len(items)})


@bp.post("/api/events/<int:event_id>/tasks/bulk")
def bulk_tasks(event_id):
    """Turns an AI checklist into real tasks."""
    event, denied = _api_event(event_id)
    if denied:
        return denied
    payload = request.get_json(silent=True)
    rows = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 60:
        return jsonify({"error": "Send between 1 and 60 tasks."}), 400
    clean = []
    try:
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError("Each task must be an object.")
            clean.append((clean_text(row, "title", "Task", max_len=200),
                          None, clean_choice(row, "phase", "Phase", ("before", "during", "after"), default="before")))
    except ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    tasks.create_many(event_id, clean)
    activity.log(g.user, f'Added {len(clean)} checklist tasks to "{event.name}"', event.owner_id, event_id)
    return jsonify({"added": len(clean)})
