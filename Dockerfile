FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies before copying the code, so a code change does not
# reinstall them. Runtime dependencies only: no test or lint tools.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Unprivileged user. /data is created here and owned by that user, so the
# named volume mounted on it starts with the right permissions.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir /data \
    && chown appuser:appuser /data

COPY app ./app

USER appuser

ENV DATABASE_URL=sqlite:////data/issues.db

EXPOSE 8000

# One worker: SQLite allows a single writer at a time.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
