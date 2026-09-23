# Terminal 2: the worker that actually executes tasks
#  if you hit errors, use:  celery -A app.celery_app worker --loglevel=info --pool=solo)

# Terminal 3: the scheduler that fires the periodic task on a timer
# celery -A app.celery_app beat --loglevel=info

import os
from celery import Celery
from celery.schedules import crontab
from .config import settings

BROKER_URL = settings.BROKER_URL

celery_app = Celery(
    "seat_reservation",
    broker=BROKER_URL,
    backend=None,
    include=["app.tasks"],
)

#acknowledge tasks only after they finish => if a worker crashes mid-task, RabbitMQ redelivers it instead of losing it
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multilier=1,  # one worker handles only one task 
    timezone="UTC",
    enable_utc=True,
)

#BEAT SCHEDULE: automate and repeats the reading of dict and enqueues and named tasks
celery_app.conf.beat_schedule = {
    "release-expired-seat-holds": {
        "task": "app.tasks.release_expired_holds",
        #"schedule": crontab(minute=5),
        "schedule": 60.0,
    },
}