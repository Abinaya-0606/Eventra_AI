"""Side effects of the event approval workflow and of registrations: notifications and activity log.

Routes call these after a change was saved, so the rules (events_logic) stay free of database code.
"""
from flask import url_for

from app.models import activity, events as events_model, notifications, registrations


def _event_link(event) -> str:
    return url_for("events.detail", event_id=event.id)


def _public_link(event) -> str:
    return url_for("student.event_detail", event_id=event.id)


def event_submitted(actor, event, *, resubmitted_edit: bool = False) -> None:
    """Organizer sent an event for approval -> every admin gets a notification."""
    verb = "updated an approved event and needs re-approval for" if resubmitted_edit else "submitted"
    notifications.notify_admins("approval_request", f'{actor.name} {verb} "{event.name}" for approval.',
                                url_for("admin.event_detail", event_id=event.id), exclude_id=actor.id)


def event_reviewed(actor, event, action: str, note: str = "") -> None:
    """Admin approved/rejected -> the organizer is told (with the reason on rejection); students hear about re-approvals."""
    link = _event_link(event)
    if action == "approve":
        notifications.notify(event.owner_id, "approved", f'Your event "{event.name}" was approved and is now visible to students.', link)
        # An event that had registrations was edited and re-approved: tell those students it was updated.
        notifications.notify_many(registrations.active_user_ids(event.id), "update",
                                  f'"{event.name}" was updated by the organizer. Please check the latest details.',
                                  _public_link(event))
    elif action == "reject":
        notifications.notify(event.owner_id, "rejected", f'Your event "{event.name}" was rejected: {note}', link)


def review_event(actor, event, action: str, note: str = "") -> None:
    """Apply an already-validated admin decision ('approve' or 'reject'): status, history, activity log, notifications."""
    new_status = "approved" if action == "approve" else "rejected"
    events_model.set_status(event.id, new_status, note, reviewer_id=actor.id)
    activity.log(actor, f'Event "{event.name}" {"approved" if action == "approve" else "rejected"}', event.owner_id, event.id)
    event_reviewed(actor, event, action, note)


def event_completed(event) -> None:
    notifications.notify_many(registrations.active_user_ids(event.id), "update",
                              f'"{event.name}" has been marked as completed. Thank you for taking part!', "")


def event_deleted(event) -> None:
    """Called BEFORE the row is deleted (registrations disappear with it)."""
    if event.status in ("approved", "completed"):
        notifications.notify_many(registrations.active_user_ids(event.id), "update",
                                  f'"{event.name}" has been cancelled by the organizer.', "")


def registered(student, event) -> None:
    notifications.notify(student.id, "registration",
                         f'You are registered for "{event.name}" on {event.event_date} at {event.start_time}.',
                         _public_link(event))
    activity.log(student, f'Registered for "{event.name}"', event.owner_id, event.id)


def registration_cancelled(student, event) -> None:
    notifications.notify(student.id, "registration", f'Your registration for "{event.name}" was cancelled.', "")
    activity.log(student, f'Cancelled registration for "{event.name}"', event.owner_id, event.id)


def announced(actor, event, message: str) -> int:
    sent = notifications.notify_many(registrations.active_user_ids(event.id), "update",
                                     f'Update for "{event.name}": {message}', _public_link(event))
    activity.log(actor, f'Sent an update to {sent} registered student(s) of "{event.name}"', event.owner_id, event.id)
    return sent
