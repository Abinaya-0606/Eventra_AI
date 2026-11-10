"""The ONE place that talks to the Groq API. Every AI feature calls these helpers.

Keeping this in one file means API-key checks, language handling, JSON parsing and
error messages are written once and behave the same everywhere.
"""
import json
import re

from flask import current_app

LANGUAGES = {"en": "English", "ta": "Tamil"}


class LLMError(Exception):
    """A problem with the AI service, with a user-friendly message and an HTTP status."""

    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.message = message
        self.status = status


def is_configured() -> bool:
    key = current_app.config.get("GROQ_API_KEY", "")
    return bool(key) and key != "your_groq_api_key"


def language_instruction(language: str) -> str:
    if language == "ta":
        return ("Write all human-readable text in natural, clear Tamil (தமிழ்) script. "
                "Keep JSON keys, numbers, dates, times and currency codes (INR) unchanged.")
    return "Write in clear, plain English."


def _translate_exception(exc: Exception) -> LLMError:
    name = type(exc).__name__
    if name == "RateLimitError":
        return LLMError("The AI service is busy (rate limit reached). Wait a moment and try again.", 429)
    if name == "AuthenticationError":
        return LLMError("The AI service rejected the API key. Check GROQ_API_KEY in your .env file.", 503)
    if name in ("NotFoundError", "BadRequestError"):
        return LLMError("The AI service rejected the request. The GROQ_MODEL name may be retired; "
                        "pick a current model from console.groq.com/docs/models.", 503)
    if name in ("APIConnectionError", "APITimeoutError", "Timeout", "ConnectError"):
        return LLMError("Could not reach the AI service. Check your internet connection and try again.", 503)
    return LLMError(f"The AI service could not answer right now ({name}). Please try again.", 503)


def complete(system: str, user: str, *, language: str = "en", history: list | None = None,
             json_mode: bool = False, temperature: float = 0.3, max_tokens: int = 2000) -> str:
    """Send one chat request to Groq and return the reply text. Raises LLMError on any problem."""
    if not is_configured():
        raise LLMError("GROQ_API_KEY is not configured. Add your key to the .env file and restart the app.", 503)

    cfg = current_app.config
    model = cfg["GROQ_MODEL_TAMIL"] if language == "ta" else cfg["GROQ_MODEL"]
    messages = [{"role": "system", "content": f"{system}\n\n{language_instruction(language)}"}]
    messages += [{"role": t["role"], "content": t["content"]} for t in (history or [])]
    messages.append({"role": "user", "content": user})

    kwargs = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        from groq import Groq  # imported here so the app still starts if the package is missing
        client = Groq(api_key=cfg["GROQ_API_KEY"], timeout=cfg["LLM_TIMEOUT"])
        response = client.chat.completions.create(**kwargs)
    except ImportError:
        raise LLMError("The 'groq' package is not installed. Run: pip install -r requirements.txt", 503)
    except Exception as exc:  # noqa: BLE001 - convert every SDK error to a friendly message
        raise _translate_exception(exc) from exc

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise LLMError("The AI returned an empty response. Please try again.", 502)
    return text


def parse_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating ```json fences and extra prose."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]):
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no JSON object found")


def complete_json(system: str, user: str, *, language: str = "en", temperature: float = 0.4,
                  max_tokens: int = 2500) -> dict:
    """Like complete(), but returns a parsed dict. Retries once if the model returns bad JSON."""
    system = system + "\nReturn ONLY one valid JSON object. No markdown, no commentary."
    for attempt in range(2):
        text = complete(system, user, language=language, json_mode=True,
                        temperature=temperature, max_tokens=max_tokens)
        try:
            return parse_json(text)
        except ValueError:
            if attempt == 1:
                break
    raise LLMError("The AI returned an unreadable answer. Please click Generate again.", 502)
