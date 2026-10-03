# syntax=docker/dockerfile:1
# Single image for both the API and the Celery worker (the command differs).
# ffmpeg ships as a static binary inside the imageio-ffmpeg wheel, so there is
# no system ffmpeg dependency.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UPLOAD_DIR=/app/uploads

WORKDIR /app

# tini reaps zombies and forwards signals so Celery/uvicorn shut down cleanly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so application edits reuse the cached layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
# Overridden by the worker/compose to run celery; migrations run as a one-shot.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
