"""Final: health check, security headers, proxy handling and the optional first-admin bootstrap."""
import pytest

from app import create_app
from app.models import users

GOOD = {"ADMIN_EMAIL": "boss@example.com", "ADMIN_PASSWORD": "Str0ng!Passw0rd", "ADMIN_NAME": "Boss"}


def make(tmp_path, **extra):
    return create_app("testing", {"DATABASE": str(tmp_path / "t.db"), **extra})


def test_healthz_is_public_and_minimal(anon):
    res = anon.get("/healthz")
    assert res.status_code == 200 and res.get_json() == {"status": "ok"}


def test_healthz_reports_database_failure(app, anon, monkeypatch):
    import app.blueprints.main.routes as routes

    class Broken:
        def execute(self, *a):
            raise RuntimeError("db down details")
    monkeypatch.setattr(routes, "get_db", lambda: Broken())
    res = anon.get("/healthz")
    assert res.status_code == 503 and "details" not in res.get_data(as_text=True)


def test_security_headers_everywhere(anon, client):
    for c, url in ((anon, "/login"), (client, "/"), (anon, "/nope")):
        h = c.get(url).headers
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY" and "Referrer-Policy" in h
    assert "Strict-Transport-Security" not in anon.get("/login").headers  # only over https in production


def test_hsts_in_production_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    app = create_app("production", {"DATABASE": str(tmp_path / "p.db")})
    assert "max-age" in app.test_client().get("/login").headers["Strict-Transport-Security"]


def test_proxy_headers_only_trusted_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    hdr = {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"}
    seen = {}
    for name, overrides in (("trusted", {}), ("untrusted", {"TRUST_PROXY": False})):
        app = create_app("production", {"DATABASE": str(tmp_path / f"{name}.db"), **overrides})

        @app.before_request
        def grab(name=name):
            from flask import request
            seen[name] = (request.remote_addr, request.scheme)
        app.test_client().get("/healthz", headers=hdr)
    assert seen["trusted"] == ("203.0.113.7", "https")
    assert seen["untrusted"][0] != "203.0.113.7"


def test_bootstrap_admin_created_once(tmp_path):
    app = make(tmp_path, **GOOD)
    with app.app_context():
        admin = users.get_by_email("boss@example.com")
        assert admin and admin.role == "admin" and admin.name == "Boss"
    again = make(tmp_path, **{**GOOD, "ADMIN_PASSWORD": "An0ther!Passw0rd"})  # second start: nothing changes
    with again.app_context():
        assert users.verify_password(users.get_by_email("boss@example.com"), "Str0ng!Passw0rd")


def test_bootstrap_skipped_when_an_admin_exists(tmp_path):
    app = make(tmp_path)
    with app.app_context():
        users.create_user("Existing", "old@example.com", "Str0ng!Passw0rd", role="admin")
    app = make(tmp_path, **GOOD)
    with app.app_context():
        assert users.get_by_email("boss@example.com") is None


@pytest.mark.parametrize("bad", [{"ADMIN_PASSWORD": "short"}, {"ADMIN_EMAIL": "not-an-email"}, {"ADMIN_PASSWORD": ""}, {"ADMIN_EMAIL": ""}])
def test_bootstrap_ignores_bad_settings_without_crashing(tmp_path, bad):
    app = make(tmp_path, **{**GOOD, **bad})
    with app.app_context():
        assert not users.admin_exists()


def test_bootstrapped_admin_can_log_in(tmp_path):
    app = make(tmp_path, **GOOD)
    c = app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "t"
    res = c.post("/admin/login", data={"email": "boss@example.com", "password": GOOD["ADMIN_PASSWORD"], "csrf_token": "t"})
    assert res.status_code == 302 and c.get("/admin/users").status_code == 200


@pytest.mark.parametrize("url", ["/login", "/register", "/forgot-password", "/reset-password/sometoken"])
def test_head_requests_are_not_treated_as_form_submissions(anon, url):
    """Monitors and link previews send HEAD. It must behave like GET and must not count as a failed login."""
    assert anon.head(url).status_code == anon.get(url).status_code != 405
    for _ in range(8):  # more than MAX_FAILED_LOGINS
        anon.head("/login")
    assert anon.get("/login").status_code == 200


def test_head_on_edit_pages_behaves_like_get(client):
    res = client.post("/events/new", data={"name": "E", "event_type": "Hackathon", "description": "", "participants": "5",
                                           "budget": "100", "duration_hours": "1", "venue": "", "event_date": "2031-01-01", "start_time": "09:00"})
    eid = res.headers["Location"].rsplit("/", 1)[1]
    assert client.head("/events/new").status_code == 200 and client.head(f"/events/{eid}/edit").status_code == 200
