"""Small, strict input validators shared by every API route.

Each helper reads one field from a dict and returns a clean value, or raises
ValidationError with a message that is safe to show to the user.
"""
import re
from datetime import datetime

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

EVENT_TYPES = [
    "Technical Symposium", "Workshop", "Hackathon", "Seminar", "Guest Lecture", "Cultural Fest",
    "Sports Meet", "Competition", "Orientation", "Alumni Meet", "Other",
]
LETTER_RECIPIENTS = {
    "principal": "Principal",
    "hod": "Head of Department (HOD)",
    "management": "College Management",
    "guest_speaker": "Guest Speaker",
    "sponsor": "Sponsor",
}


class ValidationError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def clean_text(data: dict, key: str, label: str, *, max_len: int = 200, required: bool = True,
               multiline: bool = False, default: str = "") -> str:
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(f"{label} is required.", key)
        return default
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValidationError(f"{label} must be text.", key)
    text = _CONTROL_CHARS.sub("", str(value)).strip()
    if not multiline:
        text = " ".join(text.split())
    if len(text) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters.", key)
    return text


def clean_int(data: dict, key: str, label: str, *, min_value: int, max_value: int,
              required: bool = True, default: int | None = None) -> int | None:
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(f"{label} is required.", key)
        return default
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{label} must be a whole number.", key)
    if not min_value <= value <= max_value:
        raise ValidationError(f"{label} must be between {min_value} and {max_value}.", key)
    return value


def clean_amount(data: dict, key: str, label: str, *, max_value: float = 10_000_000) -> float:
    """A money amount in INR (>= 0, up to 2 decimals)."""
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError(f"{label} is required.", key)
    if isinstance(value, str) and re.fullmatch(r"\d+(\.\d{1,2})?", value.strip()):
        value = float(value.strip())
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a valid amount in INR.", key)
    if not 0 <= value <= max_value:
        raise ValidationError(f"{label} must be between 0 and {max_value:,.0f}.", key)
    return round(float(value), 2)


def clean_choice(data: dict, key: str, label: str, choices, *, default: str | None = None) -> str:
    value = data.get(key)
    if value is None or value == "":
        if default is not None:
            return default
        raise ValidationError(f"{label} is required.", key)
    if value not in choices:
        raise ValidationError(f"{label} has an invalid value.", key)
    return value


def clean_language(data: dict) -> str:
    return clean_choice(data, "language", "Language", ("en", "ta"), default="en")


def clean_time(data: dict, key: str, label: str) -> str:
    """24-hour HH:MM (what <input type=time> sends)."""
    value = clean_text(data, key, label, max_len=5)
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ValidationError(f"{label} must be a time like 09:00.", key) from None
    return value


def clean_date(data: dict, key: str, label: str, *, required: bool = False) -> str:
    """YYYY-MM-DD (what <input type=date> sends). Returns '' when optional and empty."""
    value = clean_text(data, key, label, max_len=10, required=required)
    if value:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValidationError(f"{label} must be a valid date.", key) from None
    return value


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,}$")


def clean_email(data: dict, key: str = "email", label: str = "Email") -> str:
    value = clean_text(data, key, label, max_len=254).lower()
    if not _EMAIL.match(value):
        raise ValidationError(f"Enter a valid {label.lower()} address.", key)
    return value


def clean_password(data: dict, key: str = "password", label: str = "Password", *, strength: bool = True) -> str:
    """Passwords are never trimmed or altered. New passwords need 8-128 chars with a letter and a digit."""
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} is required.", key)
    if len(value) > 128:
        raise ValidationError(f"{label} must be at most 128 characters.", key)
    if strength:
        if len(value) < 8:
            raise ValidationError(f"{label} must be at least 8 characters.", key)
        if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
            raise ValidationError(f"{label} must contain at least one letter and one number.", key)
    return value
