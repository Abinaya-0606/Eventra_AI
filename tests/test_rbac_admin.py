"""Role-based access control (backend), admin dashboard/tools, notifications inbox, dashboards per role, CSRF."""
import html as html_lib

import pytest

from conftest import login, make_user
from test_events import EVENT, new_event
from test_workflow import decide, inbox, submit

ORGANIZER_ONLY_GET = ["/events", "/events/new", "/analytics", "/analytics/report.pdf", "/ai-studio", "/budget"]
ADMIN_ONLY_GET = ["/admin/users", "/admin/organizers", "/admin/students", "/admin/approvals", "/admin/activity", "/admin/venues"]


@pytest.mark.parametrize("path", ORGANIZER_ONLY_GET)
def test_students_blocked_from_organizer_pages(student_client, path):
    assert student_client.get(path).status_code == 403


@pytest.mark.parametrize("path", ORGANIZER_ONLY_GET)
def test_organizer_pages_work_for_organizers(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ADMIN_ONLY_GET)
def test_admin_pages_blocked_for_students_and_organizers(student_client, client, admin_client, path):
    assert student_client.get(path).status_code == 403
    assert client.get(path).status_code == 403
    assert admin_client.get(path).status_code == 200


@pytest.mark.parametrize("path", ADMIN_ONLY_GET + ORGANIZER_ONLY_GET + ["/browse", "/notifications", "/"])
def test_anonymous_is_redirected_to_login(anon, path):
    res = anon.get(path)
    assert res.status_code == 302 and "/login" in res.headers["Location"]


def test_students_blocked_from_organizer_api(student_client, client):
    eid = new_event(client)
    assert student_client.post("/api/ai/schedule", json={}).status_code == 403
    assert student_client.post(f"/api/events/{eid}/ai/venues", json={}).status_code == 403
    assert student_client.post(f"/api/events/{eid}/schedule", json={"items": []}).status_code == 403
    assert student_client.post("/events/new", data=EVENT).status_code == 403
    assert student_client.get(f"/events/{eid}").status_code == 403
    assert student_client.get(f"/events/{eid}/report.pdf").status_code == 403
    assert student_client.post(f"/events/{eid}/status", data={"action": "submit"}).status_code == 403


def test_organizers_blocked_from_student_and_admin_actions(client, other):
    eid = new_event(client)
    assert other.post("/admin/users/create", data={"name": "x"}).status_code == 403
    assert other.post("/admin/users/1/role", data={"role": "admin"}).status_code == 403
    assert client.get("/my-registrations").status_code == 403
    assert client.post(f"/registrations/{eid}/cancel").status_code == 403


def test_students_can_use_assistant_calendar_profile_policies(student_client):
    for path in ("/assistant", "/calendar", "/profile", "/policies", "/about", "/notifications", "/browse", "/my-registrations", "/"):
        assert student_client.get(path).status_code == 200, path


def test_role_cannot_be_escalated_through_registration_or_profile(anon, app, student_client):
    res = anon.post("/register", data={"name": "Mallory", "email": "m@example.com", "password": "Passw0rd!x",
                                       "confirm_password": "Passw0rd!x", "role": "admin"})
    assert res.status_code == 400
    student_client.post("/profile", data={"name": "Stella", "department": "CSE", "language": "en", "role": "admin"})
    assert student_client.get("/admin/users").status_code == 403


def test_post_without_csrf_token_is_rejected(student_client, client):
    client.csrf = False
    assert client.post("/events/new", data=EVENT).status_code == 400
    student_client.csrf = False
    assert student_client.post("/browse/1/register").status_code == 400
    assert student_client.post("/notifications/read-all").status_code == 400


def test_deactivated_user_loses_access_immediately(student_client, admin_client, app):
    from app.models import users
    with app.app_context():
        sid = users.get_by_email("stu@example.com").id
    admin_client.post(f"/admin/users/{sid}/active")
    assert student_client.get("/browse").status_code == 302


# ---------- dashboards ----------
def test_each_role_gets_its_own_dashboard_and_navigation(client, student_client, admin_client):
    s = student_client.get("/").get_data(as_text=True)
    assert "Find your next event" in s and "/browse" in s and "/my-registrations" in s
    assert "/events/new" not in s and "/analytics" not in s and "/admin/users" not in s and "/ai-studio" not in s
    o = client.get("/").get_data(as_text=True)
    assert "Approval tracker" in o and "/ai-studio" in o and "/budget" in o and "/analytics" in o
    assert "/browse" not in o and "/admin/users" not in o
    assert admin_client.get("/").headers["Location"].endswith("/admin/dashboard")  # admins land on their own console
    a = admin_client.get("/admin/dashboard").get_data(as_text=True)
    assert "Total users" in a and "/admin/event-approvals" in a and "/admin/activity-logs" in a and "/admin/venues" in a
    assert "/budget" not in a and "/ai-studio" not in a


def test_admin_dashboard_numbers(client, other, student_client, admin_client, app):
    e1 = new_event(client)
    e2 = new_event(client, name="Second")
    e3 = new_event(other, name="Third")
    submit(client, e1); submit(client, e2); submit(other, e3)
    decide(admin_client, e1, "approve")
    decide(admin_client, e2, "reject", "no")
    from app.models import events, users
    with app.app_context():
        by_role, by_status = users.counts_by_role(), events.counts_by_status()
    assert by_role == {"organizer": 2, "student": 1, "admin": 1}
    assert by_status == {"approved": 1, "rejected": 1, "pending": 1}
    html = admin_client.get("/admin/dashboard").get_data(as_text=True)
    for label in ("Total users", "Total students", "Total organizers", "Total events", "Pending approvals",
                  "Approved events", "Rejected events"):
        assert label in html


