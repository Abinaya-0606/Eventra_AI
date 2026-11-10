# Eventra AI container image:  docker build -t eventra-ai .   then see "Docker" in the README.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Keep the database and the vector store on a volume so they survive restarts: -v eventra-data:/data
ENV DATABASE_PATH=/data/eventai.db CHROMA_DIR=/data/chroma_db
RUN mkdir -p /data && useradd -m eventra && chown -R eventra /app /data
USER eventra
EXPOSE 8000
# One worker on purpose (login-lockout counters are in memory and SQLite has a single writer); threads serve parallel requests.
CMD ["sh", "-c", "python ingest.py && gunicorn run:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT}"]
