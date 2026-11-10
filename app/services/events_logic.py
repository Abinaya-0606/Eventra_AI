"""Business rules for events: who may do what, and which status changes are allowed.

Kept free of database and Flask code so the rules are easy to read and test.
"""
STATUSES = ("draft", "pending", "approved", "rejected", "completed")
STATUS_LABELS = {"draft": "Draft", "pending": "Pending approval", "approved": "Approved",
                 "rejected": "Rejected", "completed": "Completed"}
TASK_STATUSES = ("todo", "in_progress", "done")
TASK_LABELS = {"todo": "To do", "in_progress": "In progress", "done": "Done"}

# (current status, action) -> (new status, who may do it)
#   "owner"  = the person who created the event
#   "admin"  = an administrator who is NOT associated with the event (owner or task assignee): nobody reviews their own event
TRANSITIONS = {
    ("draft", "submit"): ("pending", "owner"),
    ("rejected", "submit"): ("pending", "owner"),
    ("pending", "withdraw"): ("draft", "owner"),
    ("pending", "approve"): ("approved", "admin"),
    ("pending", "reject"): ("rejected", "admin"),
    ("approved", "complete"): ("completed", "owner"),
}
ACTION_LABELS = {"submit": "Submit for approval", "withdraw": "Withdraw", "approve": "Approve",
                 "reject": "Reject", "complete": "Mark as completed"}
ACTION_MESSAGES = {"submit": "submitted for approval", "withdraw": "withdrawn to draft", "approve": "approved",
                   "reject": "rejected", "complete": "marked as completed"}


def is_owner(user, event) -> bool:
    return event.owner_id == user.id


def is_associated(user, event) -> bool:
    """True if `user` owns the event or is assigned one of its tasks (so cannot be its reviewer)."""
    ids = (getattr(event, "assignee_ids", None) or "").split(",")
    return is_owner(user, event) or str(user.id) in ids


def can_view(user, event) -> bool:
    return is_owner(user, event) or user.is_admin


def can_edit(user, event) -> bool:
    """Owners edit drafts and rejected events. Editing an approved event sends it back for approval."""
    return is_owner(user, event) and event.status in ("draft", "rejected", "approved")


def can_delete(user, event) -> bool:
    return can_view(user, event)


def can_manage_content(user, event) -> bool:
    """Schedule and task management by the owner, until the event is completed."""
    return is_owner(user, event) and event.status != "completed"


def allowed_action(user, event, action: str):
    """New status if `user` may apply `action` to `event`, otherwise None."""
    rule = TRANSITIONS.get((event.status, action))
    if rule is None:
        return None
    new_status, who = rule
    if who == "owner" and is_owner(user, event):
        return new_status
    if who == "admin" and user.is_admin and not is_associated(user, event):
        return new_status
    return None


def available_actions(user, event) -> list[str]:
    return [a for (status, a) in TRANSITIONS if status == event.status and allowed_action(user, event, a)]


def can_announce(user, event) -> bool:
    """Only the organizer who owns an approved event can message its registered students."""
    return is_owner(user, event) and event.status == "approved"


def registration_block_reason(user, event, *, already_registered: bool, registered_count: int, today: str):
    """Why `user` cannot register for `event` right now (a sentence for the page), or None if they can."""
    if user.role != "student":
        return "Only students can register for events."
    if already_registered:
        return "You are already registered for this event."
    if event.status != "approved":
        return "This event is not open for registration."
    if event.event_date < today:
        return "This event has already taken place."
    if registered_count >= event.participants:
        return "This event is full. Check back later in case a seat is released."
    return None


def can_assign_to_others(user) -> bool:
    return user.role in ("organizer", "admin")


def can_update_task_status(user, task) -> bool:
    return user.is_admin or task.event_owner_id == user.id or task.assignee_id == user.id


def can_manage_task(user, task) -> bool:
    """Edit or delete a task: the event owner or an admin."""
    return user.is_admin or task.event_owner_id == user.id
