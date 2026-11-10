"""Phase 4: budget optimizer, venues, risks, improvements, proposal + PDF. The LLM is mocked."""
import pytest

from app.models import planning
from app.services import insights, llm, pdf
from tests.conftest import make_client

EVENT = {"name": "CodeSprint", "event_type": "Hackathon", "description": "A coding contest.", "participants": "80",
         "budget": "20000", "duration_hours": "6", "venue": "Seminar Hall", "event_date": "2030-05-10", "start_time": "09:00"}

BUDGET_OUT = {"allocations": [{"category": c, "percent": p, "note": "n"} for c, p in
                              [("venue", 15), ("food", 30), ("decoration", 10), ("equipment", 15), ("guest", 10), ("transportation", 10), ("emergency", 10)]]}
RISKS_OUT = {"risks": [{"category": "budget", "title": "Cost overrun", "likelihood": "high", "impact": "high", "prevention": "Track."},
                       {"category": "x", "title": "Rain", "likelihood": "bogus", "impact": "low", "prevention": "Tent."},
                       {"category": "venue", "title": "Minor", "likelihood": "low", "impact": "low", "prevention": "Check."}]}
PROPOSAL_OUT = {"introduction": "Intro", "objectives": ["A", "B"], "description": "Desc", "target_participants": "Students",
                "required_resources": ["Projector"], "committee": [{"role": "Lead", "responsibilities": "All"}],
                "expected_outcomes": ["Skills"]}


def mock(monkeypatch, result=None, error=None):
    seen = {}

    def fake(system, user, *, language="en", **kw):
        seen.update(system=system, user=user, language=language)
        if error:
            raise error
        return result
    monkeypatch.setattr(llm, "complete_json", fake)
    return seen


@pytest.fixture()
def org(app):
    return make_client(app, "org@example.com", "organizer", "Olive Org")


@pytest.fixture()
def eid(org):
    res = org.post("/events/new", data=EVENT)
    return int(res.headers["Location"].rsplit("/", 1)[1])


# ---------- pure logic ----------
def test_normalise_scales_down_over_100_and_fills_missing():
    items = insights.normalise_allocations([{"category": "venue", "percent": 80}, {"category": "food", "percent": 80},
                                            {"category": "bogus", "percent": 50}, {"category": "guest", "percent": -5}], 10000)
    assert [i["category"] for i in items] == list(insights.BUDGET_CATEGORIES)
    assert sum(i["amount"] for i in items) <= 10000.01
    assert items[0]["amount"] == 5000 and next(i for i in items if i["category"] == "guest")["amount"] == 0


def test_normalise_handles_garbage():
    assert all(i["amount"] == 0 for i in insights.normalise_allocations("nope", 500))
    assert insights.normalise_allocations([{"category": "venue", "percent": "abc"}], 500)[0]["amount"] == 0


def test_score_venues_excludes_small_and_orders(app):
    with app.app_context():
        c, ex = insights.score_venues(planning.list_venues(), 150, 20000, ["projector"])
    assert [x["name"] for x in c] == ["Auditorium"] and ex[0]["name"] == "Seminar Hall"


def test_severity():
    assert insights.severity("high", "high") == "high" and insights.severity("low", "low") == "low"
    assert insights.severity("medium", "medium") == "medium"


# ---------- budget ----------
def test_budget_generate_does_not_save(org, eid, monkeypatch, app):
    mock(monkeypatch, BUDGET_OUT)
    d = org.post(f"/api/events/{eid}/ai/budget", json={}).get_json()
    assert d["total"] == 20000 and d["remaining"] == 0 and d["within_budget"]
    with app.app_context():
        assert planning.get_budget_items(eid) == {}


def test_budget_save_roundtrip_and_validation(org, eid, app):
    ok = org.post(f"/api/events/{eid}/budget", json={"items": {"venue": 3000, "food": "5000.5"}})
    assert ok.status_code == 200 and ok.get_json()["total"] == 8000.5
    with app.app_context():
        assert planning.get_budget_items(eid)["food"] == 5000.5 and len(planning.get_budget_items(eid)) == 7
    assert org.post(f"/api/events/{eid}/budget", json={"items": {"venue": -1}}).status_code == 400
    assert org.post(f"/api/events/{eid}/budget", json={"items": {"venue": "abc"}}).status_code == 400
    assert org.post(f"/api/events/{eid}/budget", json={"items": []}).status_code == 400


def test_standalone_budget_endpoint(client, monkeypatch):
    mock(monkeypatch, BUDGET_OUT)
    body = {"event_type": "Hackathon", "participants": 50, "budget": 10000, "duration_hours": 4}
    assert client.post("/api/ai/budget", json=body).get_json()["total"] == 10000
    assert client.post("/api/ai/budget", json={**body, "budget": "-1"}).status_code == 400


