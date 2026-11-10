from flask import abort, g, redirect, render_template, request, url_for

from app.blueprints.notifications import bp
from app.models import notifications
from app.security import safe_next

PER_PAGE = 20


@bp.get("/notifications")
def inbox():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    unread_only = request.args.get("unread") == "1"
    items, total = notifications.list_for(g.user.id, page, PER_PAGE, unread_only)
    return render_template("notifications/list.html", items=items, total=total, page=page, unread_only=unread_only,
                           pages=max((total + PER_PAGE - 1) // PER_PAGE, 1))


@bp.post("/notifications/<int:notification_id>/read")
def read(notification_id):
    """Marks the notification read, then opens what it points to. Other users' notifications answer 404."""
    row = notifications.mark_read(g.user.id, notification_id)
    if row is None:
        abort(404)
    target = row["link"]
    return redirect(safe_next(target) if target else url_for("notifications.inbox"))


@bp.post("/notifications/read-all")
def read_all():
    notifications.mark_all_read(g.user.id)
    return redirect(url_for("notifications.inbox"))
