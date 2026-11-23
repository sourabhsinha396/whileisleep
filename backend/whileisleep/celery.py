"""The Celery app: the worker that writes AI replies outside web requests.

    celery -A whileisleep worker --pool threads --concurrency 16
    celery -A whileisleep beat

Settings are the CELERY_* names in whileisleep/settings/base.py. Tasks live in each app's
tasks.py (apps/agent/tasks.py).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "whileisleep.settings.local")

app = Celery("whileisleep")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
