from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from app.blueprints.tasks import bp
from app.models import activity, events, tasks, users
from app.security import safe_next
from app.services import events_logic as rules
from app.services.validation import ValidationError, clean_date, clean_text

PER_PAGE = 20


def _assignee_id(form):
    """Blank = unassigned. Otherwise the email must belong to an active organizer or admin."""
    email = (form.get("assignee_email") or "").strip().lower()
    if not email:
        return None
    person = users.get_by_email(email)
    if person is None or not person.is_active:
        raise ValidationError("No active user has that email address.", "assignee_email")
    if person.role not in ("organizer", "admin"):  # the task area is for the organizing team; students have no access to it
        raise ValidationError("Tasks can only be assigned to organizers or admins.", "assignee_email")
    return person.id


def _load_task(task_id: int):
    task = tasks.get(task_id)
    if task is None or not (g.user.is_admin or task.event_owner_id == g.user.id or task.assignee_id == g.user.id):
        abort(404)
    return task


@bp.get("/tasks")
def list_tasks():
    status = request.args.get("status", "")
    status = status if status in rules.TASK_STATUSES else ""
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    q = (request.args.get("q") or "").strip()[:100]
    items, total = tasks.list_for_user(g.user, status, page, PER_PAGE, q)
    return render_template("tasks/list.html", tasks=items, total=total, page=page, q=q,
                           pages=max((total + PER_PAGE - 1) // PER_PAGE, 1), status=status,
                           labels=rules.TASK_LABELS, today=date.today().isoformat())


@bp.post("/events/<int:event_id>/tasks")
def create_task(event_id):
    event = events.get(event_id)
    if event is None or not rules.can_view(g.user, event):
        abort(404)
    if not rules.can_manage_content(g.user, event):
        abort(403)
    try:
        title = clean_text(request.form, "title", "Task", max_len=200)
        deadline = clean_date(request.form, "deadline", "Deadline")
        assignee = _assignee_id(request.form)
    except ValidationError as exc:
        flash(exc.message, "error")
        return redirect(url_for("events.detail", event_id=event_id) + "#tasks")
    tasks.create(event_id, title, assignee, deadline)
    activity.log(g.user, f'Added task "{title}" to "{event.name}"', event.owner_id, event_id)
    flash("Task added.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#tasks")


@bp.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):
    task = _load_task(task_id)
    if not rules.can_manage_task(g.user, task):
        abort(403)
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("tasks/edit.html", task=task, form={
            "title": task.title, "deadline": task.deadline or "",
            "assignee_email": users.get_by_id(task.assignee_id).email if task.assignee_id else ""})
    try:
        title = clean_text(request.form, "title", "Task", max_len=200)
        deadline = clean_date(request.form, "deadline", "Deadline")
        assignee = _assignee_id(request.form)
    except ValidationError as exc:
        return render_template("tasks/edit.html", task=task, form=request.form, error=exc.message, field=exc.field), 400
    tasks.update(task_id, title, assignee, deadline)
    activity.log(g.user, f'Updated task "{title}"', task.event_owner_id, task.event_id)
    flash("Task updated.", "success")
    return redirect(url_for("events.detail", event_id=task.event_id) + "#tasks")


@bp.post("/tasks/<int:task_id>/status")
def change_task_status(task_id):
    task = _load_task(task_id)
    status = request.form.get("status", "")
    if status not in rules.TASK_STATUSES or not rules.can_update_task_status(g.user, task):
        flash("That change is not allowed.", "error")
    else:
        tasks.set_status(task_id, status)
        activity.log(g.user, f'Task "{task.title}" marked {rules.TASK_LABELS[status].lower()}', task.event_owner_id, task.event_id)
    return redirect(safe_next(request.form.get("next")))


@bp.post("/tasks/<int:task_id>/delete")
def delete_task(task_id):
    task = _load_task(task_id)
    if not rules.can_manage_task(g.user, task):
        abort(403)
    tasks.delete(task_id)
    activity.log(g.user, f'Deleted task "{task.title}"', task.event_owner_id, task.event_id)
    flash("Task deleted.", "success")
    return redirect(safe_next(request.form.get("next")))
