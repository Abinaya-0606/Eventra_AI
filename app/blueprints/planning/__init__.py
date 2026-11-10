"""Phase 4: per-event AI tools (budget optimizer, venues, risks, improvements, proposal + PDF)."""
from flask import Blueprint

bp = Blueprint("planning", __name__)

from app.blueprints.planning import routes  # noqa: E402,F401
