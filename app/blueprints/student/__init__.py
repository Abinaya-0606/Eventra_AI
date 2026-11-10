"""Student side: browse approved events, register / cancel, My Registered Events."""
from flask import Blueprint

bp = Blueprint("student", __name__)

from app.blueprints.student import routes  # noqa: E402,F401
