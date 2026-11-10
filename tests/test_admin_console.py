"""Admin console: separate admin login, secure admin seeding, dashboard, approval workflow, authorization."""
import re

import pytest

from conftest import PASSWORD, admin_login, login, make_client, make_user
from test_events import EVENT, new_event, row
from test_workflow import inbox, status, submit

ADMIN_PAGES = ["/admin/dashboard", "/admin/event-approvals", "/admin/events", "/admin/students", "/admin/organizers",
               "/admin/venues", "/admin/activity-logs", "/admin/users", "/admin/admins"]
STRONG = "Correct-Horse-42"


def approve(c, eid):
    return c.post(f"/admin/events/{eid}/approve")


def reject(c, eid, note="Budget is too high"):
    return c.post(f"/admin/events/{eid}/reject", data={"note": note})


# ---------- 1. public registration ----------
def test_public_registration_offers_only_student_and_organizer(anon):
    html = anon.get("/register").get_data(as_text=True)
    options = re.findall(r'<option value="([^"]+)"', html)
    assert options == ["student", "organizer"]
    assert "admin" not in html.lower().split("<form")[1].split("</form>")[0]


@pytest.mark.parametrize("role", ["admin", "Admin", "administrator", " admin"])
def test_public_registration_cannot_create_admin(anon, app, role):
    res = anon.post("/register", data={"name": "Mallory", "email": "m@example.com", "password": STRONG,
                                       "confirm_password": STRONG, "role": role})
    assert res.status_code == 400
    from app.models import users
    with app.app_context():
        assert users.get_by_email("m@example.com") is None and not users.admin_exists()


# ---------- 2. secure admin seeding ----------
ENV = {"ADMIN_EMAIL": "root@example.com", "ADMIN_PASSWORD": STRONG, "ADMIN_NAME": "Root Admin"}


def test_seed_admin_command_creates_hashed_admin_from_environment(app):
    res = app.test_cli_runner().invoke(args=["seed-admin"], env=ENV)
    assert res.exit_code == 0 and "created" in res.output
    from app.models import users
    with app.app_context():
        u = users.get_by_email("root@example.com")
        assert u.role == "admin" and u.name == "Root Admin"
        assert STRONG not in u.password_hash and u.password_hash.split(":")[0] in ("scrypt", "pbkdf2")
    c = app.test_client()
    assert admin_login(c, "root@example.com", STRONG).status_code == 302


