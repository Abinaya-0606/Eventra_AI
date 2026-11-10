"""Create the initial Eventra AI administrator from environment variables.

    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-long-passphrase-1' python seed_admin.py

Reads ADMIN_EMAIL, ADMIN_PASSWORD and (optionally) ADMIN_NAME from the environment or from .env. Safe to run
again: an existing admin is left untouched. Same as:  flask --app run seed-admin
"""
import os
import sys

from app import create_app
from app.services.admin_seed import SeedError, read_env_credentials, seed_admin


def main(argv: list[str]) -> int:
    app = create_app(os.getenv("APP_ENV", "development"))
    try:
        name, email, password = read_env_credentials()
        with app.app_context():
            result = seed_admin(name, email, password, promote="--promote" in argv)
    except SeedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print({"created": f"Admin {email} created. Sign in at /admin/login, then remove ADMIN_PASSWORD from your environment.",
           "exists": f"{email} is already an admin. Nothing changed.",
           "promoted": f"{email} is now an admin (password unchanged)."}[result])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
