"""Application factory: builds the Flask app and registers every Blueprint."""
import os

import click
from flask import Flask, g, jsonify, render_template, request

from config import CONFIGS


def create_app(config_name: str = "development", overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    if config_name == "production" and not os.getenv("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set in the environment for production.")
    app.config.from_object(CONFIGS.get(config_name, CONFIGS["development"]))
    app.config.update(overrides or {})
    app.json.sort_keys = False  # keep JSON keys in the order we build them
    app.json.ensure_ascii = False  # return Tamil text as real characters

    from app import db, security
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.analytics import bp as analytics_bp
    from app.blueprints.ai import bp as ai_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.budget import bp as budget_bp
    from app.blueprints.chat import bp as chat_bp
    from app.blueprints.events import bp as events_bp
    from app.blueprints.tasks import bp as tasks_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.notifications import bp as notifications_bp
    from app.blueprints.planning import bp as planning_bp
    from app.blueprints.student import bp as student_bp

    db.init_app(app)
    for blueprint in (auth_bp, main_bp, events_bp, student_bp, notifications_bp, tasks_bp, chat_bp, budget_bp, ai_bp,
                      planning_bp, analytics_bp, admin_bp):
        app.register_blueprint(blueprint)

    app.before_request(security.before_request)  # login gate + CSRF check for every request
    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # exactly one proxy (Render) in front

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.endpoint != "static":  # never let the browser reuse a page after logout (Back button)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.context_processor
    def inject_globals():
        def unread_notifications() -> int:
            """Unread count for the bell in the sidebar (one query per request, only when asked for)."""
            user = g.get("user")
            if user is None:
                return 0
            if "unread" not in g:
                from app.models import notifications
                g.unread = notifications.unread_count(user.id)
            return g.unread

        return {"current_user": g.get("user"), "csrf_token": security.csrf_token,
                "unread_notifications": unread_notifications}

    _register_error_handlers(app)
    _register_cli(app)
    _bootstrap_admin(app)
    return app


def _bootstrap_admin(app: Flask) -> None:
    """Create the first admin from ADMIN_EMAIL / ADMIN_PASSWORD, but only while there is no admin at all.

    This exists for hosts without a shell (e.g. Render's free plan). It never changes an existing account.
    """
    email, password = app.config.get("ADMIN_EMAIL"), app.config.get("ADMIN_PASSWORD")
    if not (email and password):
        return
    from app.models import users
    from app.services.admin_seed import validate_admin_password
    from app.services.validation import ValidationError, clean_email, clean_password, clean_text

    with app.app_context():
        if users.admin_exists():
            return
        try:
            clean_email_value = clean_email({"email": email})
            users.create_user(clean_text({"n": app.config["ADMIN_NAME"]}, "n", "Name", max_len=80),
                              clean_email_value, validate_admin_password(clean_password({"password": password}), clean_email_value),
                              role="admin")
            app.logger.warning("Created the first admin account (%s). Remove ADMIN_PASSWORD from the environment now.", email)
        except ValidationError as exc:
            app.logger.error("ADMIN_EMAIL/ADMIN_PASSWORD were ignored: %s", exc.message)


def _register_error_handlers(app: Flask) -> None:
    """API paths get JSON errors; page paths get a friendly HTML error page."""
    messages = {
        400: "The request could not be understood. If you were submitting a form, refresh the page and try again.",
        403: "You do not have permission to open this page.",
        404: "That page or resource was not found.",
        405: "That action is not allowed here.",
        413: "The request was too large.",
        500: "Something went wrong on our side. Please try again.",
    }

    titles = {400: "Something was wrong with that request", 403: "Access denied", 404: "Page not found",
              405: "Action not allowed", 413: "Request too large", 500: "Something went wrong"}

    def handle(error):
        code = getattr(error, "code", 500) or 500
        message = messages.get(code, "Something went wrong.")
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), code
        return render_template("errors/error.html", code=code, message=message, title=titles.get(code, "Something went wrong")), code

    for code in messages:
        app.register_error_handler(code, handle)


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed-admin")
    @click.option("--promote", is_flag=True, help="If the email already belongs to a student/organizer, make it an admin.")
    def seed_admin_command(promote):
        """Create the initial admin from ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME (environment variables)."""
        from app.services.admin_seed import SeedError, read_env_credentials, seed_admin

        try:
            name, email, password = read_env_credentials()
            result = seed_admin(name, email, password, promote=promote)
        except SeedError as exc:
            raise click.ClickException(str(exc))
        click.echo({"created": f"Admin {email} created. Sign in at /admin/login, then remove ADMIN_PASSWORD from your environment.",
                    "exists": f"{email} is already an admin. Nothing changed.",
                    "promoted": f"{email} is now an admin (password unchanged)."}[result])

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.password_option()
    def create_admin(email, name, password):
        """Create an admin account (or promote an existing user). Admins cannot be created from the website."""
        from app.models import users
        from app.services.validation import ValidationError, clean_email, clean_password, clean_text

        try:
            email = clean_email({"email": email})
            name = clean_text({"name": name}, "name", "Name", max_len=80)
            password = clean_password({"password": password})
        except ValidationError as exc:
            raise click.ClickException(exc.message)
        existing = users.get_by_email(email)
        if existing:
            users.set_role(existing.id, "admin")
            click.echo(f"{email} already existed and is now an admin (password unchanged).")
        else:
            users.create_user(name, email, password, role="admin")
            click.echo(f"Admin {email} created.")
