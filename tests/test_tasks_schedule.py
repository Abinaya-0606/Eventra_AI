"""Phase 3: tasks (assign, deadline, status, progress, permissions), saved schedule API, bulk checklist import."""
import sqlite3

import pytest

from app.models import tasks as tasks_model
from conftest import make_client, make_user
from test_events import new_event, row, set_status


def add_task(client, eid, **data):
    return client.post(f"/events/{eid}/tasks", data={"title": "Book hall", **data})


def task_ids(app, eid):
    with app.app_context():
        return [t.id for t in tasks_model.for_event(eid)]


def get_task(app, tid):
    with app.app_context():
        return tasks_model.get(tid)


@pytest.fixture()
def eid(client):
    return new_event(client)


# ---------- create ----------
def test_create_task_with_deadline(client, app, eid):
    assert add_task(client, eid, deadline="2030-01-05").status_code == 302
    t = get_task(app, task_ids(app, eid)[0])
    assert (t.title, t.deadline, t.status, t.assignee_id) == ("Book hall", "2030-01-05", "todo", None)
    assert "Book hall" in client.get(f"/events/{eid}").get_data(as_text=True)


@pytest.mark.parametrize("data", [{"title": ""}, {"title": "x" * 201}, {"deadline": "5/1/2030"}, {"assignee_email": "ghost@example.com"}])
def test_create_task_validation(client, app, eid, data):
    res = add_task(client, eid, **data) if data.get("title") != "" else client.post(f"/events/{eid}/tasks", data=data, follow_redirects=True)
    assert task_ids(app, eid) == []
    assert res.status_code in (200, 302)


def test_validation_message_is_shown(client, eid):
    html = client.post(f"/events/{eid}/tasks", data={"title": ""}, follow_redirects=True).get_data(as_text=True)
    assert "Task is required" in html


def test_assign_to_self(client, app, eid):
    add_task(client, eid, assignee_email="organizer@example.com")
    assert get_task(app, task_ids(app, eid)[0]).assignee_name == "Olive Organizer"


def test_tasks_go_to_the_organizing_team_not_to_students(client, app, other):
    make_user(app, "friend@example.com", "Fran Friend", "organizer")
    make_user(app, "learner@example.com", "Lee Learner", "student")
    sid = new_event(client)
    add_task(client, sid, assignee_email="learner@example.com")  # students have no task area
    assert task_ids(app, sid) == []
    oid = new_event(other)
    add_task(other, oid, assignee_email="friend@example.com")
    assert get_task(app, task_ids(app, oid)[0]).assignee_name == "Fran Friend"


def test_cannot_assign_to_deactivated_user(other, app, admin_client):
    target = make_user(app, "gone@example.com", "Gone")
    admin_client.post(f"/admin/users/{target.id}/active")
    oid = new_event(other)
    add_task(other, oid, assignee_email="gone@example.com")
    assert task_ids(app, oid) == []


def test_other_users_cannot_add_tasks_to_my_event(client, other, app, eid):
    assert add_task(other, eid).status_code == 404
    assert task_ids(app, eid) == []


def test_cannot_add_tasks_to_completed_event(client, app, eid):
    set_status(app, eid, "completed")
    assert add_task(client, eid).status_code == 403


# ---------- status & progress ----------
def test_status_updates_and_completion_tracking(client, app, eid):
    add_task(client, eid, title="A"), add_task(client, eid, title="B")
    a, b = task_ids(app, eid)
    client.post(f"/tasks/{a}/status", data={"status": "done"})
    t = get_task(app, a)
    assert t.status == "done" and t.completed_at
    assert row(app, eid).progress == 50 and (row(app, eid).task_done, row(app, eid).task_total) == (1, 2)
    client.post(f"/tasks/{a}/status", data={"status": "in_progress"})
    assert get_task(app, a).completed_at is None and row(app, eid).progress == 0
    assert "50%" in (client.post(f"/tasks/{b}/status", data={"status": "done"}) and client.get("/events").get_data(as_text=True))