def test_budget_empty_ai_answer_is_error(org, eid, monkeypatch):
    mock(monkeypatch, {"allocations": []})
    assert org.post(f"/api/events/{eid}/ai/budget", json={}).status_code == 502


# ---------- venues ----------
def test_venues_rank_ignores_invented_ids(org, eid, monkeypatch):
    mock(monkeypatch, {"ranking": [{"id": 999, "reason": "fake"}, {"id": 2, "reason": "Big"}, {"id": 1, "reason": "Cosy"}]})
    d = org.post(f"/api/events/{eid}/ai/venues", json={"facilities": ["projector"]}).get_json()
    assert {v["id"] for v in d["recommendations"]} == {1, 2} and "availab" in d["disclaimer"].lower()


def test_venues_none_fit_skips_ai(org, monkeypatch):
    seen = mock(monkeypatch, {"ranking": []})
    res = org.post("/events/new", data={**EVENT, "participants": "5000"})
    eid = int(res.headers["Location"].rsplit("/", 1)[1])
    d = org.post(f"/api/events/{eid}/ai/venues", json={}).get_json()
    assert d["recommendations"] == [] and d["message"] and "user" not in seen


def test_venues_rejects_unknown_facility(org, eid, monkeypatch):
    mock(monkeypatch, {"ranking": []})
    assert org.post(f"/api/events/{eid}/ai/venues", json={"facilities": ["jacuzzi"]}).status_code == 400
    assert org.post(f"/api/events/{eid}/ai/venues", json={"facilities": "projector"}).status_code == 400


# ---------- risks / improve ----------
def test_risks_sorted_and_validated(org, eid, monkeypatch):
    mock(monkeypatch, RISKS_OUT)
    d = org.post(f"/api/events/{eid}/ai/risks", json={}).get_json()
    assert d["risks"][0]["title"] == "Cost overrun" and d["risks"][0]["severity"] == "high"
    assert next(r for r in d["risks"] if r["title"] == "Rain")["likelihood"] == "medium"
    assert d["overall"] == "high" and any(a["title"] == "No tasks planned" for a in d["alerts"])


def test_risk_results_are_saved_and_shown(org, eid, monkeypatch):
    mock(monkeypatch, RISKS_OUT)
    org.post(f"/api/events/{eid}/ai/risks", json={})
    assert "Cost overrun" in org.get(f"/events/{eid}/ai").get_data(as_text=True)


def test_improve(org, eid, monkeypatch):
    mock(monkeypatch, {"suggestions": [{"area": "Publicity", "suggestion": "Posters", "benefit": "Reach"}, {"area": "x"}]})
    d = org.post(f"/api/events/{eid}/ai/improve", json={}).get_json()
    assert len(d["suggestions"]) == 1
    mock(monkeypatch, {"suggestions": []})
    assert org.post(f"/api/events/{eid}/ai/improve", json={}).status_code == 502


def test_llm_error_passes_through(org, eid, monkeypatch):
    mock(monkeypatch, error=llm.LLMError("Busy", 429))
    res = org.post(f"/api/events/{eid}/ai/risks", json={})
    assert res.status_code == 429 and res.get_json()["error"] == "Busy"


# ---------- proposal + pdf ----------
def test_proposal_uses_live_schedule_and_budget(org, eid, monkeypatch):
    mock(monkeypatch, PROPOSAL_OUT)
    org.post(f"/api/events/{eid}/schedule", json={"items": [{"time": "09:00", "title": "Registration", "description": ""}]})
    org.post(f"/api/events/{eid}/budget", json={"items": {"venue": 3000, "food": 7000}})
    d = org.post(f"/api/events/{eid}/ai/proposal", json={}).get_json()
    assert d["schedule"][0]["time_label"] == "09:00 AM" and d["budget"]["total"] == 10000
    assert d["cover"]["organizer"] == "Olive Org"


def test_proposal_without_breakdown_uses_event_budget(org, eid, monkeypatch):
    mock(monkeypatch, PROPOSAL_OUT)
    d = org.post(f"/api/events/{eid}/ai/proposal", json={}).get_json()
    assert d["budget"]["source"] == "event_budget" and d["budget"]["total"] == 20000


def test_proposal_incomplete_ai_answer(org, eid, monkeypatch):
    mock(monkeypatch, {**PROPOSAL_OUT, "committee": []})
    assert org.post(f"/api/events/{eid}/ai/proposal", json={}).status_code == 502


