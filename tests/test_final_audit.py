"""Whole-system guarantees: every route has a role policy, no page crashes for any role, and one full journey."""

import pytest

from app.security import BLUEPRINT_ROLES, PUBLIC_ENDPOINTS, roles_for
from conftest import make_client
from test_events import EVENT, new_event, row
from test_workflow import decide, inbox, submit


def test_every_route_has_a_role_policy(app):
    """A new route in an unknown blueprint would be denied by default; this test makes the omission visible."""
    missing = [r.endpoint for r in app.url_map.iter_rules()
               if r.endpoint != "static" and r.endpoint not in PUBLIC_ENDPOINTS and not roles_for(r.endpoint)]
    assert missing == []
    assert set(BLUEPRINT_ROLES["admin"]) == {"admin"} and set(BLUEPRINT_ROLES["student"]) == {"student"}


def test_unlisted_endpoint_is_denied_by_default():
    assert roles_for("some_new_blueprint.view") is None


def _plain_get_paths(app):
    return sorted({r.rule for r in app.url_map.iter_rules()
                   if "GET" in r.methods and not r.arguments and r.endpoint != "static" and r.endpoint != "auth.logout"
                   and r.endpoint not in PUBLIC_ENDPOINTS and not r.rule.startswith("/api/")})


@pytest.mark.parametrize("role", ["student", "organizer", "admin"])
def test_no_page_crashes_for_any_role(app, role):
    c = make_client(app, f"{role}@smoke.example", role, f"Smoke {role}")
    for path in _plain_get_paths(app):
        assert c.get(path).status_code in (200, 302, 403), f"{role} {path}"


def test_pages_with_ids_render_for_their_audience(client, admin_client, student_client, app):
    eid = new_event(client, event_date="2099-05-20")
    submit(client, eid)
    decide(admin_client, eid, "approve")
    student_client.post(f"/browse/{eid}/register")
    for c, paths in ((client, [f"/events/{eid}", f"/events/{eid}/edit", f"/events/{eid}/registrations", f"/events/{eid}/ai"]),
                     (admin_client, [f"/events/{eid}", f"/events/{eid}/registrations", "/admin/approvals"]),
                     (student_client, [f"/browse/{eid}", "/my-registrations", "/calendar?month=2099-05"])):
        for p in paths:
            assert c.get(p).status_code == 200, p


def test_full_journey_all_three_roles(client, admin_client, student_client, student2_client, app):
    """Organizer drafts -> submits -> admin rejects with reason -> organizer fixes -> admin approves ->
    students register (capacity 2, duplicate, full, cancel) -> organizer sees them and messages them."""
    eid = new_event(client, event_date="2099-06-01", participants="2")
    assert row(app, eid).status == "draft"
    submit(client, eid)
    decide(admin_client, eid, "reject", "Add a venue")
    assert row(app, eid).status == "rejected"
    client.post(f"/events/{eid}/edit", data={**EVENT, "event_date": "2099-06-01", "participants": "2", "venue": "Auditorium"})
    submit(client, eid)
    decide(admin_client, eid, "approve")
    assert row(app, eid).status == "approved"
    assert "Tech Fest" in student_client.get("/browse").get_data(as_text=True)

    student_client.post(f"/browse/{eid}/register")
    assert "already registered" in student_client.post(f"/browse/{eid}/register", follow_redirects=True).get_data(as_text=True)
    student2_client.post(f"/browse/{eid}/register")
    third = make_client(app, "third@example.com", "student", "Third Student")
    assert "full" in third.post(f"/browse/{eid}/register", follow_redirects=True).get_data(as_text=True).lower()
    html = client.get(f"/events/{eid}/registrations").get_data(as_text=True)
    assert "Stella Student" in html and "Stan Student" in html and "Third Student" not in html

    student2_client.post(f"/registrations/{eid}/cancel")
    third.post(f"/browse/{eid}/register")  # the released seat is available again
    client.post(f"/events/{eid}/announce", data={"message": "Bring your ID card"})
    assert any("Bring your ID card" in n["message"] for n in inbox(app, "third@example.com"))
    assert not any("Bring your ID card" in n["message"] for n in inbox(app, "stu2@example.com"))
    kinds = {n["kind"] for n in inbox(app, "organizer@example.com")}
    assert {"rejected", "approved"} <= kinds


def test_capacity_cannot_drop_below_registered(client, admin_client, student_client, app):
    eid = new_event(client, event_date="2099-06-01", participants="5")
    submit(client, eid)
    decide(admin_client, eid, "approve")
    student_client.post(f"/browse/{eid}/register")
    res = client.post(f"/events/{eid}/edit", data={**EVENT, "event_date": "2099-06-01", "participants": "0"})
    assert res.status_code == 400
    res = client.post(f"/events/{eid}/edit", data={**EVENT, "event_date": "2099-06-01", "participants": "1"})
    assert res.status_code == 302 and row(app, eid).participants == 1


def test_security_headers_and_cookie_flags(app, student_client):
    res = student_client.get("/")
    assert res.headers["X-Frame-Options"] == "DENY" and res.headers["X-Content-Type-Options"] == "nosniff"
    assert app.config["SESSION_COOKIE_HTTPONLY"] and app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_no_api_key_or_password_hash_in_any_page(client, admin_client, student_client, app):
    for c in (client, admin_client, student_client):
        for path in ("/", "/profile", "/assistant"):
            text = c.get(path).get_data(as_text=True)
            assert "test-key" not in text and "pbkdf2" not in text and "scrypt" not in text
    assert "GROQ" not in student_client.get("/assistant").get_data(as_text=True)


def test_admin_user_page_never_prints_password_hashes(admin_client):
    assert "pbkdf2" not in admin_client.get("/admin/users").get_data(as_text=True)
