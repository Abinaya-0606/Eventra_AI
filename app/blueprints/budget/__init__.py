"""Budget calculator (deterministic Python; no LLM)."""
from flask import Blueprint

bp = Blueprint("budget", __name__)

from app.blueprints.budget import routes  # noqa: E402,F401
