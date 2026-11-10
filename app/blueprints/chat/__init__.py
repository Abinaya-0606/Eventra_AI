"""RAG chatbot (English / Tamil)."""
from flask import Blueprint

bp = Blueprint("chat", __name__)

from app.blueprints.chat import routes  # noqa: E402,F401
