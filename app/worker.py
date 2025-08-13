"""
Celery Worker Configuration
Background task processing for Islamic Q&A system
"""

from celery import Celery
from celery.schedules import crontab
import asyncio
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Create Celery app
celery_app = Celery(
    "islamqa_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.scraping_tasks",
        "app.tasks.ml_tasks", 
        "app.tasks.maintenance_tasks",
        "app.tasks.automation_tasks"
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic tasks schedule
celery_app.conf.beat_schedule = {
    # Daily scraping tasks
    'scrape-islamqa-daily': {
        'task': 'app.tasks.scraping_tasks.scrape_islamqa',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
    'scrape-dar-al-ifta-daily': {
        'task': 'app.tasks.scraping_tasks.scrape_dar_al_ifta',
        'schedule': crontab(hour=3, minute=0),  # 3 AM daily
    },
    
    # ML model maintenance
    'rebuild-ml-index': {
        'task': 'app.tasks.ml_tasks.rebuild_faiss_index',
        'schedule': crontab(hour=4, minute=0),  # 4 AM daily
    },
    'update-embeddings': {
        'task': 'app.tasks.ml_tasks.update_question_embeddings',
        'schedule': crontab(hour=5, minute=0, day_of_week=0),  # Weekly on Sunday
    },
    
    # System maintenance
    'cleanup-old-data': {
        'task': 'app.tasks.maintenance_tasks.cleanup_old_data',
        'schedule': crontab(hour=1, minute=0),  # 1 AM daily
    },
    'backup-database': {
        'task': 'app.tasks.maintenance_tasks.backup_database',
        'schedule': crontab(hour=6, minute=0),  # 6 AM daily
    },
    
    # GitHub automation
    'daily-github-commit': {
        'task': 'app.tasks.automation_tasks.daily_commit',
        'schedule': crontab(hour=20, minute=0),  # 8 PM daily
    },
    
    # Health checks
    'system-health-check': {
        'task': 'app.tasks.maintenance_tasks.system_health_check',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
}


@celery_app.task(bind=True)
def debug_task(self):
    """Debug task for testing"""
    print(f'Request: {self.request!r}')


if __name__ == '__main__':
    celery_app.start()
