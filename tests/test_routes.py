"""Every page loads; budget API and error handling behave."""
import pytest


@pytest.mark.parametrize("path", ["/", "/ai-studio", "/assistant", "/budget", "/policies", "/about"])
def test_pages_load(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert b"Eventra AI" in res.data


def test_policies_page_lists_documents(client):
    html = client.get("/policies").get_data(as_text=True)
    assert "Venue Policy" in html and "Seminar Hall holds 100" in html


def test_404_html_and_json(client):
    assert client.get("/nope").status_code == 404
    res = client.get("/api/nope")
    assert res.status_code == 404 and "error" in res.get_json()


def test_405_on_api_is_json(client):
    res = client.get("/api/budget")
    assert res.status_code == 405 and res.is_json


def test_budget_api_ok(client):
    res = client.post("/api/budget", json={"venue": "seminar_hall", "participants": "50",
                                           "refreshments": True, "participation_kits": False})
    assert res.status_code == 200 and res.get_json()["total"] == 7700


def test_budget_api_errors(client):
    assert client.post("/api/budget", json={"venue": "seminar_hall", "participants": 101,
                                            "refreshments": False, "participation_kits": False}).status_code == 400
    assert client.post("/api/budget", data="not json").status_code == 400