def test_organizer_tracker_counts_only_own_events(client, other, admin_client):
    e = new_event(client)
    submit(client, e)
    new_event(other)
    html = client.get("/").get_data(as_text=True)
    assert "Pending approval" in html
    from re import findall
    pending_tile = findall(r'<span>Pending approval</span><strong>(\d+)</strong>', html)
    assert pending_tile and all(n == "1" for n in pending_tile)


# ---------- admin tools ----------
def test_admin_creates_user_and_logs_it(admin_client, app, anon):
    res = admin_client.post("/admin/users/create", data={"name": "New Org", "email": "neworg@example.com",
                            "password": "Passw0rd!x", "role": "organizer", "department": "ECE"})
    assert res.status_code == 302
    assert login(anon, "neworg@example.com").status_code == 302
    assert "Created an organizer account" in admin_client.get("/admin/activity").get_data(as_text=True)
    assert "neworg@example.com" in admin_client.get("/admin/organizers").get_data(as_text=True)
    assert "neworg@example.com" not in admin_client.get("/admin/students").get_data(as_text=True)


@pytest.mark.parametrize("data,msg", [
    ({"name": "", "email": "a@example.com", "password": "Passw0rd!x", "role": "student"}, "required"),
    ({"name": "A", "email": "bad", "password": "Passw0rd!x", "role": "student"}, "valid email"),
    ({"name": "A", "email": "a@example.com", "password": "short", "role": "student"}, "at least 8"),
    ({"name": "A", "email": "a@example.com", "password": "Passw0rd!x", "role": "root"}, "invalid value"),
    ({"name": "A", "email": "admin@example.com", "password": "Passw0rd!x", "role": "student"}, "already exists"),
])
def test_admin_create_user_validation(admin_client, app, data, msg):
    res = admin_client.post("/admin/users/create", data=data, follow_redirects=True)
    assert msg in res.get_data(as_text=True)
    from app.models import users
    with app.app_context():
        assert len(users.list_users()) == 1


def test_admin_role_change_goes_back_to_same_list_and_is_logged(admin_client, app):
    s = make_user(app, "s1@example.com", "S One", "student")
    res = admin_client.post(f"/admin/users/{s.id}/role", data={"role": "organizer", "next": "/admin/students"})
    assert res.headers["Location"].endswith("/admin/students")
    assert "Changed the role of S One to organizer" in admin_client.get("/admin/activity").get_data(as_text=True)


def test_user_lists_show_counts(admin_client, client, student_client, app):
    new_event(client)
    html = admin_client.get("/admin/organizers").get_data(as_text=True)
    assert "organizer@example.com" in html and "stu@example.com" not in html


def test_activity_log_search_and_pagination(admin_client, client):
    for i in range(30):
        new_event(client, name=f"Event number {i}")
    html = admin_client.get("/admin/activity").get_data(as_text=True)
    assert "Page 1 of 2" in html
    assert "Event number 7" in admin_client.get("/admin/activity?q=number+7").get_data(as_text=True)
    assert "No activity found" in admin_client.get("/admin/activity?q=zzzzzz").get_data(as_text=True)
    assert admin_client.get("/admin/activity?page=99").status_code == 200


def test_venue_management_still_works_and_is_logged(admin_client):
    res = admin_client.post("/admin/venues/save", data={"name": "Open Lawn", "capacity": "500", "cost_per_day": "1000"})
    assert res.status_code == 302
    assert "Open Lawn" in admin_client.get("/admin/venues").get_data(as_text=True)
    assert 'Added venue "Open Lawn"' in html_lib.unescape(admin_client.get("/admin/activity").get_data(as_text=True))


def unread(app, email):
    from app.models import notifications, users
    with app.app_context():
        return notifications.unread_count(users.get_by_email(email).id)


# ---------- notifications inbox ----------
def test_notification_inbox_flow(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    html = admin_client.get("/notifications").get_data(as_text=True)
    assert "submitted" in html and 'class="nav-count"' in html
    nid = inbox(app, "admin@example.com")[0]["id"]
    res = admin_client.post(f"/notifications/{nid}/read")
    assert res.status_code == 302 and res.headers["Location"].endswith(f"/events/{eid}")
    assert admin_client.get("/notifications?unread=1").get_data(as_text=True).count("approval request") == 0
    submit(client, new_event(client, name="Another"))
    assert unread(app, "admin@example.com") == 1
    admin_client.post("/notifications/read-all")
    assert unread(app, "admin@example.com") == 0


def test_cannot_read_someone_elses_notification(client, admin_client, app):
    submit(client, new_event(client))
    nid = inbox(app, "admin@example.com")[0]["id"]
    assert client.post(f"/notifications/{nid}/read").status_code == 404
    assert inbox(app, "admin@example.com")[0]["is_read"] == 0
    assert "submitted" not in client.get("/notifications").get_data(as_text=True)


def test_notification_text_is_escaped(client, admin_client, app):
    submit(client, new_event(client, name="<script>alert(1)</script>"))
    html = admin_client.get("/notifications").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
