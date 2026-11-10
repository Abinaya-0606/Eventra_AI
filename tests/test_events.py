"""Phase 3: events - create/edit/delete, access control, status workflow, list/search, dashboard, calendar."""
import html as htmllib
import re
import sqlite3

import pytest

from app.models import events as events_model
from app.models import users

EVENT = {"name": "Tech Fest", "event_type": "Hackathon", "description": "A coding contest", "participants": "100",
         "budget": "25000", "duration_hours": "6", "venue": "Seminar Hall", "event_date": "2030-01-15",
         "start_time": "09:00"}


def new_event(client, **over):
    res = client.post("/events/new", data={**EVENT, **over})
    assert res.status_code == 302, res.get_data(as_text=True)[:300]
    return int(re.search(r"/events/(\d+)", res.headers["Location"]).group(1))


def row(app, event_id):
    with app.app_context():
        return events_model.get(event_id)


def set_status(app, event_id, status):
    sqlite3.connect(app.config["DATABASE"]).execute("UPDATE events SET status=? WHERE id=?", (status, event_id)).connection.commit()


# ---------- create ----------
def test_create_event_saves_draft_and_logs_activity(client, app):
    eid = new_event(client)
    e = row(app, eid)
    assert (e.name, e.status, e.participants, e.budget, e.event_date) == ("Tech Fest", "draft", 100, 25000.0, "2030-01-15")
    assert 'Created event "Tech Fest"' in htmllib.unescape(client.get("/").get_data(as_text=True))
    assert "Tech Fest" in client.get("/events").get_data(as_text=True)


@pytest.mark.parametrize("change,fragment", [
    ({"name": ""}, "required"), ({"event_type": "Party"}, "invalid"), ({"participants": "0"}, "between 1"),
    ({"participants": "ten"}, "whole number"), ({"budget": "-1"}, "valid amount"), ({"event_date": "15-01-2030"}, "valid date"),
    ({"event_date": ""}, "required"), ({"event_date": "1999-01-01"}, "2000 and 2100"), ({"start_time": "25:00"}, "time"),
    ({"duration_hours": "100"}, "between 1"), ({"name": "x" * 101}, "at most 100"),
])
def test_create_event_validation(client, app, change, fragment):
    res = client.post("/events/new", data={**EVENT, **change})
    assert res.status_code == 400 and fragment in res.get_data(as_text=True)
    with app.app_context():
        assert events_model.search(users.get_by_email("organizer@example.com"))[1] == 0


def test_create_form_keeps_values_after_error(client):
    html = client.post("/events/new", data={**EVENT, "participants": "0"}).get_data(as_text=True)
    assert 'value="Tech Fest"' in html


def test_new_event_form_loads(client):
    assert client.get("/events/new").status_code == 200


# ---------- access control ----------
def test_users_cannot_see_each_others_events(client, other, admin_client):
    eid = new_event(client)
    assert other.get(f"/events/{eid}").status_code == 404
    assert other.get(f"/events/{eid}/edit").status_code == 404
    assert other.post(f"/events/{eid}/delete").status_code == 404
    assert other.post(f"/events/{eid}/status", data={"action": "submit"}).status_code == 404
    assert "Tech Fest" not in other.get("/events").get_data(as_text=True)
    assert admin_client.get(f"/events/{eid}").status_code == 200  # admins can see everything


def test_unknown_event_is_404(client):
    assert client.get("/events/9999").status_code == 404


def test_admin_list_shows_all_events_with_owner(client, admin_client):
    new_event(client)
    html = admin_client.get("/events").get_data(as_text=True)
    assert "Tech Fest" in html and "Olive Organizer" in html


# ---------- edit / delete ----------
def test_owner_can_edit_draft(client, app):
    eid = new_event(client)
    assert client.post(f"/events/{eid}/edit", data={**EVENT, "name": "Renamed", "budget": "999"}).status_code == 302
    assert (row(app, eid).name, row(app, eid).budget, row(app, eid).status) == ("Renamed", 999.0, "draft")
    assert 'value="Renamed"' in client.get(f"/events/{eid}/edit").get_data(as_text=True)


def test_edit_validation_error_keeps_event_unchanged(client, app):
    eid = new_event(client)
    assert client.post(f"/events/{eid}/edit", data={**EVENT, "name": ""}).status_code == 400
    assert row(app, eid).name == "Tech Fest"


def test_pending_and_completed_events_are_locked(client, app):
    eid = new_event(client)
    for status in ("pending", "completed"):
        set_status(app, eid, status)
        assert client.get(f"/events/{eid}/edit").status_code == 302
        client.post(f"/events/{eid}/edit", data={**EVENT, "name": "Hacked"})
        assert row(app, eid).name == "Tech Fest"


def test_editing_approved_event_needs_reapproval_and_rejected_goes_to_draft(client, app):
    eid = new_event(client)
    set_status(app, eid, "approved")
    client.post(f"/events/{eid}/edit", data={**EVENT, "name": "Changed"})
    assert row(app, eid).status == "pending"
    set_status(app, eid, "rejected")
    client.post(f"/events/{eid}/edit", data={**EVENT, "name": "Fixed"})
    assert row(app, eid).status == "draft"


