"""Answers 'what events are coming up?' from the real approved-events table (no LLM, so it never invents events).

Policy questions ("when should I submit a proposal?") do not match and still go to the RAG chatbot.
"""
import re

from app.models import events

_ASK = re.compile(r"\b(what|which|any|list|show|tell me|are there|upcoming|coming up|happening)\b", re.I)
_EVENTS = re.compile(r"\bevents?\b|\bworkshops?\b|\bhackathons?\b|\bseminars?\b|\bfests?\b", re.I)
_WHEN = re.compile(r"\b(upcoming|coming up|happening|available|open for registration|this week|next week|this month|"
                   r"can i (join|register|attend)|to (join|attend|register)|on (campus|now))\b", re.I)
_POLICY = re.compile(r"\b(rule|policy|proposal|approve[sd]?|approval|budget|capacity|cost|submit|sponsor|volunteer)\b", re.I)

HEADERS = {
    "en": ("Here are the upcoming approved events:", "There are no upcoming approved events right now. Please check again soon."),
    "ta": ("வரவிருக்கும் அங்கீகரிக்கப்பட்ட நிகழ்வுகள்:", "தற்போது வரவிருக்கும் அங்கீகரிக்கப்பட்ட நிகழ்வுகள் எதுவும் இல்லை."),
}


def is_upcoming_events_question(question: str) -> bool:
    return bool(_ASK.search(question) and _EVENTS.search(question) and _WHEN.search(question) and not _POLICY.search(question))


def answer(question: str, language: str, user) -> dict | None:
    if not is_upcoming_events_question(question):
        return None
    language = language if language in HEADERS else "en"
    items, total = events.browse(user.id, per_page=5)
    header, none = HEADERS[language]
    if not items:
        return {"answer": none, "sources": ["Eventra AI events"], "language": language}
    lines = [f"- {e.name} ({e.event_type}) on {e.event_date} at {e.start_time}"
             + (f", {e.venue}" if e.venue else "") + f": {max(e.participants - e.registered_count, 0)} seats left"
             for e in items]
    more = f"\n(+{total - len(items)} more in Browse Events)" if total > len(items) else ""
    return {"answer": header + "\n" + "\n".join(lines) + more, "sources": ["Eventra AI events"], "language": language}
