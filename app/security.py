"""Security helpers: CSRF tokens, safe redirects, login throttling, login/role decorators."""
import hmac
import secrets
import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import current_app, g, jsonify, redirect, render_template, request, session, url_for

# ---------- CSRF ----------
def csrf_token() -> str:
    """The per-session token. Put it in every form (hidden field) and send it as X-CSRF-Token from JS."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_is_valid() -> bool:
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    expected = session.get("_csrf", "")
    return bool(expected) and hmac.compare_digest(sent, expected)


# ---------- safe redirects ----------
def safe_next(target: str | None) -> str:
    """Only allow same-site relative paths, so '?next=' cannot send people to another website."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        parsed = urlparse(target)
        if not parsed.scheme and not parsed.netloc:
            return target
    return url_for("main.dashboard")


# ---------- login throttling (in memory, per process) ----------
class LoginThrottle:
    def __init__(self):
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        window = current_app.config["LOCKOUT_SECONDS"]
        cutoff = time.time() - window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = recent
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= current_app.config["MAX_FAILED_LOGINS"]

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


throttle = LoginThrottle()


# ---------- sessions ----------
def start_session(user) -> None:
    """Log a user in. Clearing first prevents session fixation (a pre-login session being reused)."""
    session.clear()
    session["uid"] = user.id
    session["sv"] = user.session_version
    session.permanent = True
    csrf_token()


def load_user():
    """Return the logged-in user, or None. Signs out if the password changed or the account was disabled."""
    from app.models import users  # local import avoids a circular import at start-up

    uid = session.get("uid")
    if uid is None:
        return None
    user = users.get_by_id(uid)
    if user is None or not user.is_active or session.get("sv") != user.session_version:
        session.clear()
        return None
    return user


# ---------- access control ----------
def _deny(status: int, message: str):
    if request.path.startswith("/api/"):
        return jsonify({"error": message}), status
    return render_template("errors/error.html", code=status, message=message), status


def role_required(*roles):
    """Allow only the listed roles (login is already enforced for every page by the app-wide gate)."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None or g.user.role not in roles:
                return _deny(403, "You do not have permission to open this page.")
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------- role policy ----------
# Who may reach which part of the site. Enforced for EVERY request in before_request (default-deny for
# anything not listed in a known blueprint), so a new route can never be left open by accident.
ALL_ROLES = ("student", "organizer", "admin")
STAFF = ("organizer", "admin")
BLUEPRINT_ROLES = {
    "auth": ALL_ROLES, "main": ALL_ROLES, "chat": ALL_ROLES, "notifications": ALL_ROLES,
    "student": ("student",),            # browse / register / My Registered Events
    "admin": ("admin",),                # user, organizer, student, venue management, approvals, logs
    "events": STAFF, "tasks": STAFF, "ai": STAFF, "planning": STAFF, "budget": STAFF, "analytics": STAFF,
}
# Endpoints that differ from their blueprint's default.
ENDPOINT_ROLES = {"events.calendar_view": ALL_ROLES}


def roles_for(endpoint: str):
    """The roles allowed to use `endpoint`, or None if the policy does not know it (which means: deny)."""
    return ENDPOINT_ROLES.get(endpoint) or BLUEPRINT_ROLES.get(endpoint.split(".")[0])


PUBLIC_ENDPOINTS = {"static", "auth.login", "auth.register", "auth.forgot_password", "auth.reset_password", "main.healthz",
                    "admin.login"}  # the admin login form itself; every other /admin/* endpoint needs an admin session
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def before_request():
    """Runs before EVERY request: load the user, require login (except public pages), check CSRF."""
    g.user = load_user()
    endpoint = request.endpoint
    if endpoint is None:  # unknown URL: let the 404 handler answer
        return None
    if g.user is None and endpoint not in PUBLIC_ENDPOINTS:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Please log in to continue."}), 401
        login_endpoint = "admin.login" if request.path.startswith("/admin") else "auth.login"
        return redirect(url_for(login_endpoint, next=request.full_path.rstrip("?")))
    if request.method in UNSAFE_METHODS and not csrf_is_valid():
        return _deny(400, "Your session expired or the security token is missing. Reload the page and try again.")
    if g.user is not None and endpoint not in PUBLIC_ENDPOINTS and endpoint != "static":
        allowed = roles_for(endpoint)
        if allowed is None or g.user.role not in allowed:
            return _deny(403, "You do not have permission to open this page.")
    return None
