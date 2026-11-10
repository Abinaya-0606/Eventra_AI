"""Student registration: approved events only, duplicates, capacity, cancel/re-register, organizer view, CSV."""
import threading

import pytest

from app.models import registrations
from conftest import make_client
from test_events import new_event
from test_workflow import decide, inbox, submit

FUTURE = {"event_date": "2099-05-20"}


@pytest.fixture()
def approved(client, admin_client):
    def make(**over):
        eid = new_event(client, **{**FUTURE, **over})
        submit(client, eid)
        decide(admin_client, eid, "approve")
        return eid
    return make


def regs(app, eid):
    with app.app_context():
        return [dict(r) for r in registrations.for_event(eid)]


def test_register_and_confirmation_notification(approved, student_client, app):
    eid = approved()
    res = student_client.post(f"/browse/{eid}/register")
    assert res.status_code == 302
    assert [r["email"] for r in regs(app, eid)] == ["stu@example.com"]
    n = inbox(app, "stu@example.com")
    assert n[0]["kind"] == "registration" and "Tech Fest" in n[0]["message"]
    assert "Tech Fest" in student_client.get("/my-registrations").get_data(as_text=True)
    assert "Registered" in student_client.get("/browse").get_data(as_text=True)


def test_duplicate_registration_is_prevented(approved, student_client, app):
    eid = approved()
    student_client.post(f"/browse/{eid}/register")
    res = student_client.post(f"/browse/{eid}/register", follow_redirects=True)
    assert "already registered" in res.get_data(as_text=True)
    assert len(regs(app, eid)) == 1
    with app.app_context():  # the database itself refuses duplicates too
        assert registrations.register(eid, regs(app, eid)[0]["user_id"], 5) == registrations.DUPLICATE


def test_capacity_is_enforced(approved, student_client, student2_client, app):
    eid = approved(participants="1")
    student_client.post(f"/browse/{eid}/register")
    res = student2_client.post(f"/browse/{eid}/register", follow_redirects=True)
    assert "full" in res.get_data(as_text=True).lower()
    assert len(regs(app, eid)) == 1
    assert "Full" in student2_client.get("/browse").get_data(as_text=True)
    page = student2_client.get(f"/browse/{eid}").get_data(as_text=True)
    assert "Register for this event" not in page


def test_cancel_frees_seat_and_allows_reregistration(approved, student_client, student2_client, app):
    eid = approved(participants="1")
    student_client.post(f"/browse/{eid}/register")
    student_client.post(f"/registrations/{eid}/cancel")
    assert regs(app, eid) == []
    assert any("cancelled" in n["message"] for n in inbox(app, "stu@example.com"))
    student2_client.post(f"/browse/{eid}/register")  # seat was released
    assert [r["email"] for r in regs(app, eid)] == ["stu2@example.com"]
    student_client.post(f"/browse/{eid}/register")  # full again
    assert len(regs(app, eid)) == 1
    student2_client.post(f"/registrations/{eid}/cancel")
    student_client.post(f"/browse/{eid}/register")  # re-registering reuses the same row
    assert [r["email"] for r in regs(app, eid)] == ["stu@example.com"]


def test_cannot_register_for_unapproved_or_past_events(client, admin_client, student_client, app):
    draft = new_event(client, **FUTURE)
    assert student_client.post(f"/browse/{draft}/register").status_code == 404
    pending = new_event(client, **FUTURE)
    submit(client, pending)
    assert student_client.post(f"/browse/{pending}/register").status_code == 404
    past = new_event(client, event_date="2001-01-01")
    submit(client, past)
    decide(admin_client, past, "approve")
    res = student_client.post(f"/browse/{past}/register", follow_redirects=True)
    assert "already taken place" in res.get_data(as_text=True)
    assert regs(app, past) == []


def test_only_students_can_register(approved, client, other, admin_client, app):
    eid = approved()
    for c in (other, admin_client, client):
        assert c.post(f"/browse/{eid}/register").status_code == 403
    assert regs(app, eid) == []


def test_cannot_cancel_someone_elses_registration(approved, student_client, student2_client, app):
    eid = approved()
    student_client.post(f"/browse/{eid}/register")
    student2_client.post(f"/registrations/{eid}/cancel")
    assert len(regs(app, eid)) == 1


def test_my_registrations_only_shows_own(approved, student_client, student2_client):
    eid = approved()
    student_client.post(f"/browse/{eid}/register")
    assert "Tech Fest" in student_client.get("/my-registrations").get_data(as_text=True)
    assert "Tech Fest" not in student2_client.get("/my-registrations").get_data(as_text=True)


def test_organizer_sees_only_registrations_of_own_events(approved, client, other, admin_client, student_client):
    eid = approved()
    student_client.post(f"/browse/{eid}/register")
    html = client.get(f"/events/{eid}/registrations").get_data(as_text=True)
    assert "Stella Student" in html and "stu@example.com" in html
    assert other.get(f"/events/{eid}/registrations").status_code == 404
    assert other.get(f"/events/{eid}/registrations.csv").status_code == 404
    assert admin_client.get(f"/events/{eid}/registrations").status_code == 200
    assert student_client.get(f"/events/{eid}/registrations").status_code == 403
    assert "Stella Student" in client.get(f"/events/{eid}").get_data(as_text=True)  # preview on the event page


