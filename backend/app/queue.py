from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "audio_notes",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

import app.tasks  # noqa: E402, F401

