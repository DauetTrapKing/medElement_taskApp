from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

app = Celery("api")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.timezone = "Asia/Almaty"
app.conf.enable_utc = False
app.conf.update(
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_default_rate_limit="1/s",
)

app.conf.beat_schedule = {
    "collect-appointments-every-2-hours": {
        "task": "your_app.tasks.collect_appointments_task",  ### работает раз в два часа но начинае но ранится сразу
        "schedule": crontab(minute=0, hour="*/2"),  # каждые два часа
    },
}
