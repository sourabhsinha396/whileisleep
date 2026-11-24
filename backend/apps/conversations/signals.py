"""What happens in conversations, announced for other apps to act on (apps.integrations does).

Receivers run inside the request or the job that caused the event, so they must be quick:
write down what to do and let a worker do it.
"""

from dataclasses import dataclass, field

from django.dispatch import Signal

MESSAGE = "message"  # someone wrote; `message` is set, and may be an internal note
PERSON_REQUESTED = "person_requested"  # handed to the team; data["reason"] says why
RESOLVED = "resolved"
REOPENED = "reopened"
AI_RESUMED = "ai_resumed"  # a teammate gave the conversation back to the AI


@dataclass(frozen=True)
class Event:
    name: str
    conversation: object
    message: object = None
    # The teammate who did it, if one did.
    by: object = None
    data: dict = field(default_factory=dict)
    # What caused it, when that was not the widget or the dashboard ("integration:12"), so a
    # service isn't told about what it just told us.
    origin: str = ""


# Sent with event=Event(...).
happened = Signal()


def announce(name: str, conversation, **details) -> None:
    happened.send(sender=None, event=Event(name, conversation, **details))
