"""Google's "I'm not a robot" checkbox (reCAPTCHA v2) in front of forms that anyone can send.

Only where its two keys are set; without them every form works as if there were none. The person
waits for Google's answer, so this is the one call to a service inside a web request, with its short
deadline, its "counts as down" and a limit per address (apps.integrations.http).
"""

import logging

from django.conf import settings
from ninja.errors import HttpError

from apps.conversations.limits import hit
from apps.integrations import http
from whileisleep.client_ip import client_ip

log = logging.getLogger(__name__)

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
TOTAL_SECONDS = 4
CHECKS_PER_MINUTE = 20


def site_key() -> str:
    """What the page needs to show the checkbox. Empty: there is none."""
    return settings.RECAPTCHA_SITE_KEY if settings.RECAPTCHA_ENABLED else ""


def require(request, token: str) -> None:
    """Stops the request unless its box was ticked by a person. Each token is good for one check."""
    if not settings.RECAPTCHA_ENABLED:
        return
    if not token:
        raise HttpError(400, "Tick the box to show you're not a robot.")
    if not hit("captcha", client_ip(request) or "-", CHECKS_PER_MINUTE, 60):
        raise HttpError(429, "Too many tries. Wait a minute and try again.")
    try:
        answer = http.request(
            "POST",
            VERIFY_URL,
            data={"secret": settings.RECAPTCHA_SECRET_KEY, "response": token},
            total_seconds=TOTAL_SECONDS,
        ).json()
        passed, problems = answer["success"] is True, answer.get("error-codes", [])
    except (http.Unreachable, ValueError, KeyError, TypeError, AttributeError) as error:
        # Letting everyone in meanwhile would make it useless: an attacker only has to wait.
        log.warning("reCAPTCHA couldn't be checked: %s", error)
        raise HttpError(503, "We couldn't check that you're not a robot. Try again in a minute.") from error
    if passed:
        return
    if any("secret" in str(problem) for problem in problems):
        log.error("Google refuses RECAPTCHA_SECRET_KEY: %s", problems)
    raise HttpError(400, "The robot check didn't pass or has expired. Tick the box again.")
