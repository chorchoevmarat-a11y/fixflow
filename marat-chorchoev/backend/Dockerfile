FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

# Dependencies first so they are cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && mkdir -p /app/uploads

EXPOSE 8000

# The first start with SEED_ON_START=1 replays the demo history through the API before serving, so give it time.
HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=6 \
    CMD curl -fsS http://localhost:8000/api/v1/health/ready || exit 1

# Wait for PostgreSQL, apply migrations, optionally seed, then start several workers (SEC-07).
# Seeding is explicit (see README) so restarts never touch existing data. Note the `if`: a `&&` placed
# inside a `${VAR:+...}` expansion is passed to the seed command as a literal argument and crashes it.
CMD ["sh", "-c", "uv run --no-sync python -m app.cli wait-for-db && uv run --no-sync alembic upgrade head && if [ -n \"$SEED_ON_START\" ]; then uv run --no-sync python -m app.cli seed; fi && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-4}"]
