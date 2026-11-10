"""Event approval workflow: draft -> submit -> admin approve/reject -> student visibility, re-approval, notifications."""


from app.models import notifications
from conftest import make_client, make_user
from test_events import EVENT, new_event, row


def status(app, eid):
    return row(app, eid).status


def submit(c, eid):
    return c.post(f"/events/{eid}/status", data={"action": "submit"})


def decide(c, eid, action, note=""):
    return c.post(f"/events/{eid}/status", data={"action": action, "note": note})


def inbox(app, email):
    with app.app_context():
        from app.models import users
        uid = users.get_by_email(email).id
        return [dict(r) for r in notifications.list_for(uid, 1, 50)[0]]


def test_full_happy_path(client, admin_client, student_client, app):
    eid = new_event(client)
    assert status(app, eid) == "draft"
    # drafts are invisible to students
    assert "Tech Fest" not in student_client.get("/browse").get_data(as_text=True)
    assert student_client.get(f"/browse/{eid}").status_code == 404

    assert submit(client, eid).status_code == 302 and status(app, eid) == "pending"
    assert "Tech Fest" not in student_client.get("/browse").get_data(as_text=True)  # still hidden while pending

    assert decide(admin_client, eid, "approve").status_code == 302
    e = row(app, eid)
    assert e.status == "approved" and e.reviewed_by and e.reviewed_at and e.submitted_at
    assert "Tech Fest" in student_client.get("/browse").get_data(as_text=True)
    assert student_client.get(f"/browse/{eid}").status_code == 200


def test_rejection_requires_reason_and_returns_to_organizer(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    decide(admin_client, eid, "reject", note="")
    assert status(app, eid) == "pending"  # no reason -> nothing happens
    decide(admin_client, eid, "reject", note="   ")
    assert status(app, eid) == "pending"
    decide(admin_client, eid, "reject", note="Budget is too high")
    e = row(app, eid)
    assert e.status == "rejected" and e.admin_note == "Budget is too high"
    assert "Budget is too high" in client.get(f"/events/{eid}").get_data(as_text=True)  # organizer sees the reason
    assert "Budget is too high" in client.get("/").get_data(as_text=True)  # ...and on the dashboard tracker
    # correction + resubmission
    assert client.post(f"/events/{eid}/edit", data={**EVENT, "budget": "10000"}).status_code == 302
    assert status(app, eid) == "draft"
    assert submit(client, eid).status_code == 302 and status(app, eid) == "pending"
    decide(admin_client, eid, "approve")
    assert status(app, eid) == "approved" and row(app, eid).admin_note == ""


def test_rejected_event_can_be_resubmitted_directly(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    decide(admin_client, eid, "reject", "Fix the venue")
    submit(client, eid)
    assert status(app, eid) == "pending"


def test_editing_approved_event_requires_reapproval_and_hides_it(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    decide(admin_client, eid, "approve")
    client.post(f"/events/{eid}/edit", data={**EVENT, "name": "Tech Fest 2"})
    assert status(app, eid) == "pending"
    assert "Tech Fest 2" not in student_client.get("/browse").get_data(as_text=True)
    assert any("re-approval" in n["message"] for n in inbox(app, "admin@example.com"))


def test_organizer_cannot_approve_or_reject_own_event(client, app):
    eid = new_event(client)
    submit(client, eid)
    for action in ("approve", "reject"):
        decide(client, eid, action, "x")
        assert status(app, eid) == "pending"


def test_admin_cannot_approve_their_own_event(admin_client, app):
    eid = new_event(admin_client)
    submit(admin_client, eid)
    decide(admin_client, eid, "approve")
    assert status(app, eid) == "pending"
    assert "another admin must review" in admin_client.get("/admin/approvals").get_data(as_text=True)


def test_second_admin_can_approve_admins_event(admin_client, app):
    eid = new_event(admin_client)
    submit(admin_client, eid)
    other_admin = make_client(app, "admin2@example.com", "admin", "Ava Admin")
    decide(other_admin, eid, "approve")
    assert status(app, eid) == "approved"


def test_cannot_skip_states(client, admin_client, app):
    eid = new_event(client)
    decide(admin_client, eid, "approve")  # draft cannot be approved
    assert status(app, eid) == "draft"
    client.post(f"/events/{eid}/status", data={"action": "complete"})
    assert status(app, eid) == "draft"
    client.post(f"/events/{eid}/status", data={"action": "nonsense"})
    assert status(app, eid) == "draft"


def test_other_organizer_cannot_submit_or_touch_event(client, other, app):
    eid = new_event(client)
    assert submit(other, eid).status_code == 404
    assert other.post(f"/events/{eid}/edit", data=EVENT).status_code == 404
    assert other.post(f"/events/{eid}/delete").status_code == 404
    assert status(app, eid) == "draft"


# ---------- notifications ----------
def test_admin_notified_on_submit_organizer_on_decision(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    adm = inbox(app, "admin@example.com")
    assert len(adm) == 1 and adm[0]["kind"] == "approval_request" and "Tech Fest" in adm[0]["message"]
    assert f"/events/{eid}" in adm[0]["link"]
    decide(admin_client, eid, "approve")
    org = inbox(app, "organizer@example.com")
    assert org[0]["kind"] == "approved"
    eid2 = new_event(client, name="Second")
    submit(client, eid2)
    decide(admin_client, eid2, "reject", "Needs a venue")
    org = inbox(app, "organizer@example.com")
    assert org[0]["kind"] == "rejected" and "Needs a venue" in org[0]["message"]


def test_every_admin_is_notified(client, admin_client, app):
    make_user(app, "admin2@example.com", "Ava Admin", "admin")
    submit(client, new_event(client))
    assert len(inbox(app, "admin@example.com")) == 1 and len(inbox(app, "admin2@example.com")) == 1


def test_admin_approvals_queue_actions_redirect_back(client, admin_client, app):
    eid = new_event(client)
    submit(client, eid)
    html = admin_client.get("/admin/approvals").get_data(as_text=True)
    assert "Tech Fest" in html and "Reason for rejection" in html
    res = admin_client.post(f"/events/{eid}/status", data={"action": "approve", "next": "/admin/approvals"})
    assert res.headers["Location"].endswith("/admin/approvals")
    res = admin_client.post(f"/events/{eid}/status", data={"action": "complete", "next": "//evil.example"})
    assert "evil.example" not in res.headers["Location"]  # open-redirect protection


def test_deleting_approved_event_notifies_registered_students(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    decide(admin_client, eid, "approve")
    student_client.post(f"/browse/{eid}/register")
    client.post(f"/events/{eid}/delete")
    assert events_model_count(app) == 0
    assert any("cancelled by the organizer" in n["message"] for n in inbox(app, "stu@example.com"))


def events_model_count(app):
    with app.app_context():
        from app.db import get_db
        return get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0]


def test_reapproval_notifies_registered_students(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    decide(admin_client, eid, "approve")
    student_client.post(f"/browse/{eid}/register")
    client.post(f"/events/{eid}/edit", data={**EVENT, "venue": "Auditorium"})
    decide(admin_client, eid, "approve")
    assert any("was updated by the organizer" in n["message"] for n in inbox(app, "stu@example.com"))


def test_completed_event_notifies_students(client, admin_client, student_client, app):
    eid = new_event(client)
    submit(client, eid)
    decide(admin_client, eid, "approve")
    student_client.post(f"/browse/{eid}/register")
    client.post(f"/events/{eid}/status", data={"action": "complete"})
    assert any("completed" in n["message"] for n in inbox(app, "stu@example.com"))