def test_admin_cannot_edit_someone_elses_event(client, admin_client, app):
    eid = new_event(client)
    admin_client.post(f"/events/{eid}/edit", data={**EVENT, "name": "Admin edit"})
    assert row(app, eid).name == "Tech Fest"


def test_delete_removes_event_and_its_children(client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/tasks", data={"title": "T1"})
    client.post(f"/api/events/{eid}/schedule", json={"items": [{"time": "09:00", "title": "Open"}]})
    assert client.post(f"/events/{eid}/delete").status_code == 302
    con = sqlite3.connect(app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM event_schedule_items").fetchone()[0] == 0
    assert client.get(f"/events/{eid}").status_code == 404
    assert 'Deleted event "Tech Fest"' in htmllib.unescape(client.get("/").get_data(as_text=True))  # history survives


def test_admin_can_delete_any_event(client, admin_client, app):
    eid = new_event(client)
    admin_client.post(f"/events/{eid}/delete")
    assert row(app, eid) is None


def test_delete_requires_csrf(client):
    eid = new_event(client)
    client.csrf = False
    assert client.post(f"/events/{eid}/delete").status_code == 400
    assert client.get(f"/events/{eid}").status_code == 200


# ---------- status workflow ----------
def test_full_approval_workflow(client, admin_client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    assert row(app, eid).status == "pending"
    admin_client.post(f"/events/{eid}/status", data={"action": "approve"})
    assert row(app, eid).status == "approved"
    client.post(f"/events/{eid}/status", data={"action": "complete"})
    assert row(app, eid).status == "completed"


def test_reject_needs_reason_then_owner_can_fix_and_resubmit(client, admin_client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    admin_client.post(f"/events/{eid}/status", data={"action": "reject", "note": ""})
    assert row(app, eid).status == "pending"  # no reason -> refused
    admin_client.post(f"/events/{eid}/status", data={"action": "reject", "note": "Budget too high"})
    e = row(app, eid)
    assert (e.status, e.admin_note) == ("rejected", "Budget too high")
    assert "Budget too high" in client.get(f"/events/{eid}").get_data(as_text=True)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    assert row(app, eid).status == "pending"


def test_withdraw_returns_to_draft(client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    client.post(f"/events/{eid}/status", data={"action": "withdraw"})
    assert row(app, eid).status == "draft"


@pytest.mark.parametrize("start,action", [("draft", "approve"), ("draft", "complete"), ("pending", "complete"),
                                          ("approved", "submit"), ("completed", "submit"), ("draft", "bogus")])
def test_invalid_transitions_are_ignored(client, app, start, action):
    eid = new_event(client)
    set_status(app, eid, start)
    client.post(f"/events/{eid}/status", data={"action": action})
    assert row(app, eid).status == start


def test_owner_cannot_approve_or_reject_own_event(client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    for action in ("approve", "reject"):
        client.post(f"/events/{eid}/status", data={"action": action, "note": "x"})
        assert row(app, eid).status == "pending"


def test_admin_cannot_approve_their_own_event(admin_client, app):
    eid = new_event(admin_client)
    admin_client.post(f"/events/{eid}/status", data={"action": "submit"})
    admin_client.post(f"/events/{eid}/status", data={"action": "approve"})
    assert row(app, eid).status == "pending"


def test_only_owner_completes(client, admin_client, app):
    eid = new_event(client)
    set_status(app, eid, "approved")
    admin_client.post(f"/events/{eid}/status", data={"action": "complete"})
    assert row(app, eid).status == "approved"


def test_buttons_shown_match_permissions(client, admin_client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    owner_html = client.get(f"/events/{eid}").get_data(as_text=True)
    admin_html = admin_client.get(f"/events/{eid}").get_data(as_text=True)
    assert "Withdraw" in owner_html and "Approve" not in owner_html
    assert "Approve" in admin_html and 'value="reject"' in admin_html and "Withdraw" not in admin_html


# ---------- list, search, filters ----------
def test_search_and_filters(client, app):
    new_event(client, name="Alpha Workshop", event_type="Workshop", venue="Auditorium")
    b = new_event(client, name="Beta Hack", event_type="Hackathon", venue="Lab")
    set_status(app, b, "approved")
    get = lambda qs: client.get("/events?" + qs).get_data(as_text=True)  # noqa: E731
    assert "Alpha" in get("q=alpha") and "Beta" not in get("q=alpha")
    assert "Alpha" in get("q=auditor") and "Beta" not in get("q=auditor")  # venue search too
    assert "Beta" in get("status=approved") and "Alpha" not in get("status=approved")
    assert "Alpha" in get("type=Workshop") and "Beta" not in get("type=Workshop")
    assert "No events match" in get("q=zzzz")


def test_search_treats_percent_and_underscore_literally(client):
    new_event(client, name="100% Fun")
    new_event(client, name="Plain Event")
    html = client.get("/events?q=%25").get_data(as_text=True)
    assert "100% Fun" in html and "Plain Event" not in html


def test_search_is_safe_against_sql_injection(client):
    new_event(client)
    res = client.get("/events?q=' OR 1=1 --&status=x'; DROP TABLE events; --")
    assert res.status_code == 200
    assert "Tech Fest" in client.get("/events").get_data(as_text=True)


def test_pagination(client):
    for i in range(12):
        new_event(client, name=f"Event {i:02d}", event_date=f"2030-02-{i + 1:02d}")
    page1 = client.get("/events").get_data(as_text=True)
    page2 = client.get("/events?page=2").get_data(as_text=True)
    assert "Page 1 of 2" in page1 and "12 events" in page1 and "Event 11" in page1 and "Event 00" not in page1
    assert "Event 00" in page2 and "Event 11" not in page2
    assert client.get("/events?page=abc").status_code == 200 and client.get("/events?page=-3").status_code == 200


def test_empty_state(client):
    assert "Create your first event" in client.get("/events").get_data(as_text=True)


# ---------- dashboard ----------
def test_dashboard_stats(client, app):
    a = new_event(client, budget="10000", event_date="2030-01-01")                      # upcoming draft
    b = new_event(client, budget="5000", event_date="2020-01-01")                       # past, will be completed
    c = new_event(client, budget="7000", event_date="2030-03-01")                       # rejected: excluded from budget
    set_status(app, b, "completed")
    set_status(app, c, "rejected")
    client.post(f"/events/{a}/tasks", data={"title": "Open task"})
    client.post(f"/events/{a}/tasks", data={"title": "Other task"})
    with app.app_context():
        s = events_model.stats(users.get_by_email("organizer@example.com"))
    assert s == {"total": 3, "completed": 1, "awaiting_approval": 0, "upcoming": 1, "budget": 15000.0}
    html = client.get("/").get_data(as_text=True)
    assert "₹15,000" in html and "Open task" in html and "Upcoming events" in html


def test_dashboard_empty_state(client):
    html = client.get("/").get_data(as_text=True)
    assert "No upcoming events" in html and "all caught up" in html and "Your activity will appear here" in html


def test_dashboard_numbers_are_per_user(client, other):
    new_event(client)
    assert "₹25,000" in client.get("/").get_data(as_text=True)
    assert "₹25,000" not in other.get("/").get_data(as_text=True)


def test_admin_dashboard_counts_everything_and_highlights_approvals(client, admin_client):
    eid = new_event(client)
    client.post(f"/events/{eid}/status", data={"action": "submit"})
    html = admin_client.get("/admin/dashboard").get_data(as_text=True)
    assert "Pending approvals" in html and "stat attention" in html
    assert "submitted for approval" in html  # admin sees everyone's activity


def test_activity_feed_is_private(client, other):
    new_event(client, name="Secret Plan")
    assert "Secret Plan" not in other.get("/").get_data(as_text=True)


# ---------- calendar ----------
def test_calendar_shows_event_in_its_month(client):
    new_event(client, name="Jan Event", event_date="2030-01-15")
    jan = client.get("/calendar?month=2030-01").get_data(as_text=True)
    feb = client.get("/calendar?month=2030-02").get_data(as_text=True)
    assert "Jan Event" in jan and "January 2030" in jan and "Jan Event" not in feb
    assert "month=2029-12" in jan and "month=2030-02" in jan  # prev / next links


def test_calendar_is_private_and_admin_sees_all(client, other, admin_client):
    new_event(client, name="Mine Only")
    assert "Mine Only" not in other.get("/calendar?month=2030-01").get_data(as_text=True)
    assert "Mine Only" in admin_client.get("/calendar?month=2030-01").get_data(as_text=True)


@pytest.mark.parametrize("month", ["garbage", "2030-13", "1999-01", "2030-1", ""])
def test_calendar_bad_month_falls_back(client, month):
    assert client.get(f"/calendar?month={month}").status_code == 200


def test_calendar_handles_leap_february_and_december(client):
    new_event(client, name="Leap Day", event_date="2028-02-29")
    assert "Leap Day" in client.get("/calendar?month=2028-02").get_data(as_text=True)
    assert "month=2031-01" in client.get("/calendar?month=2030-12").get_data(as_text=True)


# ---------- XSS ----------
def test_user_text_is_escaped_everywhere(client):
    evil = '<script>alert(1)</script>'
    eid = new_event(client, name=evil, venue='"><img src=x onerror=alert(2)>', event_date="2030-01-10")
    client.post(f"/events/{eid}/tasks", data={"title": evil})
    for path in (f"/events/{eid}", "/events", "/", "/calendar?month=2030-01", "/tasks"):
        html = client.get(path).get_data(as_text=True)
        assert evil not in html, path
        assert "<img src=x" not in html, path


def test_name_with_quotes_cannot_break_the_json_data_attribute(client):
    eid = new_event(client, name="O'Reilly \"Meet\" </script>")
    html = client.get(f"/events/{eid}").get_data(as_text=True)
    assert "</script>'" not in html and "O'Reilly" not in html.split('data-event=')[1].split(">")[0]
