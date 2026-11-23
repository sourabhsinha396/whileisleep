# Loads the Celery app with Django, so tasks declared with @shared_task bind to it.
from .celery import app as celery_app

__all__ = ("celery_app",)
