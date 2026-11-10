"""Registration, login, logout, password reset and profile."""
from flask import Blueprint

bp = Blueprint("auth", __name__)

from app.blueprints.auth import routes  # noqa: E402,F401
