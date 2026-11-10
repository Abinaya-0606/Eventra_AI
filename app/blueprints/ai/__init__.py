"""AI Studio: planner, name/description/schedule/checklist/letter generators (JSON API + page)."""
from flask import Blueprint

bp = Blueprint("ai", __name__)

from app.blueprints.ai import routes  # noqa: E402,F401  (registers the routes)