def test_csv_export_and_formula_injection(approved, client, app):
    eid = approved()
    s = make_client(app, "evil@example.com", "student", "=HYPERLINK(\"http://x\")")
    s.post(f"/browse/{eid}/register")
    res = client.get(f"/events/{eid}/registrations.csv")
    assert res.mimetype == "text/csv" and "attachment" in res.headers["Content-Disposition"]
    text = res.get_data(as_text=True)
    assert text.splitlines()[0].startswith("Name,Email")
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text and '"=HYPERLINK' not in text


def test_announcement_reaches_registered_students_only(approved, client, other, student_client, student2_client, app):
    eid = approved()
    student_client.post(f"/browse/{eid}/register")
    assert client.post(f"/events/{eid}/announce", data={"message": "Venue changed to Auditorium"}).status_code == 302
    assert any("Venue changed" in n["message"] for n in inbox(app, "stu@example.com"))
    assert not any("Venue changed" in n["message"] for n in inbox(app, "stu2@example.com"))
    assert other.post(f"/events/{eid}/announce", data={"message": "hi"}).status_code == 404
    assert student_client.post(f"/events/{eid}/announce", data={"message": "hi"}).status_code == 403
    client.post(f"/events/{eid}/announce", data={"message": ""})  # empty message is rejected, nothing sent
    assert len([n for n in inbox(app, "stu@example.com") if n["kind"] == "update"]) == 1


def test_announcement_needs_approved_event(client, app):
    eid = new_event(client, **FUTURE)
    assert client.post(f"/events/{eid}/announce", data={"message": "hi"}).status_code == 403


def test_browse_search_and_filters(client, admin_client, student_client):
    ids = []
    for name, etype, date, venue in [("Alpha Hack", "Hackathon", "2099-03-01", "Lab"),
                                      ("Beta Talk", "Seminar", "2099-04-01", "Auditorium"),
                                      ("Old Fest", "Cultural Fest", "2001-04-01", "Lawn")]:
        eid = new_event(client, name=name, event_type=etype, event_date=date, venue=venue)
        submit(client, eid)
        decide(admin_client, eid, "approve")
        ids.append(eid)
    get = lambda q: student_client.get("/browse?" + q).get_data(as_text=True)
    assert "Alpha Hack" in get("") and "Beta Talk" in get("") and "Old Fest" not in get("")
    assert "Old Fest" in get("past=1")
    assert "Alpha Hack" in get("q=alpha") and "Beta Talk" not in get("q=alpha")
    assert "Beta Talk" in get("q=auditorium") and "Alpha Hack" not in get("q=auditorium")
    assert "Beta Talk" in get("type=Seminar") and "Alpha Hack" not in get("type=Seminar")
    assert "Beta Talk" in get("from=2099-03-15") and "Alpha Hack" not in get("from=2099-03-15")
    assert "Alpha Hack" in get("to=2099-03-15") and "Beta Talk" not in get("to=2099-03-15")
    assert "valid date" in get("from=notadate")
    assert "No events match" in get("q=zzzz")
    assert "No events match" in get("q=%25")  # a literal % is escaped, it is not a wildcard
    assert student_client.get("/browse?page=abc").status_code == 200


def test_browse_seats_available_filter(approved, student_client, student2_client):
    eid = approved(participants="1")
    student_client.post(f"/browse/{eid}/register")
    assert "Tech Fest" in student2_client.get("/browse").get_data(as_text=True)
    assert "Tech Fest" not in student2_client.get("/browse?open=1").get_data(as_text=True)


def test_calendar_for_students_shows_approved_only(client, admin_client, student_client):
    new_event(client, name="Hidden Draft", event_date="2099-05-20")
    eid = new_event(client, name="Public Show", event_date="2099-05-21")
    submit(client, eid)
    decide(admin_client, eid, "approve")
    html = student_client.get("/calendar?month=2099-05").get_data(as_text=True)
    assert "Public Show" in html and "Hidden Draft" not in html
    assert f"/browse/{eid}" in html and f"/events/{eid}" not in html


def test_assistant_lists_upcoming_events_from_database(approved, student_client):
    approved()
    res = student_client.post("/api/chat", json={"question": "What events are upcoming?"})
    d = res.get_json()
    assert res.status_code == 200 and "Tech Fest" in d["answer"] and "seats left" in d["answer"]


def test_concurrent_registration_never_exceeds_capacity(approved, app):
    """Many students race for 2 seats: exactly 2 get in."""
    eid = approved(participants="2")
    students = [make_client(app, f"racer{i}@example.com", "student", f"Racer {i}") for i in range(6)]
    results = []

    def go(c):
        results.append(c.post(f"/browse/{eid}/register").status_code)

    threads = [threading.Thread(target=go, args=(c,)) for c in students]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(regs(app, eid)) == 2
