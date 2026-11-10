from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from app.blueprints.auth import bp
from app.models import tokens, users
from app.security import safe_next, start_session, throttle
from app.services import mailer
from app.services.validation import (ValidationError, clean_choice, clean_email, clean_language,
                                     clean_password, clean_text)

GENERIC_LOGIN_ERROR = "Invalid email or password."


def _client_key(email: str) -> str:
    return f"{email}|{request.remote_addr}"


def _form_error(template: str, exc: ValidationError, status: int = 400, **context):
    return render_template(template, error=exc.message, field=exc.field, form=request.form, **context), status


# ---------- register ----------
@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("main.dashboard"))
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("auth/register.html", form={})
    try:
        name = clean_text(request.form, "name", "Name", max_len=80)
        email = clean_email(request.form)
        password = clean_password(request.form)
        if password != request.form.get("confirm_password"):
            raise ValidationError("The two passwords do not match.", "confirm_password")
        # Only student/organizer can be chosen here. Admins are created by seed-admin or by another admin.
        role = clean_choice(request.form, "role", "Role", ("student", "organizer"), default="student")
        department = clean_text(request.form, "department", "Department", max_len=100, required=False)
        user = users.create_user(name, email, password, role=role, department=department)
    except ValidationError as exc:
        return _form_error("auth/register.html", exc)
    except users.EmailTaken:
        return _form_error("auth/register.html", ValidationError("An account with this email already exists.", "email"), 409)
    start_session(user)
    flash(f"Welcome, {user.name}! Your account is ready.", "success")
    return redirect(url_for("main.dashboard"))


# ---------- login / logout ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    nxt = request.values.get("next", "")
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("auth/login.html", form={}, next=nxt)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    key = _client_key(email)
    if throttle.blocked(key):
        return render_template("auth/login.html", form=request.form, next=nxt,
                               error="Too many failed attempts. Please wait a few minutes and try again."), 429
    user = users.get_by_email(email) if email else None
    if not users.verify_password(user, password):
        throttle.fail(key)
        return render_template("auth/login.html", form=request.form, next=nxt, error=GENERIC_LOGIN_ERROR), 401
    if not user.is_active:
        return render_template("auth/login.html", form=request.form, next=nxt,
                               error="This account has been deactivated. Contact an administrator."), 403
    if user.is_admin:  # admins have their own sign-in page; no session is started here
        return render_template("auth/login.html", form=request.form, next="", admin_notice=True,
                               error="Administrator accounts sign in on the separate admin login page."), 403
    throttle.reset(key)
    start_session(user)
    return redirect(safe_next(nxt))


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


# ---------- forgot / reset password ----------
@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("auth/forgot.html", form={})
    try:
        email = clean_email(request.form)
    except ValidationError as exc:
        return _form_error("auth/forgot.html", exc)

    user = users.get_by_email(email)
    if user and user.is_active:
        raw = tokens.create_reset_token(user.id, current_app.config["RESET_TOKEN_MINUTES"])
        base = current_app.config["APP_BASE_URL"].rstrip("/") or request.host_url.rstrip("/")
        link = base + url_for("auth.reset_password", token=raw)
        mailer.send_email(
            user.email, "Reset your Eventra AI password",
            f"Hello {user.name},\n\nUse this link to choose a new password "
            f"(valid for {current_app.config['RESET_TOKEN_MINUTES']} minutes, one use only):\n\n{link}\n\n"
            "If you did not ask for this, you can ignore this email.\n\nEventra AI - Your Smart Event Companion")
    # Same answer whether or not the account exists, so this form cannot be used to find registered emails.
    flash("If an account exists for that email, a password reset link has been sent.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if not tokens.is_valid(token):
        return render_template("auth/reset.html", invalid=True), 400
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("auth/reset.html", token=token)
    try:
        password = clean_password(request.form)
        if password != request.form.get("confirm_password"):
            raise ValidationError("The two passwords do not match.", "confirm_password")
    except ValidationError as exc:
        return _form_error("auth/reset.html", exc, token=token)
    user_id = tokens.consume(token)
    if user_id is None:
        return render_template("auth/reset.html", invalid=True), 400
    users.set_password(user_id, password)  # also signs the user out on every other device
    flash("Your password has been changed. Please log in.", "success")
    return redirect(url_for("auth.login"))


# ---------- profile ----------
@bp.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method != "POST":  # GET, and HEAD which Flask adds automatically
        return render_template("auth/profile.html", form={})
    try:
        name = clean_text(request.form, "name", "Name", max_len=80)
        department = clean_text(request.form, "department", "Department", max_len=100, required=False)
        language = clean_language(request.form)
    except ValidationError as exc:
        return _form_error("auth/profile.html", exc)
    users.update_profile(g.user.id, name, department, language)
    flash("Profile updated.", "success")
    return redirect(url_for("auth.profile", saved=1))  # lets the page apply the new language right away


@bp.post("/profile/password")
def change_password():
    try:
        if not users.verify_password(g.user, request.form.get("current_password") or ""):
            raise ValidationError("Your current password is not correct.", "current_password")
        new = clean_password(request.form, "new_password", "New password")
        if new != request.form.get("confirm_password"):
            raise ValidationError("The two new passwords do not match.", "confirm_password")
    except ValidationError as exc:
        return _form_error("auth/profile.html", exc, pw_error=True)
    users.set_password(g.user.id, new)
    start_session(users.get_by_id(g.user.id))  # keep THIS device logged in with the new session version
    flash("Password changed. Other devices have been signed out.", "success")
    return redirect(url_for("auth.profile"))
