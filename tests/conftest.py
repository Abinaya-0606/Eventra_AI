"""Shared pytest fixtures.

`client` is a logged-in ORGANIZER, `student_client` / `student2_client` are students, `admin_client` an admin,
`other` a second organizer and `anon` is not logged in.
"""
import os
import sys

import pytest
from flask.testing import FlaskClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.models import users  # noqa: E402
from app.security import throttle  # noqa: E402
from app.services import rag  # noqa: E402

PASSWORD = "Passw0rd!x"


class CSRFClient(FlaskClient):
    """Test client that sends a valid CSRF header on every POST (set `.csrf = False` to test rejection)."""
    csrf = True

    def open(self, *args, **kwargs):
        if self.csrf and (kwargs.get("method") or "GET").upper() in ("POST", "PUT", "PATCH", "DELETE"):
            with self.session_transaction() as sess:
                token = sess.setdefault("_csrf", "test-csrf-token")
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-CSRF-Token", token)
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


@pytest.fixture()
def app(tmp_path):
    rag._collection = None  # never reuse a vector store between tests
    throttle.clear()
    app = create_app("testing", {"DATABASE": str(tmp_path / "test.db")})
    app.test_client_class = CSRFClient
    return app


@pytest.fixture()
def anon(app):
    return app.test_client()


def make_user(app, email="organizer@example.com", name="Olive Organizer", role="organizer", password=PASSWORD):
    with app.app_context():
        return users.create_user(name, email, password, role=role)


def login(client, email="organizer@example.com", password=PASSWORD, **extra):
    return client.post("/login", data={"email": email, "password": password, **extra})


def admin_login(client, email="admin@example.com", password=PASSWORD, **extra):
    """Admins sign in on their own page (/admin/login); /login refuses admin accounts."""
    return client.post("/admin/login", data={"email": email, "password": password, **extra})


@pytest.fixture()
def client(app):
    make_user(app)
    c = app.test_client()
    assert login(c).status_code == 302
    return c


@pytest.fixture()
def admin_client(app):
    make_user(app, "admin@example.com", "Ada Admin", "admin")
    c = app.test_client()
    assert admin_login(c, "admin@example.com").status_code == 302
    return c


def make_client(app, email, role="organizer", name=None):
    """A second (or third) logged-in user, e.g. to test that users cannot see each other's data."""
    make_user(app, email, name or email.split("@")[0].title(), role)
    c = app.test_client()
    assert (admin_login if role == "admin" else login)(c, email).status_code == 302
    return c


@pytest.fixture()
def other(app):
    return make_client(app, "other@example.com", "organizer", "Olivia Other")


@pytest.fixture()
def student_client(app):
    return make_client(app, "stu@example.com", "student", "Stella Student")


@pytest.fixture()
def student2_client(app):
    return make_client(app, "stu2@example.com", "student", "Stan Student")