def test_bad_status_is_ignored(client, app, eid):
    add_task(client, eid)
    tid = task_ids(app, eid)[0]
    client.post(f"/tasks/{tid}/status", data={"status": "bogus"})
    assert get_task(app, tid).status == "todo"


def test_status_redirect_cannot_leave_the_site(client, app, eid):
    add_task(client, eid)
    tid = task_ids(app, eid)[0]
    assert client.post(f"/tasks/{tid}/status", data={"status": "done", "next": "https://evil.com"}).headers["Location"] == "/"
    assert client.post(f"/tasks/{tid}/status", data={"status": "todo", "next": "/tasks"}).headers["Location"] == "/tasks"


def test_assignee_can_update_status_but_not_edit_or_delete(app, other):
    oid = new_event(other)
    worker = make_client(app, "worker@example.com", "organizer", "Wendy Worker")
    add_task(other, oid, assignee_email="worker@example.com")
    tid = task_ids(app, oid)[0]
    assert worker.post(f"/tasks/{tid}/status", data={"status": "done"}).status_code == 302
    assert get_task(app, tid).status == "done"
    assert worker.get(f"/tasks/{tid}/edit").status_code == 403
    assert worker.post(f"/tasks/{tid}/edit", data={"title": "Hijack"}).status_code == 403
    assert worker.post(f"/tasks/{tid}/delete").status_code == 403
    assert get_task(app, tid).title == "Book hall"
    assert "Book hall" in worker.get("/tasks").get_data(as_text=True)  # assigned tasks are visible to the assignee
    assert worker.get(f"/events/{oid}").status_code == 404  # ...but the event itself stays private


def test_unrelated_user_cannot_touch_task(client, other, app, eid):
    add_task(client, eid)
    tid = task_ids(app, eid)[0]
    assert other.post(f"/tasks/{tid}/status", data={"status": "done"}).status_code == 404
    assert other.get(f"/tasks/{tid}/edit").status_code == 404
    assert other.post(f"/tasks/{tid}/delete").status_code == 404
    assert "Book hall" not in other.get("/tasks").get_data(as_text=True)


# ---------- edit / delete ----------
def test_edit_task(client, app, eid):
    add_task(client, eid)
    tid = task_ids(app, eid)[0]
    assert client.get(f"/tasks/{tid}/edit").status_code == 200
    client.post(f"/tasks/{tid}/edit", data={"title": "Renamed", "deadline": "2030-02-02", "assignee_email": "organizer@example.com"})
    t = get_task(app, tid)
    assert (t.title, t.deadline, t.assignee_name) == ("Renamed", "2030-02-02", "Olive Organizer")
    assert client.post(f"/tasks/{tid}/edit", data={"title": ""}).status_code == 400
    assert get_task(app, tid).title == "Renamed"


def test_delete_task(client, app, eid):
    add_task(client, eid)
    tid = task_ids(app, eid)[0]
    client.post(f"/tasks/{tid}/delete")
    assert get_task(app, tid) is None


def test_task_list_filter_and_pending_count(client, app, eid):
    add_task(client, eid, title="Open one"), add_task(client, eid, title="Done one")
    _, done = task_ids(app, eid)
    client.post(f"/tasks/{done}/status", data={"status": "done"})
    assert "Done one" not in client.get("/tasks?status=todo").get_data(as_text=True)
    assert "Done one" in client.get("/tasks?status=done").get_data(as_text=True)
    assert client.get("/tasks?status=bogus").status_code == 200
    assert 'Pending tasks</span><strong>1<' in client.get("/").get_data(as_text=True)


def test_overdue_task_is_flagged(client, eid):
    add_task(client, eid, deadline="2020-01-01")
    assert "overdue" in client.get("/tasks").get_data(as_text=True)


def test_tasks_empty_state(client):
    assert "No tasks yet" in client.get("/tasks").get_data(as_text=True)


def test_admin_sees_all_tasks(client, admin_client, eid):
    add_task(client, eid)
    assert "Book hall" in admin_client.get("/tasks").get_data(as_text=True)


