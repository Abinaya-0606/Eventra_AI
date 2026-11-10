"""Phase 5: analytics numbers, dashboard page and PDF reports."""
import json
import re

import pytest

from app.models import analytics, events
from tests.conftest import make_client

BASE = {"name": "E", "event_type": "Hackathon", "description": "", "participants": "50", "budget": "10000",
        "duration_hours": "4", "venue": "", "event_date": "2031-03-10", "start_time": "09:00"}


def add(c, **kw):
    res = c.post("/events/new", data={**BASE, **kw})
    assert res.status_code == 302
    return int(res.headers["Location"].rsplit("/", 1)[1])


@pytest.fixture()
def org(app):
    return make_client(app, "org@example.com", "organizer", "Olive Org")


def state(html):
    return json.loads(re.search(r'id="analytics-data">(.*?)</script>', html, re.S).group(1))


def set_status(app, eid, status):
    with app.app_context():
        events.set_status(eid, status)


def test_summary_numbers(org, app):
    a = add(org, name="A", event_date="2031-03-10", budget="10000", participants="50")
    b = add(org, name="B", event_date="2031-03-20", budget="5000", participants="20", event_type="Workshop")
    c = add(org, name="C", event_date="2031-07-01", budget="99999", participants="500")
    add(org, name="OtherYear", event_date="2032-01-01")
    set_status(app, a, "completed"); set_status(app, b, "pending"); set_status(app, c, "rejected")
    d = state(org.get("/analytics?year=2031").get_data(as_text=True))
    t = d["totals"]
    assert t["events"] == 3 and t["completed"] == 1 and t["pending"] == 1
    assert t["budget"] == 15000 and t["participants"] == 70  # rejected event is not counted
    assert d["monthly"][2]["events"] == 2 and d["monthly"][2]["budget"] == 15000 and d["monthly"][6]["events"] == 1
    assert {x["label"]: x["count"] for x in d["types"]} == {"Hackathon": 2, "Workshop": 1}
    assert {x["key"]: x["count"] for x in d["status"]}["rejected"] == 1


def test_comparison_and_categories_use_saved_breakdown(org, app):
    a = add(org, name="A", budget="10000")
    add(org, name="B", budget="2000")
    org.post(f"/api/events/{a}/budget", json={"items": {"venue": 3000, "food": 4000}})
    d = state(org.get("/analytics?year=2031").get_data(as_text=True))
    comp = {c["name"]: c for c in d["comparison"]}
    assert comp["A"]["planned"] == 7000 and comp["B"]["planned"] is None
    assert [c["name"] for c in d["comparison"]][0] == "A"  # biggest budget first
    cats = {c["key"]: c["amount"] for c in d["categories"]}
    assert cats["venue"] == 3000 and cats["food"] == 4000 and cats["guest"] == 0


def test_task_counts(org):
    a = add(org)
    org.post(f"/events/{a}/tasks", data={"title": "T1"})
    tk = state(org.get("/analytics?year=2031").get_data(as_text=True))["tasks"]
    assert sum(tk.values()) == 1


def test_scoping_users_and_admin(org, other, admin_client):
    add(org, name="Mine")
    add(other, name="Theirs", budget="777")
    mine = state(org.get("/analytics?year=2031").get_data(as_text=True))
    assert mine["totals"]["events"] == 1 and mine["totals"]["budget"] == 10000
    everyone = state(admin_client.get("/analytics?year=2031").get_data(as_text=True))
    assert everyone["totals"]["events"] == 2 and everyone["totals"]["budget"] == 10777


def test_year_handling(org):
    add(org, event_date="2031-01-05")
    html = org.get("/analytics?year=2031").get_data(as_text=True)
    assert '<option value="2031" selected>' in html
    from datetime import date
    now = f'<option value="{date.today().year}" selected>'
    for bad in ("abc", "1", "99999", "-5", "2031;drop"):
        res = org.get(f"/analytics?year={bad}")
        assert res.status_code == 200 and now in res.get_data(as_text=True)  # falls back to this year
    assert "No events in" in org.get("/analytics?year=2040").get_data(as_text=True)


def test_empty_state_has_no_chart_scripts(org):
    html = org.get("/analytics").get_data(as_text=True)
    assert "No events in" in html and "chart.umd" not in html


def test_page_has_chart_canvases_and_fallback_tables(org):
    add(org)
    html = org.get("/analytics?year=2031").get_data(as_text=True)
    for key in ("monthly", "budget", "types", "status", "compare", "categories"):
        assert f'id="chart-{key}"' in html
    assert "View as table" in html and "chart.js@4.4.1" in html


def test_event_names_are_escaped(org):
    add(org, name="<script>alert(1)</script>")
    html = org.get("/analytics?year=2031").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html


def test_login_required(anon):
    for url in ("/analytics", "/analytics/report.pdf", "/events/1/report.pdf"):
        assert anon.get(url).status_code in (302, 401)


def test_analytics_pdf(org):
    add(org)
    res = org.get("/analytics/report.pdf?year=2031")
    assert res.status_code == 200 and res.data.startswith(b"%PDF") and "attachment" in res.headers["Content-Disposition"]
    assert org.get("/analytics/report.pdf?year=2040").data.startswith(b"%PDF")  # empty year still works


def test_event_report_pdf_and_permissions(org, other, admin_client):
    eid = add(org, name="Café ₹ தமிழ்")
    org.post(f"/events/{eid}/tasks", data={"title": "Book hall"})
    org.post(f"/api/events/{eid}/budget", json={"items": {"venue": 1000}})
    res = org.get(f"/events/{eid}/report.pdf")
    assert res.status_code == 200 and res.data.startswith(b"%PDF")
    assert admin_client.get(f"/events/{eid}/report.pdf").status_code == 200
    assert other.get(f"/events/{eid}/report.pdf").status_code == 404
    assert org.get("/events/9999/report.pdf").status_code == 404


def test_years_always_include_current(app):
    class U:
        is_admin, id = True, 1
    with app.app_context():
        assert analytics.years(U())  # at least the current year
