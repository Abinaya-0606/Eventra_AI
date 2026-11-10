"""Entry point:  python run.py   (development)   |   gunicorn "run:app"   (production)."""
import os

from app import create_app

app = create_app(os.getenv("APP_ENV", "development"))

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)))
