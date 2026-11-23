from django.core.management.base import BaseCommand
from django.utils import autoreload

from whileisleep.celery import app


def run_worker():
    # Threads, like production: replies spend their time waiting on the LLM. Beat runs
    # inside (-B) so development needs one process, not two.
    app.worker_main(["worker", "--pool", "threads", "--concurrency", "8", "--loglevel", "info", "-B"])


class Command(BaseCommand):
    help = "Development only: runs the Celery worker and restarts it when the code changes."

    def handle(self, *args, **options):
        autoreload.run_with_reloader(run_worker)
