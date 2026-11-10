"""Phase 6: task search, error pages, theme/i18n/validation wiring and static-file safety."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import make_client

ROOT = Path(__file__).resolve().parent.parent
STATIC_JS = sorted((ROOT / "app/static/js").glob("*.js"))
BASE = {"name": "E", "event_type": "Hackathon", "description": "", "participants": "50", "budget": "10000",
        "duration_hours": "4", "venue": "", "event_date": "2031-03-10", "start_time": "09:00"}


@pytest.fixture()
def org(app):
    return make_client(app, "org@example.com", "organizer", "Olive Org")


def add_event(c, name):
    res = c.post("/events/new", data={**BASE, "name": name})
    return int(res.headers["Location"].rsplit("/", 1)[1])


def add_task(c, eid, title):
    assert c.post(f"/events/{eid}/tasks", data={"title": title}).status_code == 302


# ---------- task search ----------
def test_task_search_matches_title_and_event_name(org):
    a, b = add_event(org, "Hack Night"), add_event(org, "Art Fair")
    add_task(org, a, "Book projector"); add_task(org, b, "Order paint")
    html = org.get("/tasks?q=projector").get_data(as_text=True)
    assert "Book projector" in html and "Order paint" not in html
    assert "Order paint" in org.get("/tasks?q=art fair").get_data(as_text=True)
    assert "No tasks match your search" in org.get("/tasks?q=zzz").get_data(as_text=True)


def test_task_search_treats_wildcards_literally(org):
    a = add_event(org, "E")
    add_task(org, a, "100% done"); add_task(org, a, "plain task")
    html = org.get("/tasks?q=%25").get_data(as_text=True)
    assert "100% done" in html and "plain task" not in html
    assert "plain task" not in org.get("/tasks?q=_").get_data(as_text=True)  # "_" must not match any character


def test_task_search_is_scoped_to_user_and_combines_with_status(org, other):
    a = add_event(org, "Mine"); add_task(org, a, "secret-token task")
    title = "secret-token task"  # the search box echoes the query, so look for the full task title instead
    assert title not in other.get("/tasks?q=secret-token").get_data(as_text=True)
    assert title in org.get("/tasks?q=secret-token&status=todo").get_data(as_text=True)
    assert title not in org.get("/tasks?q=secret-token&status=done").get_data(as_text=True)


def test_task_search_survives_odd_input(org):
    for q in ("'; DROP TABLE tasks;--", "x" * 500, "%%%", "\\"):
        assert org.get("/tasks", query_string={"q": q}).status_code == 200


# ---------- error pages ----------
def test_404_page_for_people_and_json_for_api(org):
    html = org.get("/no-such-page")
    assert html.status_code == 404 and "Page not found" in html.get_data(as_text=True) and "Go back" in html.get_data(as_text=True)
    api = org.get("/api/no-such")
    assert api.status_code == 404 and api.get_json()["error"]


def test_500_page_hides_details(app, org, monkeypatch):
    from app.models import analytics

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(analytics, "summary", boom)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    res = org.get("/analytics")
    text = res.get_data(as_text=True)
    assert res.status_code == 500 and "Something went wrong" in text and "secret internal detail" not in text and "Traceback" not in text


def test_error_page_works_when_logged_out(anon):
    assert anon.open("/login", method="DELETE").status_code == 405  # an error page rendered without a user


# ---------- templates ----------
def test_layout_wiring(org):
    html = org.get("/").get_data(as_text=True)
    assert 'localStorage.getItem("theme")' in html and "data-theme-toggle" in html          # theme applied before paint
    assert "js/theme.js" in html and "js/app.js" in html and 'class="skip-link"' in html
    assert html.count('data-i18n') >= 10                                                     # nav labels can be translated


def test_auth_pages_have_theme_and_validation(anon):
    for url in ("/login", "/register", "/forgot-password"):
        html = anon.get(url).get_data(as_text=True)
        assert "data-theme-toggle" in html and "data-validate" in html and "js/app.js" in html


def test_forms_opt_in_to_validation(org):
    assert "data-validate" in org.get("/events/new").get_data(as_text=True)
    eid = add_event(org, "E")
    assert "data-validate" in org.get(f"/events/{eid}").get_data(as_text=True)


def test_delete_forms_still_ask_for_confirmation(org):
    eid = add_event(org, "E")
    assert "data-confirm=" in org.get(f"/events/{eid}").get_data(as_text=True)


def test_admin_tables_have_filters(admin_client):
    assert 'data-filter-table="users-table"' in admin_client.get("/admin/users").get_data(as_text=True)
    assert 'data-filter-table="venues-table"' in admin_client.get("/admin/venues").get_data(as_text=True)


# ---------- static files ----------
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("path", STATIC_JS, ids=lambda p: p.name)
def test_js_files_parse(path):
    res = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_every_nav_label_has_a_tamil_translation():
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    labels = set(re.findall(r"\('[a-z_.]+', '([^']+)', 'i-[a-z]+'\)", base))
    js = (ROOT / "app/static/js/app.js").read_text(encoding="utf-8")
    assert len(labels) >= 10
    missing = [l for l in labels | {"Log out", "Skip to content"} if f'"{l}":' not in js]
    assert not missing, f"no Tamil text for: {missing}"


def test_no_secrets_in_static_files():
    for path in (ROOT / "app/static").rglob("*"):
        if path.is_file() and path.suffix in {".js", ".css", ".html"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "gsk_" not in text and "GROQ_API_KEY" not in text and "SECRET_KEY" not in text, path


def test_dark_theme_defines_every_token():
    css = (ROOT / "app/static/css/design-system.css").read_text(encoding="utf-8")
    light = re.search(r":root\{(.*?)\n\}", css, re.S).group(1)
    dark = re.search(r':root\[data-theme="dark"\]\{(.*?)\n\}', css, re.S).group(1)
    names = lambda block: set(re.findall(r"(--[a-z0-9-]+):", block))
    must_change = {"--bg", "--surface", "--surface-2", "--line", "--ink", "--muted", "--topbar", "--ok-bg", "--err-bg", "--warn-bg", "--brand-soft"}
    assert must_change <= names(dark)
    assert {n for n in names(light) if n.startswith("--") and n not in {"--r", "--font", "--navy", "--navy-2", "--brand", "--brand-hover"}} - names(dark) == set()