def test_pdf_download(org, eid, monkeypatch, admin_client):
    assert org.get(f"/events/{eid}/proposal.pdf").status_code == 404  # nothing generated yet
    mock(monkeypatch, PROPOSAL_OUT)
    org.post(f"/api/events/{eid}/ai/proposal", json={})
    res = org.get(f"/events/{eid}/proposal.pdf")
    assert res.status_code == 200 and res.mimetype == "application/pdf" and res.data.startswith(b"%PDF")
    assert "attachment" in res.headers["Content-Disposition"]
    assert admin_client.get(f"/events/{eid}/proposal.pdf").status_code == 200  # admins may view


def test_pdf_survives_odd_text():
    view = {"cover": {"title": "A <b>& ₹ தமிழ்", "event_type": "T", "date": "d", "start_time": "s", "venue": "v", "participants": 1,
                      "duration_hours": 1, "organizer": "O", "department": "", "college": "", "status": "draft"},
            "introduction": "x", "objectives": ["<i>y"], "description": "z", "target_participants": "t", "schedule": [],
            "budget": {"lines": [{"label": "L", "amount": 1.5}], "total": 1.5, "source": "breakdown"},
            "required_resources": ["r"], "committee": [{"role": "r", "responsibilities": "p"}], "expected_outcomes": ["o"]}
    assert pdf.build_proposal_pdf(view).startswith(b"%PDF")


# ---------- permissions ----------
def test_other_user_cannot_see_or_generate(other, eid, monkeypatch):
    mock(monkeypatch, RISKS_OUT)
    for url in (f"/events/{eid}/ai", f"/events/{eid}/proposal.pdf"):
        assert other.get(url).status_code == 404
    for p in ("ai/risks", "ai/improve", "ai/budget", "ai/venues", "ai/proposal"):
        assert other.post(f"/api/events/{eid}/{p}", json={}).status_code == 404
    assert other.post(f"/api/events/{eid}/budget", json={"items": {}}).status_code == 404


def test_admin_can_view_but_not_generate(admin_client, eid, monkeypatch):
    mock(monkeypatch, RISKS_OUT)
    assert admin_client.get(f"/events/{eid}/ai").status_code == 200
    assert admin_client.post(f"/api/events/{eid}/ai/risks", json={}).status_code == 403
    assert admin_client.post(f"/api/events/{eid}/budget", json={"items": {}}).status_code == 403


def test_completed_event_is_read_only(org, eid, admin_client, monkeypatch, app):
    from app.models import events
    with app.app_context():
        events.set_status(eid, "completed")
    mock(monkeypatch, RISKS_OUT)
    assert org.post(f"/api/events/{eid}/ai/risks", json={}).status_code == 403
    assert org.get(f"/events/{eid}/ai").status_code == 200


def test_login_and_csrf_required(anon, eid, org):
    assert anon.post(f"/api/events/{eid}/ai/risks", json={}).status_code == 401
    org.csrf = False
    assert org.post(f"/api/events/{eid}/ai/risks", json={}).status_code in (400, 403)


# ---------- admin venues ----------
def test_admin_venue_crud(admin_client, org):
    assert org.get("/admin/venues").status_code == 403
    ok = admin_client.post("/admin/venues/save", data={"name": "Lab 1", "capacity": "40", "cost_per_day": "500", "facilities": ["projector", "bogus"]})
    assert ok.status_code == 302
    page = admin_client.get("/admin/venues").get_data(as_text=True)
    assert "Lab 1" in page
    dup = admin_client.post("/admin/venues/save", data={"name": "lab 1", "capacity": "40", "cost_per_day": "500"})
    assert dup.status_code == 400
    assert admin_client.post("/admin/venues/save", data={"name": "X", "capacity": "0", "cost_per_day": "1"}).status_code == 400
    assert admin_client.post("/admin/venues/3/active").status_code == 302
    assert admin_client.get("/admin/venues/3/edit").status_code == 200


def test_deactivated_venue_not_recommended(admin_client, app):
    with app.app_context():
        planning.set_venue_active(2, False)
        c, _ = insights.score_venues(planning.list_venues(), 50, 10000, [])
    assert [v["id"] for v in c] == [1]


def test_page_state_keeps_category_order_and_overall(org, eid):
    import json, re
    html = org.get(f"/events/{eid}/ai").get_data(as_text=True)
    state = json.loads(re.search(r'id="state">(.*?)</script>', html, re.S).group(1))
    assert [c[0] for c in state["categories"]] == list(insights.BUDGET_CATEGORIES)
    assert state["overall"] == "medium"  # no tasks / schedule yet -> medium warnings
