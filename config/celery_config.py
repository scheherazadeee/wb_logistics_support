from celery import Celery
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))



celery_app = Celery(
    'wb_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0',
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Europe/Moscow',
    task_track_started=True,
    task_time_limit=23 * 60 * 60,           # < visibility_timeout, иначе передоставка
    task_acks_late=True,
    task_reject_on_worker_lost=True,        # не передоставлять при SIGKILL
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        'visibility_timeout': 24 * 60 * 60,
    },
)

import src.ingestion.tasks 
 
