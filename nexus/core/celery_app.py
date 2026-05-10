from celery import Celery
from core.config import settings

celery_app = Celery(
    "nexus",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "scheduler.deadline_monitor",
        "scheduler.scheduled_crawl",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "crawl_*": {"queue": "crawl"},
        "enrich_*": {"queue": "enrich"},
        "score_*": {"queue": "score"},
        "cleanup_*": {"queue": "cleanup"},
    },
    beat_schedule={
        "run-deadline-monitor": {
            "task": "scheduler.deadline_monitor.run_deadline_monitor",
            "schedule": 3600.0,
        },
        "run-scheduled-crawl": {
            "task": "scheduler.scheduled_crawl.run_scheduled_crawl",
            "schedule": 86400.0,
            "args": ("scheduled",),
        },
    },
)