# ---------- saved schedule API ----------
ROWS = [{"time": "09:00", "title": "Registration", "description": "Desk"}, {"time": "10:30", "title": "Talk", "description": ""}]


def test_save_and_replace_schedule(client, app, eid):
    assert client.post(f"/api/events/{eid}/schedule", json={"items": ROWS}).get_json() == {"saved": 2}
    html = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "Registration" in html and 'data-can-manage="true"' in html
    client.post(f"/api/events/{eid}/schedule", json={"items": ROWS[:1]})
    assert sqlite3.connect(app.config["DATABASE"]).execute("SELECT COUNT(*) FROM event_schedule_items").fetchone()[0] == 1
    assert client.post(f"/api/events/{eid}/schedule", json={"items": []}).get_json() == {"saved": 0}


@pytest.mark.parametrize("payload", [
    {"items": [{"time": "25:00", "title": "x"}]}, {"items": [{"time": "09:00", "title": ""}]},
    {"items": [{"time": "09:00", "title": "x" * 121}]}, {"items": "nope"}, {"items": ["str"]},
    {"items": [{"time": "09:00", "title": "t"}] * 31}, [], {},
])
def test_schedule_validation(client, eid, payload):
    assert client.post(f"/api/events/{eid}/schedule", json=payload).status_code == 400


def test_failed_schedule_save_keeps_old_schedule(client, app, eid):
    client.post(f"/api/events/{eid}/schedule", json={"items": ROWS})
    client.post(f"/api/events/{eid}/schedule", json={"items": [{"time": "bad", "title": "x"}]})
    assert sqlite3.connect(app.config["DATABASE"]).execute("SELECT COUNT(*) FROM event_schedule_items").fetchone()[0] == 2


def test_schedule_permissions(client, other, admin_client, app, eid):
    assert other.post(f"/api/events/{eid}/schedule", json={"items": ROWS}).status_code == 404
    assert admin_client.post(f"/api/events/{eid}/schedule", json={"items": ROWS}).status_code == 403  # admins view, owners edit
    set_status(app, eid, "completed")
    assert client.post(f"/api/events/{eid}/schedule", json={"items": ROWS}).status_code == 403
    client.csrf = False
    assert client.post(f"/api/events/{eid}/schedule", json={"items": ROWS}).status_code == 400


def test_admin_sees_schedule_read_only(client, admin_client, eid):
    client.post(f"/api/events/{eid}/schedule", json={"items": ROWS})
    html = admin_client.get(f"/events/{eid}").get_data(as_text=True)
    assert 'data-can-manage="false"' in html and "Registration" in html and 'id="ai-checklist"' not in html


# ---------- bulk checklist -> tasks ----------
def test_bulk_tasks(client, app, eid):
    res = client.post(f"/api/events/{eid}/tasks/bulk", json={"tasks": [{"title": "Get permission", "phase": "before"}, {"title": "Thank guests", "phase": "after"}]})
    assert res.get_json() == {"added": 2}
    t = get_task(app, task_ids(app, eid)[0])
    assert t.phase in ("before", "after") and t.assignee_id is None


@pytest.mark.parametrize("payload", [{"tasks": []}, {"tasks": [{"title": "x", "phase": "never"}]}, {"tasks": [{"title": ""}]},
                                     {"tasks": [{"title": "t"}] * 61}, {"tasks": "x"}, []])
def test_bulk_validation(client, app, eid, payload):
    assert client.post(f"/api/events/{eid}/tasks/bulk", json=payload).status_code == 400
    assert task_ids(app, eid) == []


def test_bulk_permissions(client, other, eid):
    assert other.post(f"/api/events/{eid}/tasks/bulk", json={"tasks": [{"title": "x"}]}).status_code == 404


def test_event_page_shows_ai_buttons_only_to_owner(client, eid):
    html = client.get(f"/events/{eid}").get_data(as_text=True)
    assert 'id="ai-checklist"' in html and "Add task" in html
