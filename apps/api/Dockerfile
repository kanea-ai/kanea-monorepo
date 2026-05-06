# syntax=docker/dockerfile:1.7
# Multi-stage build for the Kanea FastAPI service.
# Built from the monorepo root: `docker build -f apps/api/Dockerfile .`

# ---------- Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /build

COPY apps/api/pyproject.toml apps/api/poetry.lock ./
RUN poetry export --without dev --without-hashes -f requirements.txt -o requirements.txt

# Install into an isolated prefix so we can copy the result into the runtime stage.
RUN pip install --prefix=/install -r requirements.txt

# ---------- Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Run as non-root.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini

USER app

EXPOSE 8080

# Cloud Run sets $PORT; bind 0.0.0.0 so the container is reachable.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
