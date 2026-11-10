"""The Groq wrapper: configuration, JSON parsing, error translation (Groq itself is faked)."""
import sys
import types

import pytest

from app.services import llm


def fake_groq(monkeypatch, reply=None, error=None, calls=None):
    class Completions:
        def create(self, **kwargs):
            if calls is not None:
                calls.append(kwargs)
            if error:
                raise error
            msg = types.SimpleNamespace(content=reply)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class Groq:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "groq", types.SimpleNamespace(Groq=Groq))


def test_parse_json_variants():
    assert llm.parse_json('{"a": 1}') == {"a": 1}
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Sure! {"a": {"b": 2}} Hope it helps') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        llm.parse_json("no json here")
    with pytest.raises(ValueError):
        llm.parse_json("[1, 2]")


def test_missing_key_message(app):
    app.config["GROQ_API_KEY"] = ""
    with app.app_context():
        with pytest.raises(llm.LLMError) as e:
            llm.complete("s", "u")
    assert "GROQ_API_KEY" in e.value.message and e.value.status == 503


def test_placeholder_key_is_not_configured(app):
    app.config["GROQ_API_KEY"] = "your_groq_api_key"
    with app.app_context():
        assert not llm.is_configured()


def test_complete_sends_language_model_and_history(app, monkeypatch):
    calls = []
    fake_groq(monkeypatch, reply="  hello  ", calls=calls)
    app.config["GROQ_MODEL_TAMIL"] = "tamil-model"
    with app.app_context():
        out = llm.complete("SYS", "USER", language="ta", history=[{"role": "user", "content": "earlier"}], json_mode=True)
    assert out == "hello"
    sent = calls[0]
    assert sent["model"] == "tamil-model"
    assert "Tamil" in sent["messages"][0]["content"] and sent["messages"][0]["content"].startswith("SYS")
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "user"]
    assert sent["response_format"] == {"type": "json_object"}


def test_sdk_errors_become_friendly(app, monkeypatch):
    class RateLimitError(Exception):
        pass

    fake_groq(monkeypatch, error=RateLimitError("429"))
    with app.app_context():
        with pytest.raises(llm.LLMError) as e:
            llm.complete("s", "u")
    assert e.value.status == 429 and "busy" in e.value.message


def test_complete_json_retries_once_then_fails(app, monkeypatch):
    calls = []
    fake_groq(monkeypatch, reply="not json", calls=calls)
    with app.app_context():
        with pytest.raises(llm.LLMError) as e:
            llm.complete_json("s", "u")
    assert len(calls) == 2 and e.value.status == 502


def test_complete_json_recovers_on_second_try(app, monkeypatch):
    replies = iter(["oops", '{"ok": true}'])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: next(replies))
    with app.app_context():
        assert llm.complete_json("s", "u") == {"ok": True}