def test_seed_admin_needs_environment_and_has_no_default_password(app):
    res = app.test_cli_runner().invoke(args=["seed-admin"], env={"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""})
    assert res.exit_code != 0 and "ADMIN_EMAIL" in res.output
    from app.models import users
    with app.app_context():
        assert not users.admin_exists()


@pytest.mark.parametrize("password", ["short1", "onlyletterslong", "password123", "root"])
def test_seed_admin_refuses_weak_passwords(app, password):
    res = app.test_cli_runner().invoke(args=["seed-admin"], env={**ENV, "ADMIN_PASSWORD": password})
    assert res.exit_code != 0
    from app.models import users
    with app.app_context():
        assert not users.admin_exists()


def test_seed_admin_is_idempotent_and_never_resets_a_password(app):
    runner = app.test_cli_runner()
    runner.invoke(args=["seed-admin"], env=ENV)
    again = runner.invoke(args=["seed-admin"], env={**ENV, "ADMIN_PASSWORD": "Another-Pass-77"})
    assert again.exit_code == 0 and "already an admin" in again.output
    assert admin_login(app.test_client(), "root@example.com", STRONG).status_code == 302
    assert admin_login(app.test_client(), "root@example.com", "Another-Pass-77").status_code == 401


def test_seed_admin_will_not_silently_take_over_an_existing_user(app):
    make_user(app, "root@example.com", "Real Student", "student")
    runner = app.test_cli_runner()
    res = runner.invoke(args=["seed-admin"], env=ENV)
    assert res.exit_code != 0 and "--promote" in res.output
    from app.models import users
    with app.app_context():
        assert users.get_by_email("root@example.com").role == "student"
    assert runner.invoke(args=["seed-admin", "--promote"], env=ENV).exit_code == 0
    with app.app_context():
        assert users.get_by_email("root@example.com").role == "admin"


def test_only_admins_create_more_admins(client, student_client, admin_client, app, anon):
    data = {"name": "Second Admin", "email": "admin2@example.com", "password": STRONG, "role": "admin"}
    assert client.post("/admin/users/create", data=data).status_code == 403
    assert student_client.post("/admin/users/create", data=data).status_code == 403
    assert admin_client.post("/admin/users/create", data={**data, "password": "Short1pw"}).status_code == 400  # < 10 chars
    assert admin_client.post("/admin/users/create", data=data).status_code == 302
    assert admin_login(anon, "admin2@example.com", STRONG).status_code == 302
    assert "Second Admin" in admin_client.get("/admin/admins").get_data(as_text=True)


# ---------- 3. separate admin login ----------
def test_student_organizer_and_admin_can_each_log_in(app, anon):
    make_user(app, "s@example.com", "Sam", "student")
    make_user(app, "o@example.com", "Oli", "organizer")
    make_user(app, "a@example.com", "Ann", "admin")
    s, o, a = app.test_client(), app.test_client(), app.test_client()
    assert login(s, "s@example.com").status_code == 302
    assert login(o, "o@example.com").status_code == 302
    res = admin_login(a, "a@example.com")
    assert res.status_code == 302 and res.headers["Location"].endswith("/admin/dashboard")
    assert s.get("/browse").status_code == 200 and o.get("/events").status_code == 200
    assert a.get("/admin/dashboard").status_code == 200


def test_admin_login_page_renders_and_has_its_own_form(anon):
    html = anon.get("/admin/login").get_data(as_text=True)
    assert "Admin sign-in" in html and 'action="/admin/login"' in html and 'name="csrf_token"' in html


def test_student_and_organizer_credentials_do_not_work_on_admin_login(student_client, client, anon):
    for email in ("stu@example.com", "organizer@example.com", "nobody@example.com"):
        res = admin_login(anon, email, PASSWORD)
        assert res.status_code == 401 and "Invalid email or password." in res.get_data(as_text=True)
    assert anon.get("/admin/dashboard").status_code == 302  # still not signed in


def test_admin_credentials_do_not_work_on_the_public_login(app, anon):
    make_user(app, "a@example.com", "Ann", "admin")
    res = login(anon, "a@example.com")
    assert res.status_code == 403 and "admin login page" in res.get_data(as_text=True)
    assert anon.get("/admin/dashboard").status_code == 302  # no session was started


def test_admin_login_wrong_password_and_lockout(app, anon):
    make_user(app, "a@example.com", "Ann", "admin")
    for _ in range(5):
        assert admin_login(anon, "a@example.com", "wrong-password-1").status_code == 401
    assert admin_login(anon, "a@example.com", PASSWORD).status_code == 429


def test_deactivated_admin_cannot_sign_in(app, anon):
    u = make_user(app, "a@example.com", "Ann", "admin")
    from app.models import users
    with app.app_context():
        users.set_active(u.id, False)
    assert admin_login(anon, "a@example.com").status_code == 403


def test_anonymous_admin_urls_redirect_to_admin_login(anon):
    for path in ADMIN_PAGES:
        res = anon.get(path)
        assert res.status_code == 302 and "/admin/login" in res.headers["Location"], path


def test_admin_login_returns_to_the_requested_admin_page_only(app, anon):
    make_user(app, "a@example.com", "Ann", "admin")
    res = admin_login(anon, "a@example.com", next="/admin/events")
    assert res.headers["Location"].endswith("/admin/events")
    other = app.test_client()
    assert admin_login(other, "a@example.com", next="/events").headers["Location"].endswith("/admin/dashboard")
    assert admin_login(app.test_client(), "a@example.com", next="//evil.example").headers["Location"].endswith("/admin/dashboard")


def test_admin_logout_ends_the_session(admin_client):
    res = admin_client.post("/admin/logout")
    assert res.status_code == 302 and res.headers["Location"].endswith("/admin/login")
    assert admin_client.get("/admin/dashboard").status_code == 302


def test_admin_home_redirects_to_admin_dashboard(admin_client):
    assert admin_client.get("/").headers["Location"].endswith("/admin/dashboard")


# ---------- 4. dashboard ----------
def test_admin_dashboard_access_and_sidebar(admin_client):
    res = admin_client.get("/admin/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    for label in ("Overview", "Event Approvals", "All Events", "Students", "Organizers", "Venues", "Activity Logs", "Log out"):
        assert label in html, label
    for href in ("/admin/dashboard", "/admin/event-approvals", "/admin/events", "/admin/students", "/admin/organizers",
                 "/admin/venues", "/admin/activity-logs", "/admin/logout"):
        assert href in html, href
    assert "/budget" not in html and "/ai-studio" not in html and "/events/new" not in html


def test_admin_dashboard_shows_the_six_numbers(client, other, student_client, admin_client, app):
    e1, e2, e3 = new_event(client), new_event(client, name="Second"), new_event(other, name="Third")
    new_event(other, name="Still a draft")
    for c, e in ((client, e1), (client, e2), (other, e3)):
        submit(c, e)
    approve(admin_client, e1)
    reject(admin_client, e2)
    html = admin_client.get("/admin/dashboard").get_data(as_text=True)

    def stat(label):
        return int(re.search(rf"<span>{label}</span><strong>(\d+)</strong>", html).group(1))

    assert (stat("Total students"), stat("Total organizers"), stat("Total events")) == (1, 2, 4)
    assert (stat("Pending approvals"), stat("Approved events"), stat("Rejected events")) == (1, 1, 1)


# ---------- 5/6. authorization ----------
@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_students_and_organizers_cannot_open_admin_pages(student_client, client, admin_client, path):
    assert student_client.get(path).status_code == 403
    assert client.get(path).status_code == 403
    assert admin_client.get(path).status_code == 200


def test_students_and_organizers_cannot_use_admin_actions(student_client, client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    for c in (student_client, client):
        assert c.get(f"/admin/events/{eid}").status_code == 403
        assert approve(c, eid).status_code == 403
        assert reject(c, eid).status_code == 403
        assert c.post("/admin/logout").status_code == 403
        assert c.post("/admin/venues/save", data={"name": "X", "capacity": "5", "cost_per_day": "1"}).status_code == 403
    assert status(app, eid) == "pending"  # nothing changed


def test_approval_actions_need_post_and_csrf(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    assert admin_client.get(f"/admin/events/{eid}/approve").status_code == 405
    assert admin_client.get(f"/admin/events/{eid}/reject").status_code == 405
    admin_client.csrf = False
    assert approve(admin_client, eid).status_code == 400
    assert reject(admin_client, eid).status_code == 400
    assert status(app, eid) == "pending"


def test_unknown_event_is_404_for_admin(admin_client):
    assert admin_client.get("/admin/events/9999").status_code == 404
    assert approve(admin_client, 9999).status_code == 404


def test_admin_cannot_approve_own_event_through_admin_routes(admin_client, app):
    eid = new_event(admin_client)
    submit(admin_client, eid)
    approve(admin_client, eid)
    reject(admin_client, eid)
    assert status(app, eid) == "pending"
    html = admin_client.get(f"/admin/events/{eid}").get_data(as_text=True)
    assert "another admin must review it" in html and f"/admin/events/{eid}/approve" not in html


def test_admin_assigned_to_an_event_cannot_review_it(client, admin_client, app):
    eid = new_event(client)
    client.post(f"/events/{eid}/tasks", data={"title": "Book hall", "deadline": "2030-01-01", "assignee_email": "admin@example.com"})
    submit(client, eid)
    assert approve(admin_client, eid).status_code == 302
    assert status(app, eid) == "pending"
    assert reject(admin_client, eid).status_code == 302 and status(app, eid) == "pending"
    other_admin = make_client(app, "admin2@example.com", "admin", "Second Admin")
    assert approve(other_admin, eid).status_code == 302 and status(app, eid) == "approved"


def test_only_pending_events_can_be_decided(client, admin_client, app):
    eid = new_event(client)  # draft
    approve(admin_client, eid)
    reject(admin_client, eid)
    assert status(app, eid) == "draft"
    submit(client, eid)
    approve(admin_client, eid)
    reject(admin_client, eid, "changed my mind")
    assert status(app, eid) == "approved"


# ---------- 7. approve ----------
def test_submitted_event_is_pending_and_shown_to_admin_with_organizer_details(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    assert status(app, eid) == "pending"
    queue = admin_client.get("/admin/event-approvals").get_data(as_text=True)
    assert "Tech Fest" in queue and "Olive Organizer" in queue and "organizer@example.com" in queue
    detail = admin_client.get(f"/admin/events/{eid}").get_data(as_text=True)
    for text in ("Tech Fest", "Hackathon", "2030-01-15", "Seminar Hall", "A coding contest", "Olive Organizer",
                 "organizer@example.com", "Approve event", "Reject event"):
        assert text in detail, text
    assert "Tech Fest" not in student_client.get("/browse").get_data(as_text=True)


def test_admin_approves_event_and_students_can_see_it(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    res = approve(admin_client, eid)
    assert res.status_code == 302
    e = row(app, eid)
    assert e.status == "approved" and e.reviewed_by and e.reviewed_at and e.admin_note == ""
    assert "Tech Fest" in student_client.get("/browse").get_data(as_text=True)
    assert student_client.get(f"/browse/{eid}").status_code == 200
    assert any("approved" in n["message"] for n in inbox(app, "organizer@example.com"))
    assert "approved" in admin_client.get("/admin/activity-logs").get_data(as_text=True)


# ---------- 8/9. reject ----------
def test_rejection_needs_a_reason(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    for note in ("", "   "):
        res = admin_client.post(f"/admin/events/{eid}/reject", data={"note": note}, follow_redirects=True)
        assert "reason is required" in res.get_data(as_text=True)
    assert admin_client.post(f"/admin/events/{eid}/reject").status_code == 302
    assert status(app, eid) == "pending"


def test_rejection_reason_is_saved_and_shown_to_the_organizer_who_can_edit_and_resubmit(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    assert reject(admin_client, eid, "Budget is too high").status_code == 302
    e = row(app, eid)
    assert (e.status, e.admin_note) == ("rejected", "Budget is too high")
    assert "Tech Fest" not in student_client.get("/browse").get_data(as_text=True)
    # organizer sees it on the dashboard, the event page and in a notification
    assert "Budget is too high" in client.get("/").get_data(as_text=True)
    assert "Budget is too high" in client.get(f"/events/{eid}").get_data(as_text=True)
    assert any("Budget is too high" in n["message"] for n in inbox(app, "organizer@example.com"))
    # edit and resubmit; the old reason stays visible while correcting
    assert client.post(f"/events/{eid}/edit", data={**EVENT, "budget": "10000"}).status_code == 302
    assert "Previously rejected" in client.get(f"/events/{eid}").get_data(as_text=True)
    assert submit(client, eid).status_code == 302 and status(app, eid) == "pending"
    assert approve(admin_client, eid).status_code == 302 and status(app, eid) == "approved"


def test_reasons_are_html_escaped(client, admin_client):
    eid = new_event(client)
    submit(client, eid)
    reject(admin_client, eid, "<script>alert(1)</script>")
    for page in (client.get("/"), client.get(f"/events/{eid}"), admin_client.get("/admin/event-approvals?view=rejected"),
                 admin_client.get(f"/admin/events/{eid}")):
        html = page.get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


# ---------- history, lists ----------
def test_admin_sees_previously_approved_and_rejected_events(client, admin_client, app):
    a, r = new_event(client, name="Approved One"), new_event(client, name="Rejected One")
    submit(client, a); submit(client, r)
    approve(admin_client, a)
    reject(admin_client, r, "Clashes with exams")
    admin_client.get("/admin/dashboard")  # shows (and clears) the one-time flash messages
    approved = admin_client.get("/admin/event-approvals?view=approved").get_data(as_text=True)
    rejected = admin_client.get("/admin/event-approvals?view=rejected").get_data(as_text=True)
    assert "Approved One" in approved and "Rejected One" not in approved
    assert "Rejected One" in rejected and "Clashes with exams" in rejected and "Ada Admin" in rejected
    assert "Approved One" not in admin_client.get("/admin/event-approvals").get_data(as_text=True)  # pending view
    assert admin_client.get("/admin/event-approvals?view=bogus").status_code == 200


def test_review_history_keeps_every_decision(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid); reject(admin_client, eid, "First problem")
    submit(client, eid); approve(admin_client, eid)
    html = admin_client.get(f"/admin/events/{eid}").get_data(as_text=True)
    assert "First problem" in html and "Rejected" in html and "Approved" in html


def test_all_events_page_lists_filters_and_paginates(client, other, admin_client):
    for i in range(14):
        new_event(client, name=f"Bulk {i}")
    new_event(other, name="Other Org Event")
    page1 = admin_client.get("/admin/events").get_data(as_text=True)
    assert "Page 1 of 2" in page1 and "organizer@example.com" in page1
    assert "Other Org Event" in admin_client.get("/admin/events?q=Other+Org").get_data(as_text=True)
    assert "No events match" in admin_client.get("/admin/events?status=approved").get_data(as_text=True)
    assert admin_client.get("/admin/events?page=99&status=bogus&type=bogus").status_code == 200


def test_old_admin_urls_still_work(admin_client):
    assert admin_client.get("/admin/approvals").status_code == 200
    assert admin_client.get("/admin/activity").status_code == 200


# ---------- 10. students only see approved ----------
def test_only_approved_events_appear_in_the_student_dashboard(client, admin_client, student_client, app):
    names = {"draft": "Draft Ev", "pending": "Pending Ev", "rejected": "Rejected Ev", "approved": "Approved Ev"}
    ids = {k: new_event(client, name=v) for k, v in names.items()}
    for k in ("pending", "rejected", "approved"):
        submit(client, ids[k])
    reject(admin_client, ids["rejected"])
    approve(admin_client, ids["approved"])
    for page in ("/", "/browse", "/calendar?month=2030-01"):
        html = student_client.get(page).get_data(as_text=True)
        assert "Approved Ev" in html, page
        for hidden in ("Draft Ev", "Pending Ev", "Rejected Ev"):
            assert hidden not in html, (page, hidden)
    for k in ("draft", "pending", "rejected"):
        assert student_client.get(f"/browse/{ids[k]}").status_code == 404


# ---------- existing flows keep working ----------
def test_existing_event_status_route_still_reviews_and_records_history(client, admin_client, app):
    from app.models import reviews
    eid = new_event(client)
    submit(client, eid)
    admin_client.post(f"/events/{eid}/status", data={"action": "reject", "note": "Via old route"})
    with app.app_context():
        history = reviews.for_event(eid)
    assert [(h["decision"], h["reason"]) for h in history] == [("rejected", "Via old route")]


def test_admin_notification_links_to_the_admin_review_page(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    assert inbox(app, "admin@example.com")[0]["link"] == f"/admin/events/{eid}"


# ---------- upgrading an existing database ----------
def test_review_history_migration_keeps_data_and_backfills(tmp_path, monkeypatch):
    import shutil
    import sqlite3

    from app import db as dbmod

    old = tmp_path / "old_migrations"
    old.mkdir()
    for f in dbmod.MIGRATIONS_DIR.glob("00[1-5]_*.sql"):
        shutil.copy(f, old / f.name)
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", old)
    assert dbmod.run_migrations(path) == 5
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO users (name,email,password_hash,role,created_at) VALUES ('A','a@x.io','h','admin','t'),('O','o@x.io','h','organizer','t')")
    cols = "(owner_id,name,event_type,participants,duration_hours,event_date,status,admin_note,reviewed_by,reviewed_at,created_at,updated_at)"
    conn.execute(f"INSERT INTO events {cols} VALUES (2,'Old approved','Workshop',10,2,'2030-01-01','approved','',1,'2026-01-02T00:00:00+00:00','t','t')")
    conn.execute(f"INSERT INTO events {cols} VALUES (2,'Old rejected','Workshop',10,2,'2030-01-01','rejected','Too costly',1,'2026-01-03T00:00:00+00:00','t','t')")
    conn.execute(f"INSERT INTO events {cols} VALUES (2,'Old draft','Workshop',10,2,'2030-01-01','draft','',NULL,NULL,'t','t')")
    conn.commit(); conn.close()

    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", dbmod.__dict__["Path"](__file__).resolve().parent.parent / "app" / "migrations")
    assert dbmod.run_migrations(path) >= 6
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3 and conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
    rows = conn.execute("SELECT decision, reason FROM event_reviews ORDER BY id").fetchall()
    assert rows == [("approved", ""), ("rejected", "Too costly")]
