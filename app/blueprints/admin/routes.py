"""Admin area: user / organizer / student management, the approval queue, activity logs and venues.

The whole blueprint is admin-only (see security.BLUEPRINT_ROLES) and every route also carries
@role_required("admin") as a second lock.
"""
import sqlite3

from flask import abort, current_app, flash, g, redirect, render_template, request, session, url_for

from app.blueprints.admin import bp
from app.models import activity, events, planning, registrations, reviews, tasks, users
from app.security import role_required, safe_next, start_session, throttle
from app.services import events_logic as rules
from app.services import workflow
from app.services.admin_seed import validate_admin_password
from app.services.insights import FACILITIES
from app.services.validation import (EVENT_TYPES, ValidationError, clean_amount, clean_choice, clean_email, clean_int,
                                     clean_password, clean_text)

LOG_PER_PAGE = 25
EVENTS_PER_PAGE = 12
PEOPLE = {  # endpoint -> (role filter, page title, subtitle)
    "admin.admin_list": ("admin", "Administrator accounts", "Only existing admins can create more admins. Public sign-up can never create one."),
    "admin.user_list": (None, "User management", "Create accounts, change roles and activate or deactivate people."),
    "admin.organizer_list": ("organizer", "Organizer management", "Organizers create events and submit them for approval."),
    "admin.student_list": ("student", "Student management", "Students browse approved events and register for them."),
}


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


def _people_page(endpoint: str, status: int = 200, form=None, error=None):
    role, title, subtitle = PEOPLE[endpoint]
    return render_template("admin/users.html", people=users.list_with_counts(role), roles=users.ROLES, title=title,
                           subtitle=subtitle, endpoint=endpoint, role_filter=role, form=form or {}, error=error), status


def _back(default: str) -> str:
    """Return to the list the admin came from (only same-site paths are accepted)."""
    target = request.form.get("next", "")
    return safe_next(target) if target else default


# ---------- separate admin sign-in ----------
GENERIC_LOGIN_ERROR = "Invalid email or password."


