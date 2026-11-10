"""Phase 5: analytics dashboard and downloadable PDF reports."""
from flask import Blueprint

bp = Blueprint("analytics", __name__)

from app.blueprints.analytics import routes  # noqa: E402,F401
