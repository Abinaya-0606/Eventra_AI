"""Eventra AI branding: name, tagline, logo and favicon appear on every page; the old EventAI name does not."""
import re
from pathlib import Path

import pytest

from conftest import make_user

ROOT = Path(__file__).resolve().parent.parent
NAME, TAGLINE = "Eventra AI", "Your Smart Event Companion"
APP_PAGES = ["/", "/events", "/calendar", "/analytics", "/tasks", "/ai-studio", "/assistant", "/budget", "/policies", "/about", "/profile"]
AUTH_PAGES = ["/login", "/register", "/forgot-password", "/reset-password/sometoken"]


def visible_text(html):
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def assert_branded(html):
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    assert title.strip().endswith(NAME), title
    text = visible_text(html)
    assert NAME in text and TAGLINE in text
    assert 'href="/static/img/favicon.svg"' in html and "#i-eventra" in html
    assert "eventai" not in html.lower().replace("event ai tools", "") and "smart college events" not in html.lower()


@pytest.mark.parametrize("path", APP_PAGES)
def test_signed_in_pages_are_branded(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert_branded(res.get_data(as_text=True))


@pytest.mark.parametrize("path", AUTH_PAGES)
def test_login_register_and_reset_pages_are_branded(anon, path):
    html = anon.get(path).get_data(as_text=True)
    assert_branded(html)
    assert "auth-brand" in html


def test_admin_pages_are_branded(admin_client):
    for path in ("/admin/users", "/admin/venues"):
        assert_branded(admin_client.get(path).get_data(as_text=True))


def test_error_pages_are_branded(client, anon):
    assert_branded(client.get("/nope").get_data(as_text=True))
    assert_branded(anon.get("/nope").get_data(as_text=True))


def test_footer_and_about_page_use_new_identity(client):
    html = client.get("/about").get_data(as_text=True)
    assert 'class="site-footer"' in html
    text = visible_text(html)
    assert "Eventra AI is an intelligent AI-powered event planning and management platform that helps users organize events efficiently with smart AI assistance." in text


def test_favicon_is_served(anon):
    res = anon.get("/static/img/favicon.svg")
    assert res.status_code == 200 and b"<svg" in res.data


def test_reset_email_is_branded(anon, app):
    make_user(app)
    anon.post("/forgot-password", data={"email": "organizer@example.com"})
    mail = app.extensions["outbox"][-1]
    assert NAME in mail["subject"] and "EventAI" not in mail["subject"] + mail["body"]


def test_no_old_brand_in_source_files():
    """Technical identifiers such as the eventai.db file name are intentionally kept; user-facing code must not use the old name."""
    offenders = []
    for path in list((ROOT / "app").rglob("*")) + [ROOT / "config.py", ROOT / "run.py", ROOT / "render.yaml", ROOT / ".env.example"]:
        if path.is_file() and path.suffix in {".py", ".html", ".css", ".js", ".svg", ".yaml", ".example", ".sql", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            text = text.replace("eventai.db", "")
            if re.search(r"event\s?ai\b(?!\s+tools)", text, re.I) and not re.search(r"eventra", text, re.I):
                offenders.append(str(path.relative_to(ROOT)))
            if "EventAI" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders
