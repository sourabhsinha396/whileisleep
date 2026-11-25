"""Emails about accounts. On the queue of the jobs that wait on outside services (settings.CELERY_TASK_ROUTES)."""

import logging

from celery import shared_task

from whileisleep import mail

from . import passwords

log = logging.getLogger(__name__)

# Seconds before each new try.
DELAYS = (10, 60, 300)


def send(task, message: mail.Mail) -> None:
    try:
        mail.send(message)
    except mail.NotSent as error:
        if task.request.retries >= len(DELAYS):
            log.error("An email was given up on: %s", error)
            return
        raise task.retry(countdown=DELAYS[task.request.retries]) from error


@shared_task(bind=True, max_retries=len(DELAYS))
def send_reset(self, email: str) -> None:
    # Here, not in the request, which so takes as long for an address without an account. And the
    # link never waits in the queue.
    message = passwords.reset_mail(email)
    if message:
        send(self, message)


@shared_task(bind=True, max_retries=len(DELAYS))
def send_changed(self, email: str) -> None:
    send(self, passwords.changed_mail(email))
