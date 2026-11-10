from flask import jsonify, render_template, request

from app.blueprints.ai import bp
from app.services import ai_features as features
from app.services.llm import LLMError
from app.services.validation import (EVENT_TYPES, LETTER_RECIPIENTS, ValidationError, clean_amount,
                                     clean_choice, clean_date, clean_int, clean_language, clean_text,
                                     clean_time)


@bp.get("/ai-studio")
def studio():
    return render_template("ai/studio.html", event_types=EVENT_TYPES, recipients=LETTER_RECIPIENTS)


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send the details as JSON.")
    return data


def _handle(parse, generate):
    """Shared flow for every generator: read JSON -> validate -> call AI -> JSON response."""
    try:
        data = _json_body()
        language = clean_language(data)
        params = parse(data)
        return jsonify(generate(params, language))
    except ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    except LLMError as exc:
        return jsonify({"error": exc.message}), exc.status


def _event_type(d):
    return clean_choice(d, "event_type", "Event type", EVENT_TYPES)


@bp.post("/api/ai/plan")
def plan():
    def parse(d):
        return {
            "event_type": _event_type(d),
            "name": clean_text(d, "name", "Event name", max_len=100),
            "participants": clean_int(d, "participants", "Number of participants", min_value=1, max_value=10000),
            "budget": clean_amount(d, "budget", "Available budget"),
            "duration_hours": clean_int(d, "duration_hours", "Duration (hours)", min_value=1, max_value=72),
            "venue": clean_text(d, "venue", "Venue preference", max_len=100),
            "description": clean_text(d, "description", "Event description", max_len=1000, multiline=True),
        }
    return _handle(parse, features.generate_plan)


@bp.post("/api/ai/names")
def names():
    def parse(d):
        return {
            "event_type": _event_type(d),
            "theme": clean_text(d, "theme", "Theme or keywords", max_len=150, required=False),
            "department": clean_text(d, "department", "Department", max_len=100, required=False),
            "count": clean_int(d, "count", "Number of names", min_value=3, max_value=12, required=False, default=8),
        }
    return _handle(parse, features.generate_names)


@bp.post("/api/ai/description")
def description():
    def parse(d):
        return {
            "name": clean_text(d, "name", "Event name", max_len=100),
            "event_type": _event_type(d),
            "audience": clean_text(d, "audience", "Target audience", max_len=150, required=False),
            "tone": clean_choice(d, "tone", "Tone", ("professional", "exciting", "formal", "friendly"),
                                 default="professional"),
            "details": clean_text(d, "details", "Key details", max_len=800, required=False, multiline=True),
        }
    return _handle(parse, features.generate_description)


@bp.post("/api/ai/schedule")
def schedule():
    def parse(d):
        return {
            "name": clean_text(d, "name", "Event name", max_len=100),
            "event_type": _event_type(d),
            "start_time": clean_time(d, "start_time", "Start time"),
            "duration_hours": clean_int(d, "duration_hours", "Duration (hours)", min_value=1, max_value=24),
            "participants": clean_int(d, "participants", "Number of participants", min_value=1, max_value=10000,
                                      required=False, default=None),
            "notes": clean_text(d, "notes", "Notes", max_len=500, required=False, multiline=True),
        }
    return _handle(parse, features.generate_schedule)


@bp.post("/api/ai/checklist")
def checklist():
    def parse(d):
        return {
            "name": clean_text(d, "name", "Event name", max_len=100),
            "event_type": _event_type(d),
            "participants": clean_int(d, "participants", "Number of participants", min_value=1, max_value=10000,
                                      required=False, default=None),
            "notes": clean_text(d, "notes", "Notes", max_len=500, required=False, multiline=True),
        }
    return _handle(parse, features.generate_checklist)


@bp.post("/api/ai/letter")
def letter():
    def parse(d):
        return {
            "recipient": clean_choice(d, "recipient", "Recipient", tuple(LETTER_RECIPIENTS)),
            "event_name": clean_text(d, "event_name", "Event name", max_len=100),
            "event_type": _event_type(d),
            "event_date": clean_date(d, "event_date", "Event date"),
            "venue": clean_text(d, "venue", "Venue", max_len=100, required=False),
            "sender_name": clean_text(d, "sender_name", "Your name", max_len=80),
            "department": clean_text(d, "department", "Department", max_len=100),
            "college": clean_text(d, "college", "College name", max_len=120, required=False),
            "details": clean_text(d, "details", "Purpose and details", max_len=800, required=False, multiline=True),
        }
    return _handle(parse, features.generate_letter)


@bp.post("/api/ai/budget")
def budget_optimizer():
    def parse(d):
        return {
            "event_type": _event_type(d),
            "participants": clean_int(d, "participants", "Number of participants", min_value=1, max_value=10000),
            "budget": clean_amount(d, "budget", "Total budget"),
            "duration_hours": clean_int(d, "duration_hours", "Duration (hours)", min_value=1, max_value=72),
            "venue": clean_text(d, "venue", "Venue", max_len=100, required=False),
            "description": clean_text(d, "description", "Description", max_len=500, required=False, multiline=True),
            "venue_cost": None,
        }
    return _handle(parse, features.generate_budget)
