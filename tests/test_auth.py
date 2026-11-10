"""Phase 2: registration, login, sessions, CSRF, password reset, profile, roles, admin, throttle."""
import re
import sqlite3

import pytest

from app.db import run_migrations
from app.models import tokens, users
from conftest import PASSWORD, login, make_user

REGISTER = {"name": "Ravi Kumar", "email": "Ravi@Example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, "role": "organizer", "department": "CSE"}


def count_users(app):
    with app.app_context():
        return len(users.list_users())


# ---------- registration ----------
def test_register_success_logs_in_and_stores_hash(anon, app):
    res = anon.post("/register", data=REGISTER)
    assert res.status_code == 302 and res.headers["Location"].endswith("/")
    assert anon.get("/").status_code == 200  # now logged in
    with app.app_context():
        u = users.get_by_email("ravi@example.com")  # email is normalised to lower-case
        assert u.role == "organizer" and u.department == "CSE"
        assert PASSWORD not in u.password_hash and "$" in u.password_hash  # hashed with a salt


def test_same_password_gets_different_hashes(app):
    a, b = make_user(app, "a@x.com"), make_user(app, "b@x.com")
    assert a.password_hash != b.password_hash


@pytest.mark.parametrize("change,fragment", [
    ({"name": ""}, "required"), ({"email": "not-an-email"}, "valid email"),
    ({"password": "short1", "confirm_password": "short1"}, "at least 8"),
    ({"password": "onlyletters", "confirm_password": "onlyletters"}, "letter and one number"),
    ({"confirm_password": "Different1"}, "do not match"), ({"name": "x" * 81}, "at most 80"),
])
def test_register_validation(anon, app, change, fragment):
    res = anon.post("/register", data={**REGISTER, **change})
    assert res.status_code == 400 and fragment in res.get_data(as_text=True)
    assert count_users(app) == 0


def test_register_duplicate_email_case_insensitive(anon, app):
    make_user(app, "ravi@example.com")
    res = anon.post("/register", data=REGISTER)
    assert res.status_code == 409 and "already exists" in res.get_data(as_text=True)


def test_cannot_self_register_as_admin(anon, app):
    res = anon.post("/register", data={**REGISTER, "role": "admin"})
    assert res.status_code == 400  # "admin" is not an allowed choice
    assert count_users(app) == 0


def test_register_does_not_echo_password(anon):
    html = anon.post("/register", data={**REGISTER, "confirm_password": "x"}).get_data(as_text=True)
    assert PASSWORD not in html


# ---------- login / logout ----------
def test_login_wrong_password_and_unknown_user_look_identical(anon, app):
    make_user(app)
    a = login(anon, password="WrongPass1")
    b = login(anon, "nobody@example.com")
    assert a.status_code == b.status_code == 401
    assert "Invalid email or password." in a.get_data(as_text=True) and "Invalid email or password." in b.get_data(as_text=True)


def test_login_is_case_insensitive_on_email(anon, app):
    make_user(app)
    assert login(anon, "ORGANIZER@example.com").status_code == 302


def test_sql_injection_in_login_is_harmless(anon, app):
    make_user(app)
    assert login(anon, "' OR '1'='1' --", "x").status_code == 401
    assert login(anon, "organizer@example.com'; DROP TABLE users; --").status_code == 401
    assert count_users(app) == 1


def test_logout_requires_post_and_ends_session(client):
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/").status_code == 302  # back to login


@pytest.mark.parametrize("nxt,expected", [("/budget", "/budget"), ("https://evil.com", "/"), ("//evil.com", "/"),
                                          ("/\\evil.com", "/"), ("javascript:alert(1)", "/"), ("evil.com", "/")])
def test_login_next_redirect_is_safe(anon, app, nxt, expected):
    make_user(app)
    loc = login(anon, next=nxt).headers["Location"]
    assert loc == expected  # unsafe targets fall back to the dashboard ("/")


def test_login_page_redirects_when_already_logged_in(client):
    assert client.get("/login").status_code == 302


def test_deactivated_user_cannot_log_in_and_is_kicked_out(client, app, admin_client):
    with app.app_context():
        uid = users.get_by_email("organizer@example.com").id
    assert client.get("/budget").status_code == 200
    admin_client.post(f"/admin/users/{uid}/active")
    assert client.get("/budget").status_code == 302  # existing session no longer works
    assert login(app.test_client()).status_code == 403


def test_brute_force_lockout(anon, app):
    make_user(app)
    for _ in range(5):
        assert login(anon, password="WrongPass1").status_code == 401
    assert login(anon, password="WrongPass1").status_code == 429
    assert login(anon).status_code == 429  # even the right password is blocked during the lockout
    assert login(app.test_client(), "other@example.com").status_code == 401  # other accounts unaffected


def test_successful_login_resets_failure_count(anon, app):
    make_user(app)
    for _ in range(4):
        login(anon, password="WrongPass1")
    assert login(anon).status_code == 302


# ---------- the app-wide login gate ----------
@pytest.mark.parametrize("path", ["/", "/ai-studio", "/assistant", "/budget", "/policies", "/about", "/profile", "/admin/users"])
def test_pages_redirect_anonymous_users_to_login(anon, path):
    res = anon.get(path)
    assert res.status_code == 302 and "/login" in res.headers["Location"]


@pytest.mark.parametrize("path", ["/api/chat", "/api/budget", "/api/ai/plan", "/api/ai/letter"])
def test_api_returns_401_json_for_anonymous(anon, path):
    res = anon.post(path, json={})
    assert res.status_code == 401 and res.get_json()["error"]


def test_redirect_keeps_the_page_you_wanted(anon):
    assert anon.get("/budget").headers["Location"] == "/login?next=/budget"


def test_public_pages_open_without_login(anon):
    for path in ("/login", "/register", "/forgot-password"):
        assert anon.get(path).status_code == 200


def test_unknown_url_for_anonymous_is_a_plain_404_page(anon):
    res = anon.get("/nothing-here")
    assert res.status_code == 404 and "Go to login" in res.get_data(as_text=True)


# ---------- CSRF ----------
def test_post_without_csrf_token_is_rejected(client):
    client.csrf = False
    res = client.post("/api/budget", json={"venue": "seminar_hall", "participants": 5,
                                           "refreshments": False, "participation_kits": False})
    assert res.status_code == 400 and "security token" in res.get_json()["error"]


def test_post_with_wrong_csrf_token_is_rejected(client):
    client.csrf = False
    res = client.post("/api/budget", json={}, headers={"X-CSRF-Token": "forged"})
    assert res.status_code == 400


def test_forms_reject_missing_token_and_accept_hidden_field(anon, app):
    anon.csrf = False
    anon.get("/login")  # creates the session token
    assert login(anon, "a@b.com").status_code == 400
    with anon.session_transaction() as s:
        token = s["_csrf"]
    make_user(app)
    assert anon.post("/login", data={"email": "organizer@example.com", "password": PASSWORD, "csrf_token": token}).status_code == 302


def test_every_form_contains_a_csrf_field(anon, client):
    for path in ("/login", "/register", "/forgot-password"):
        assert 'name="csrf_token"' in anon.get(path).get_data(as_text=True)
    assert 'name="csrf_token"' in client.get("/profile").get_data(as_text=True)


# ---------- sessions & cookies ----------
def test_session_cookie_flags(anon, app):
    make_user(app)
    cookie = login(anon).headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_login_replaces_pre_login_session(anon, app):
    make_user(app)
    anon.get("/login")
    with anon.session_transaction() as s:
        s["planted"] = "x"
    login(anon)
    with anon.session_transaction() as s:
        assert "planted" not in s and "uid" in s


# ---------- forgot / reset password ----------
def reset_link(app):
    mail = app.extensions["outbox"][-1]
    return re.search(r"http://localhost(/reset-password/\S+)", mail["body"]).group(1)


def test_forgot_password_sends_link_and_same_answer_for_unknown_email(anon, app):
    make_user(app)
    a = anon.post("/forgot-password", data={"email": "organizer@example.com"}, follow_redirects=True)
    b = anon.post("/forgot-password", data={"email": "ghost@example.com"}, follow_redirects=True)
    msg = "If an account exists for that email"
    assert msg in a.get_data(as_text=True) and msg in b.get_data(as_text=True)
    assert len(app.extensions["outbox"]) == 1 and app.extensions["outbox"][0]["to"] == "organizer@example.com"


def test_reset_flow_end_to_end_and_token_is_single_use(anon, app):
    make_user(app)
    anon.post("/forgot-password", data={"email": "organizer@example.com"})
    link = reset_link(app)
    assert anon.get(link).status_code == 200
    res = anon.post(link, data={"password": "NewPassw0rd", "confirm_password": "NewPassw0rd"})
    assert res.status_code == 302
    assert login(anon, password=PASSWORD).status_code == 401  # old password dead
    assert login(anon, password="NewPassw0rd").status_code == 302
    assert anon.get(link).status_code == 400  # token already used
    assert anon.post(link, data={"password": "Another1pass", "confirm_password": "Another1pass"}).status_code == 400


def test_reset_validation_keeps_token_usable(anon, app):
    make_user(app)
    anon.post("/forgot-password", data={"email": "organizer@example.com"})
    link = reset_link(app)
    assert anon.post(link, data={"password": "weak", "confirm_password": "weak"}).status_code == 400
    assert anon.post(link, data={"password": "NewPassw0rd", "confirm_password": "NewPassw0rd"}).status_code == 302


def test_reset_token_expires(anon, app):
    user = make_user(app)
    with app.app_context():
        raw = tokens.create_reset_token(user.id, -1)  # already expired
        assert not tokens.is_valid(raw) and tokens.consume(raw) is None
    assert anon.get(f"/reset-password/{raw}").status_code == 400


def test_bad_tokens(anon):
    for t in ("garbage", "a" * 43):
        assert anon.get(f"/reset-password/{t}").status_code == 400


def test_new_request_cancels_older_token_and_only_hash_is_stored(app):
    user = make_user(app)
    with app.app_context():
        first = tokens.create_reset_token(user.id, 30)
        second = tokens.create_reset_token(user.id, 30)
        assert not tokens.is_valid(first) and tokens.is_valid(second)
        rows = [r[0] for r in sqlite3.connect(app.config["DATABASE"]).execute("SELECT token_hash FROM password_reset_tokens")]
        assert second not in rows and len(rows) == 1


def test_password_reset_signs_out_other_devices(app):
    make_user(app)
    laptop, phone = app.test_client(), app.test_client()
    login(laptop), login(phone)
    laptop.post("/profile/password", data={"current_password": PASSWORD, "new_password": "NewPassw0rd", "confirm_password": "NewPassw0rd"})
    assert laptop.get("/budget").status_code == 200  # this device stays logged in
    assert phone.get("/budget").status_code == 302  # the other one is signed out


# ---------- profile ----------
def test_profile_update(client, app):
    res = client.post("/profile", data={"name": "New Name", "department": "ECE", "language": "ta"})
    assert res.status_code == 302
    with app.app_context():
        u = users.get_by_email("organizer@example.com")
        assert (u.name, u.department, u.language) == ("New Name", "ECE", "ta")
    html = client.get("/profile?saved=1").get_data(as_text=True)
    assert 'data-lang="ta"' in html and 'localStorage.setItem("lang", "ta")' in html
    assert 'localStorage.setItem("lang"' not in client.get("/profile").get_data(as_text=True)


def test_profile_validation(client):
    assert client.post("/profile", data={"name": "", "language": "en"}).status_code == 400
    assert client.post("/profile", data={"name": "A", "language": "fr"}).status_code == 400


def test_change_password_checks_current_password(client):
    res = client.post("/profile/password", data={"current_password": "wrong", "new_password": "NewPassw0rd", "confirm_password": "NewPassw0rd"})
    assert res.status_code == 400 and "current password is not correct" in res.get_data(as_text=True)


def test_profile_page_escapes_html_in_name(client):
    client.post("/profile", data={"name": "<script>alert(1)</script>", "language": "en"})
    html = client.get("/profile").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


# ---------- roles & admin ----------
def test_students_cannot_open_admin_pages(client):
    assert client.get("/admin/users").status_code == 403
    assert client.post("/admin/users/1/role", data={"role": "admin"}).status_code == 403


def test_admin_sees_users_and_nav_link(admin_client):
    html = admin_client.get("/admin/users").get_data(as_text=True)
    assert "admin@example.com" in html
    assert "/admin/users" in admin_client.get("/admin/dashboard").get_data(as_text=True)


def test_student_nav_has_no_admin_link(client):
    assert "/admin/users" not in client.get("/").get_data(as_text=True)


def test_admin_can_change_role(admin_client, app):
    target = make_user(app, "t@example.com")
    admin_client.post(f"/admin/users/{target.id}/role", data={"role": "organizer"})
    with app.app_context():
        assert users.get_by_id(target.id).role == "organizer"


def test_admin_cannot_use_invalid_role_or_edit_self(admin_client, app):
    target = make_user(app, "t@example.com", role="student")
    admin_client.post(f"/admin/users/{target.id}/role", data={"role": "superuser"})
    with app.app_context():
        me = users.get_by_email("admin@example.com")
        assert users.get_by_id(target.id).role == "student"
    admin_client.post(f"/admin/users/{me.id}/role", data={"role": "student"})
    admin_client.post(f"/admin/users/{me.id}/active")
    with app.app_context():
        me = users.get_by_id(me.id)
        assert me.role == "admin" and me.is_active


def test_admin_unknown_user_is_handled(admin_client):
    assert admin_client.post("/admin/users/999/role", data={"role": "student"}).status_code == 302


def test_create_admin_cli(app):
    runner = app.test_cli_runner()
    res = runner.invoke(args=["create-admin", "--email", "boss@example.com", "--name", "Boss", "--password", PASSWORD])
    assert res.exit_code == 0, res.output
    with app.app_context():
        assert users.get_by_email("boss@example.com").role == "admin"
    bad = runner.invoke(args=["create-admin", "--email", "nope", "--name", "B", "--password", PASSWORD])
    assert bad.exit_code != 0


def test_cli_promotes_existing_user(app):
    make_user(app, "s@example.com")
    app.test_cli_runner().invoke(args=["create-admin", "--email", "s@example.com", "--name", "S", "--password", PASSWORD])
    with app.app_context():
        assert users.get_by_email("s@example.com").role == "admin"


# ---------- database ----------
def test_migrations_are_idempotent(tmp_path):
    path = str(tmp_path / "m.db")
    v1 = run_migrations(path)
    assert run_migrations(path) == v1 >= 1
    tables = {r[0] for r in sqlite3.connect(path).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "password_reset_tokens"} <= tables


def test_database_rejects_invalid_role(app):
    with pytest.raises(sqlite3.IntegrityError):
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.execute("INSERT INTO users (name,email,password_hash,role,created_at) VALUES ('a','a@a.com','x','root','now')")


def test_production_requires_secret_key(monkeypatch):
    from app import create_app
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app("production")


# ---------- logout button + back-button safety ----------
def test_logout_button_rendered_in_sidebar_user_box(client):
    html = client.get("/").get_data(as_text=True)
    box = html[html.index('class="user-box"'):html.index("</aside>")]
    assert 'action="/logout"' in box and 'name="csrf_token"' in box and "Log out" in box


def test_logout_redirects_to_login_and_blocks_protected_pages(client):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/").get_data(as_text=True)).group(1)
    res = client.post("/logout", data={"csrf_token": token})
    assert res.status_code == 302 and "/login" in res.headers["Location"]
    back = client.get("/")  # what the Back button triggers once the cache is bypassed
    assert back.status_code == 302 and "/login" in back.headers["Location"]


def test_logout_requires_post_and_csrf(client):
    assert client.get("/logout").status_code == 405
    client.csrf = False  # the CSRF check must still protect logout
    assert client.post("/logout").status_code == 400
    assert client.get("/").status_code == 200  # still logged in


def test_pages_are_not_cacheable(client):
    cc = client.get("/").headers["Cache-Control"]
    assert "no-store" in cc
