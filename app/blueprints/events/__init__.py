"""Events: list, create, details, edit, delete, status workflow, calendar, saved schedule."""
from flask import Blueprint

bp = Blueprint("events", __name__)

from app.blueprints.events import routes  # noqa: E402,F401
