"""Secure creation of administrator accounts.

Admins can NEVER be created from the public sign-up form. The first one is created from the command line
(`flask --app run seed-admin`, or `python seed_admin.py`) using credentials read from ENVIRONMENT VARIABLES:

    ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME (optional)

There is no default account and no default password. The password is hashed (scrypt) before it is stored.
"""
import os

from app.services.validation import ValidationError, clean_email, clean_password, clean_text

MIN_ADMIN_PASSWORD = 10
_COMMON = {"password", "password1", "password123", "admin123", "admin12345", "administrator1", "qwerty12345",
           "letmein123", "welcome123", "changeme123", "eventra123", "1234567890"}


class SeedError(Exception):
    """A problem the person running the command can fix (message is safe to print)."""


def validate_admin_password(password: str, email: str = "") -> str:
    """Admins need a stronger password than other roles: 10+ characters, a letter and a number, not a common one."""
    clean_password({"password": password})  # length 8-128, letter + digit (raises ValidationError)
    if len(password) < MIN_ADMIN_PASSWORD:
        raise ValidationError(f"An admin password must be at least {MIN_ADMIN_PASSWORD} characters.", "password")
    if password.lower() in _COMMON or (email and password.lower() == email.split("@")[0].lower()):
        raise ValidationError("That password is too easy to guess. Choose a different one.", "password")
    return password


def read_env_credentials(environ=None) -> tuple[str, str, str]:
    """(name, email, password) from the environment, validated. Raises SeedError when missing or invalid."""
    env = os.environ if environ is None else environ
    email_raw, password = (env.get("ADMIN_EMAIL") or "").strip(), env.get("ADMIN_PASSWORD") or ""
    if not email_raw or not password:
        raise SeedError("Set ADMIN_EMAIL and ADMIN_PASSWORD in the environment (or .env) first. "
                        "There is deliberately no default admin account or password.")
    try:
        email = clean_email({"email": email_raw})
        name = clean_text({"n": env.get("ADMIN_NAME") or "Administrator"}, "n", "Name", max_len=80)
        validate_admin_password(password, email)
    except ValidationError as exc:
        raise SeedError(exc.message) from None
    return name, email, password


def seed_admin(name: str, email: str, password: str, *, promote: bool = False) -> str:
    """Create the admin (inside an app context). Returns 'created', 'exists' or 'promoted'. Never changes a password."""
    from app.models import users

    existing = users.get_by_email(email)
    if existing is None:
        users.create_user(name, email, password, role="admin")
        return "created"
    if existing.role == "admin":
        return "exists"
    if not promote:
        raise SeedError(f"{email} is already registered as a {existing.role}. Re-run with --promote to make that "
                        "account an admin (its password is not changed).")
    users.set_role(existing.id, "admin")
    return "promoted"
