"""Emails, sent through Brevo. Only where its key and a sender are set; without them, features that need
an email (a forgotten password) aren't there.

Only background jobs call `send`: Brevo may be slow or down.
"""

import logging
from dataclasses import dataclass
from html import escape

from django.conf import settings

from apps.integrations import http

log = logging.getLogger(__name__)

SEND_URL = "https://api.brevo.com/v3/smtp/email"


class NotSent(Exception):
    """Worth another try later."""


@dataclass
class Mail:
    to: str
    subject: str
    # Paragraphs of plain text.
    lines: list[str]
    # A button under them: what it says, and where it goes.
    button: tuple[str, str] | None = None
    # A last, smaller paragraph.
    note: str = ""

    def text(self) -> str:
        parts = [*self.lines, *(["{}:\n{}".format(*self.button)] if self.button else []), self.note]
        return "\n\n".join(part for part in parts if part)

    def html(self) -> str:
        """Written for mail programs: one column, styles inside."""
        parts = [f'<p style="margin:0 0 16px">{escape(line)}</p>' for line in self.lines]
        if self.button:
            label, url = (escape(part) for part in self.button)
            parts.append(
                f'<p style="margin:24px 0"><a href="{url}" style="display:inline-block;padding:12px 22px;'
                'border-radius:999px;background:#0070d8;color:#ffffff;font-weight:600;text-decoration:none">'
                f"{label}</a></p>"
                f'<p style="margin:0 0 16px;font-size:13px;color:#667085;word-break:break-all">{url}</p>'
            )
        if self.note:
            parts.append(f'<p style="margin:0;font-size:13px;color:#667085">{escape(self.note)}</p>')
        return (
            '<div style="max-width:520px;margin:0 auto;padding:24px;font-family:Arial,sans-serif;'
            'font-size:15px;line-height:1.6;color:#101828">'
            f'<p style="margin:0 0 24px;font-size:18px;font-weight:700">whileisleep</p>{"".join(parts)}</div>'
        )


def send(mail: Mail) -> None:
    """Raises NotSent when trying again may help. Anything else is for whoever runs the server."""
    if not settings.MAIL_ENABLED:
        return
    try:
        response = http.request(
            "POST",
            SEND_URL,
            headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
            json={
                "sender": {"email": settings.MAIL_FROM, "name": settings.MAIL_FROM_NAME},
                "to": [{"email": mail.to}],
                "subject": mail.subject,
                "textContent": mail.text(),
                "htmlContent": mail.html(),
            },
        )
    except http.Unreachable as error:
        raise NotSent(str(error)) from error
    if response.status_code == 429 or response.status_code >= 500:
        raise NotSent(f"Brevo answered {response.status_code}.")
    if response.status_code >= 400:
        # Such as a wrong key, or a sender that Brevo hasn't verified.
        log.error("Brevo refused an email (%s): %s", response.status_code, problem(response))


def problem(response) -> str:
    try:
        return str(response.json().get("message", ""))[:200]
    except (ValueError, AttributeError):
        return ""