def _admin_next(target: str) -> str:
    """After sign-in go back to an /admin page the admin asked for, otherwise to the dashboard."""
    target = safe_next(target) if target else ""
    return target if target.startswith("/admin") else url_for("admin.dashboard")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Admin-only sign-in. Student/organizer credentials never start a session here."""
    if g.user and g.user.is_admin:
        return redirect(url_for("admin.dashboard"))
    nxt = request.values.get("next", "")
    if request.method != "POST":
        return render_template("admin/login.html", form={}, next=nxt)
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    key = f"admin|{email}|{request.remote_addr}"
    if throttle.blocked(key):
        return render_template("admin/login.html", form=request.form, next=nxt,
                               error="Too many failed attempts. Please wait a few minutes and try again."), 429
    user = users.get_by_email(email) if email else None
    # Same answer for "no such user", "wrong password" and "not an admin": nothing reveals which accounts exist.
    if not users.verify_password(user, password) or not user.is_admin:
        throttle.fail(key)
        return render_template("admin/login.html", form=request.form, next=nxt, error=GENERIC_LOGIN_ERROR), 401
    if not user.is_active:
        return render_template("admin/login.html", form=request.form, next=nxt,
                               error="This account has been deactivated."), 403
    throttle.reset(key)
    start_session(user)
    activity.log_admin(user, "Signed in to the admin console")
    return redirect(_admin_next(nxt))


@bp.post("/logout")
@role_required("admin")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


# ---------- overview ----------
@bp.get("/dashboard")
@role_required("admin")
def dashboard():
    by_status, by_role = events.counts_by_status(), users.counts_by_role()
    return render_template("admin/dashboard.html", by_status=by_status, by_role=by_role,
                           total_events=sum(by_status.values()), total_users=sum(by_role.values()),
                           registrations_total=registrations.total_active(), pending=events.pending_review(5),
                           feed=activity.recent(g.user, 8))


# ---------- people ----------
@bp.get("/admins")
@role_required("admin")
def admin_list():
    return _people_page("admin.admin_list")


@bp.get("/users")
@role_required("admin")
def user_list():
    return _people_page("admin.user_list")


@bp.get("/organizers")
@role_required("admin")
def organizer_list():
    return _people_page("admin.organizer_list")


@bp.get("/students")
@role_required("admin")
def student_list():
    return _people_page("admin.student_list")


@bp.post("/users/create")
@role_required("admin")
def create_user():
    """Admins can create student and organizer accounts (and other admins)."""
    endpoint = request.form.get("source", "")
    endpoint = endpoint if endpoint in PEOPLE else "admin.user_list"
    try:
        name = clean_text(request.form, "name", "Name", max_len=80)
        email = clean_email(request.form)
        password = clean_password(request.form)
        role = clean_choice(request.form, "role", "Role", users.ROLES)
        if role == "admin":
            validate_admin_password(password, email)
        department = clean_text(request.form, "department", "Department", max_len=100, required=False)
        user = users.create_user(name, email, password, role=role, department=department)
    except ValidationError as exc:
        return _people_page(endpoint, 400, form=request.form, error=exc.message)
    except users.EmailTaken:
        return _people_page(endpoint, 409, form=request.form, error="An account with this email already exists.")
    activity.log_admin(g.user, f"Created {_article(role)} {role} account for {user.name} ({user.email})")
    flash(f"{role.capitalize()} account created for {user.name}.", "success")
    return redirect(url_for(endpoint))


def _target(user_id: int):
    """The user being edited, or None (with a message) if it is missing or is the admin themselves."""
    target = users.get_by_id(user_id)
    if target is None:
        flash("User not found.", "error")
    elif target.id == g.user.id:
        flash("You cannot change your own role or status.", "error")
        return None
    return target


@bp.post("/users/<int:user_id>/role")
@role_required("admin")
def change_role(user_id):
    target = _target(user_id)
    role = request.form.get("role")
    if target and role in users.ROLES:
        if role != target.role:
            users.set_role(target.id, role)
            activity.log_admin(g.user, f"Changed the role of {target.name} to {role}")
        flash(f"{target.name} is now {role}.", "success")
    elif target:
        flash("Invalid role.", "error")
    return redirect(_back(url_for("admin.user_list")))


@bp.post("/users/<int:user_id>/active")
@role_required("admin")
def toggle_active(user_id):
    target = _target(user_id)
    if target:
        users.set_active(target.id, not target.is_active)
        state = "activated" if not target.is_active else "deactivated"
        activity.log_admin(g.user, f"{state.capitalize()} the account of {target.name}")
        flash(f"{target.name} {state}.", "success")
    return redirect(_back(url_for("admin.user_list")))


# ---------- event approvals ----------
@bp.get("/approvals")  # earlier URL, kept so old links and bookmarks still work
@bp.get("/event-approvals")
@role_required("admin")
def approvals():
    view = request.args.get("view", "pending")
    view = view if view in ("pending", "approved", "rejected") else "pending"
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    by_status = events.counts_by_status()
    counts = {"pending": by_status.get("pending", 0), "approved": by_status.get("approved", 0) + by_status.get("completed", 0),
              "rejected": by_status.get("rejected", 0)}
    if view == "pending":
        items, total = events.pending_review(), counts["pending"]
    else:
        items, total = events.reviewed_list(view, page, EVENTS_PER_PAGE)
    return render_template("admin/approvals.html", items=items, view=view, counts=counts, page=page, total=total,
                           pages=max((total + EVENTS_PER_PAGE - 1) // EVENTS_PER_PAGE, 1) if view != "pending" else 1)


@bp.get("/events")
@role_required("admin")
def all_events():
    q = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status", "")
    status = status if status in rules.STATUSES else ""
    etype = request.args.get("type", "")
    etype = etype if etype in EVENT_TYPES else ""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    items, total = events.search(g.user, q, status, etype, page, EVENTS_PER_PAGE)
    return render_template("admin/events.html", events=items, total=total, page=page, q=q, status=status, etype=etype,
                           pages=max((total + EVENTS_PER_PAGE - 1) // EVENTS_PER_PAGE, 1),
                           statuses=rules.STATUS_LABELS, event_types=EVENT_TYPES)


@bp.get("/events/<int:event_id>")
@role_required("admin")
def event_detail(event_id):
    event = events.get(event_id)
    if event is None:
        abort(404)
    organizer = users.get_by_id(event.owner_id)
    return render_template(
        "admin/event_detail.html", event=event, organizer=organizer, status_label=rules.STATUS_LABELS[event.status],
        schedule=events.get_schedule(event_id), tasks=tasks.for_event(event_id), history=reviews.for_event(event_id),
        associated=rules.is_associated(g.user, event), can_review=event.status == "pending" and not rules.is_associated(g.user, event),
        owner_stats=events.counts_by_status(event.owner_id))


def _review(event_id: int, action: str):
    """Approve or reject. Every rule is enforced here on the server; hiding the buttons is never the protection."""
    event = events.get(event_id)
    if event is None:
        abort(404)
    back = url_for("admin.event_detail", event_id=event_id)
    if rules.allowed_action(g.user, event, action) is None:
        if event.status != "pending":
            flash("Only events that are waiting for approval can be approved or rejected.", "error")
        elif rules.is_associated(g.user, event):
            flash("You are associated with this event (as its creator or a task assignee), so another admin must review it.", "error")
        else:
            flash("That action is not allowed.", "error")
        return redirect(back)
    note = ""
    if action == "reject":
        note = clean_text(request.form, "note", "Reason", max_len=300, required=False, multiline=True)
        if not note:
            flash("A reason is required to reject an event. The organizer will see it.", "error")
            return redirect(back)
    workflow.review_event(g.user, event, action, note)
    flash(f'"{event.name}" {"approved. It is now visible to students" if action == "approve" else "rejected. The organizer can see your reason and resubmit"}.', "success")
    nxt = request.form.get("next", "")
    return redirect(safe_next(nxt) if nxt.startswith("/admin") else url_for("admin.approvals"))


@bp.post("/events/<int:event_id>/approve")
@role_required("admin")
def approve_event(event_id):
    return _review(event_id, "approve")


@bp.post("/events/<int:event_id>/reject")
@role_required("admin")
def reject_event(event_id):
    return _review(event_id, "reject")


# ---------- activity log ----------
@bp.get("/activity")  # earlier URL, kept so old links still work
@bp.get("/activity-logs")
@role_required("admin")
def activity_log():
    q = (request.args.get("q") or "").strip()[:100]
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    rows, total = activity.search(q, page, LOG_PER_PAGE)
    return render_template("admin/activity.html", rows=rows, total=total, page=page, q=q,
                           pages=max((total + LOG_PER_PAGE - 1) // LOG_PER_PAGE, 1))


# ---------- venues (used by the AI venue recommendation) ----------
def _parse_venue(form) -> dict:
    return {
        "name": clean_text(form, "name", "Venue name", max_len=80),
        "capacity": clean_int(form, "capacity", "Capacity", min_value=1, max_value=100000),
        "cost": clean_amount(form, "cost_per_day", "Cost per day"),
        "facilities": [f for f in FACILITIES if f in form.getlist("facilities")],
        "notes": clean_text(form, "notes", "Notes", max_len=300, required=False, multiline=True),
    }


def _venues_page(status=200, form=None, editing=None):
    return render_template("admin/venues.html", venues=planning.list_venues(active_only=False), facilities=FACILITIES,
                           form=form or {}, editing=editing), status


@bp.get("/venues")
@role_required("admin")
def venue_list():
    return _venues_page()


@bp.get("/venues/<int:venue_id>/edit")
@role_required("admin")
def venue_edit_form(venue_id):
    venue = planning.get_venue(venue_id)
    if venue is None:
        flash("Venue not found.", "error")
        return redirect(url_for("admin.venue_list"))
    return _venues_page(form={"name": venue.name, "capacity": venue.capacity, "cost_per_day": venue.cost_per_day,
                              "notes": venue.notes, "facilities": venue.facilities}, editing=venue)


@bp.post("/venues/save")
@role_required("admin")
def venue_save():
    venue_id = request.form.get("venue_id", type=int)
    editing = planning.get_venue(venue_id) if venue_id else None
    if venue_id and editing is None:
        flash("Venue not found.", "error")
        return redirect(url_for("admin.venue_list"))
    form = {**request.form.to_dict(), "facilities": request.form.getlist("facilities")}
    try:
        data = _parse_venue(request.form)
        planning.save_venue(venue_id, data["name"], data["capacity"], data["cost"], data["facilities"], data["notes"])
    except ValidationError as exc:
        flash(exc.message, "error")
        return _venues_page(400, form, editing)
    except sqlite3.IntegrityError:
        flash("A venue with that name already exists.", "error")
        return _venues_page(400, form, editing)
    activity.log_admin(g.user, f'{"Updated" if editing else "Added"} venue "{data["name"]}"')
    flash("Venue saved.", "success")
    return redirect(url_for("admin.venue_list"))


@bp.post("/venues/<int:venue_id>/active")
@role_required("admin")
def venue_toggle(venue_id):
    venue = planning.get_venue(venue_id)
    if venue is None:
        flash("Venue not found.", "error")
    else:
        planning.set_venue_active(venue_id, not venue.is_active)
        state = "deactivated" if venue.is_active else "activated"
        activity.log_admin(g.user, f'{state.capitalize()} venue "{venue.name}"')
        flash(f"{venue.name} {state}.", "success")
    return redirect(url_for("admin.venue_list"))
