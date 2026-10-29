# Debian/glibc base — required for Oz cloud agents (Alpine/musl not supported).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    WORKOUT_DB_PATH=/app/data/workouts.db \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Install uv + gosu (drop root after fixing volume perms)
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (UID 1000) — matches Oz agent user conventions.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash app \
    && mkdir -p /app/data \
    && chown -R app:app /app

COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src ./src
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER app
RUN uv sync --no-dev

# Stay root only for entrypoint chown of mounted data volume; then gosu -> app.
USER root
ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "workout_tracker.main:app", "--host", "0.0.0.0", "--port", "8000"]
