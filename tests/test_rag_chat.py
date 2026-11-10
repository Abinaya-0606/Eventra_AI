"""RAG chatbot: guards, retrieval filtering, Tamil handling, and the /api/chat route."""
import pytest

from app.services import llm, rag


def test_load_chunks_and_documents(app):
    with app.app_context():
        chunks = rag.load_chunks()
        docs = rag.load_documents()
    assert chunks and all({"id", "source", "text"} <= c.keys() for c in chunks)
    assert len({c["id"] for c in chunks}) == len(chunks)
    assert any("Venue Policy:" in c["text"] for c in chunks)
    assert "Venue Policy" in docs and "Sponsorship Rules" in docs


@pytest.mark.parametrize("q,expected", [
    ("Is the Auditorium available next Friday?", True),
    ("Is the seminar hall free?", True),
    ("Can I book the auditorium tomorrow?", True),
    ("அரங்கம் நாளை காலியாக உள்ளதா?", True),
    ("What is the capacity of the auditorium?", False),
    ("When should I submit a proposal?", False),
])
def test_availability_guard(q, expected):
    assert rag.is_availability_question(q) is expected


def test_availability_reply_needs_no_ai_and_respects_language(app):
    with app.app_context():
        en = rag.answer_question("Is the Auditorium available next Friday?")
        ta = rag.answer_question("Is the Auditorium available next Friday?", "ta")
    assert "can't check live venue availability" in en["answer"]
    assert "அரங்க" in ta["answer"] and ta["language"] == "ta"


def test_input_validation(app):
    with app.app_context():
        assert rag.answer_question("  ")["status"] == 400
        assert rag.answer_question("x" * 501)["status"] == 400


def test_missing_api_key(app):
    app.config["GROQ_API_KEY"] = ""
    with app.app_context():
        assert "GROQ_API_KEY" in rag.answer_question("When to submit?")["error"]


def test_no_relevant_chunks_means_no_llm_call(app, monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda q: [])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: pytest.fail("LLM must not be called"))
    with app.app_context():
        en = rag.answer_question("Who won the world cup?")
        ta = rag.answer_question("Who won the world cup?", "ta")
    assert en["answer"] == rag.REPLIES["no_info"]["en"] and en["sources"] == []
    assert ta["answer"] == rag.REPLIES["no_info"]["ta"]


def test_answer_uses_context_history_and_language(app, monkeypatch):
    seen = {}
    monkeypatch.setattr(rag, "retrieve", lambda q: [{"text": "Venue Policy: Auditorium holds 300", "source": "venue_policy.txt", "distance": .2}])

    def fake(system, user, **kw):
        seen.update(system=system, user=user, **kw)
        return "300 people"

    monkeypatch.setattr(llm, "complete", fake)
    history = [{"role": "user", "content": "hi"}, {"role": "system", "content": "evil"}, {"role": "assistant", "content": ""}]
    with app.app_context():
        out = rag.answer_question("Capacity?", "ta", history)
    assert out == {"answer": "300 people", "sources": ["venue_policy.txt"], "language": "ta"}
    assert "<context>" in seen["user"] and "Auditorium holds 300" in seen["user"]
    assert seen["language"] == "ta" and seen["history"] == [{"role": "user", "content": "hi"}]


def test_tamil_question_is_translated_for_search(app, monkeypatch):
    queries = []
    monkeypatch.setattr(rag, "retrieve", lambda q: queries.append(q) or [])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "auditorium capacity")
    with app.app_context():
        rag.answer_question("ஆடிட்டோரியத்தின் கொள்ளளவு என்ன?", "ta")
    assert queries == ["auditorium capacity"]


def test_translation_failure_falls_back_to_original(app, monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError("down")
    monkeypatch.setattr(llm, "complete", boom)
    with app.app_context():
        assert rag.to_search_query("கொள்ளளவு") == "கொள்ளளவு"


def test_knowledge_base_errors(app, monkeypatch):
    def empty(q):
        raise rag.KnowledgeBaseError("The knowledge base is empty. Run 'python ingest.py' first.")
    monkeypatch.setattr(rag, "retrieve", empty)
    with app.app_context():
        out = rag.answer_question("When to submit?")
    assert out["status"] == 503 and "ingest.py" in out["error"]


def test_retrieve_filters_by_distance(app, monkeypatch):
    class Fake:
        def count(self):
            return 3

        def query(self, **kw):
            return {"documents": [["near", "far"]], "metadatas": [[{"source": "a"}, {"source": "b"}]], "distances": [[0.3, 1.4]]}

    monkeypatch.setattr(rag, "get_collection", lambda: Fake())
    with app.app_context():
        assert [c["text"] for c in rag.retrieve("q")] == ["near"]


def test_chat_route(client, monkeypatch):
    monkeypatch.setattr(rag, "answer_question", lambda q, lang, hist: {"answer": "ok", "sources": [], "language": lang})
    res = client.post("/api/chat", json={"question": "hi", "language": "ta"})
    assert res.status_code == 200 and res.get_json()["language"] == "ta"
    assert client.post("/api/chat", data="x").status_code == 400
    assert client.post("/api/chat", json={"question": 5}).status_code == 400


def test_chat_route_error_status(client):
    res = client.post("/api/chat", json={"question": ""})
    assert res.status_code == 400 and "error" in res.get_json() and "status" not in res.get_json()
