from flask import g, jsonify, render_template, request

from app.blueprints.chat import bp
from app.services import event_answers, rag

SUGGESTED = {
    "en": ["When should I submit an event proposal?", "What is the Auditorium capacity?",
           "Who approves a budget above INR 20,000?", "What information is required in an event proposal?",
           "What are the refreshment and participation kit costs?"],
    "ta": ["நிகழ்வு முன்மொழிவை எப்போது சமர்ப்பிக்க வேண்டும்?", "ஆடிட்டோரியத்தின் கொள்ளளவு என்ன?",
           "ரூ. 20,000-க்கு மேல் பட்ஜெட்டுக்கு யார் ஒப்புதல் அளிப்பார்?",
           "நிகழ்வு முன்மொழிவில் என்ன தகவல்கள் தேவை?"],
}


@bp.get("/assistant")
def assistant():
    return render_template("chat/assistant.html", suggested=SUGGESTED)


@bp.post("/api/chat")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send the question as JSON."}), 400
    question = data.get("question", "")
    if not isinstance(question, str):
        return jsonify({"error": "Please type a question."}), 400
    language = data.get("language", "en")
    # "What events are coming up?" is answered from the real approved-events table (never invented by the LLM).
    if question.strip() and len(question) <= 500:
        listing = event_answers.answer(question, language if isinstance(language, str) else "en", g.user)
        if listing is not None:
            return jsonify(listing)
    result = rag.answer_question(question, data.get("language", "en"), data.get("history"))
    status = result.pop("status", 200)
    return jsonify(result), status
