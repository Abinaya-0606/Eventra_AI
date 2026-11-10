from datetime import date

from flask import g, jsonify, redirect, render_template, url_for

from app.blueprints.main import bp
from app.db import get_db
from app.models import activity, events, notifications, registrations, tasks, users
from app.services import rag


@bp.get("/")
def dashboard():
    """Each role gets its own dashboard (and its own navigation in base.html)."""
    today = date.today().isoformat()
    user = g.user
    if user.role == "student":
        available, available_total = events.browse(user.id, per_page=3)
        mine = registrations.for_user(user.id, True, today)
        return render_template("main/dashboard_student.html", available=available, available_total=available_total,
                               my_upcoming=mine[:5], my_upcoming_total=len(mine), alerts=notifications.recent(user.id, 5))
    if user.role == "admin":  # admins have their own console
        return redirect(url_for("admin.dashboard"))
    return render_template(
        "main/dashboard.html", stats=events.stats(user), pending_tasks=tasks.pending_count(user),
        upcoming=events.upcoming(user, 5), task_list=tasks.pending_list(user, 5),
        feed=activity.recent(user, 8), today=today, tracker=events.counts_by_status(user.id),
        rejected=events.rejected_for(user.id))


@bp.get("/policies")
def policies():
    # Built from the same data/*.txt files the chatbot uses, so the two can never disagree.
    return render_template("main/policies.html", documents=rag.load_documents())


@bp.get("/about")
def about():
    return render_template("main/about.html")


@bp.get("/healthz")
def healthz():
    """Used by the hosting platform to see that the app and its database are alive. Public and reveals nothing else."""
    try:
        get_db().execute("SELECT 1").fetchone()
    except Exception:  # noqa: BLE001 - any failure means "not healthy"
        return jsonify({"status": "error"}), 503
    return jsonify({"status": "ok"})
