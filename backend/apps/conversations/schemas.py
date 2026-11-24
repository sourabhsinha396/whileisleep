from datetime import datetime
from typing import Any

from django.conf import settings
from ninja import Schema
from pydantic import Field, field_validator, model_validator

from .attachments import MAX_PER_MESSAGE


class AttributeOut(Schema):
    key: str
    value: str | int | float | bool
    # Who said so: verified, agent, rule, host, visitor or ai.
    source: str


class AttributeIn(Schema):
    value: str | int | float | bool


class VisitorOut(Schema):
    id: int
    name: str
    email: str
    # The host site signed for this visitor's identity; verified attributes can be relied on.
    verified: bool = False
    attributes: list[AttributeOut] = []
    online: bool
    current_url: str
    page_title: str
    referrer: str
    user_agent: str
    first_seen: datetime
    last_seen: datetime
    conversation_id: int | None = None


class AttachmentOut(Schema):
    id: int
    name: str
    url: str
    content_type: str
    size: int
    # Pictures only.
    width: int | None = None
    height: int | None = None


class WithFiles(Schema):
    """A message to send: text, files that were uploaded for it, or both."""

    attachments: list[int] = Field(default_factory=list, max_length=MAX_PER_MESSAGE)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.body.strip() and not self.attachments:
            raise ValueError("Write a message or attach a file.")
        return self


class MessageOut(Schema):
    id: int
    sender: str
    author_name: str = ""
    author_photo: str = ""
    body: str
    a2ui: list[dict[str, Any]] | None = None
    is_note: bool
    intent: str = ""
    form_submitted: bool = False
    attachments: list[AttachmentOut] = []
    created_at: datetime


class ConversationRow(Schema):
    id: int
    status: str
    unread: bool
    human_requested: bool
    tags: list[str] = []
    attributes: list[AttributeOut] = []
    assignee_id: int | None
    last_message_at: datetime
    preview: str
    visitor: VisitorOut


class ConversationDetail(ConversationRow):
    messages: list[MessageOut]


class ReplyIn(WithFiles):
    body: str = Field("", max_length=10000)
    is_note: bool = False


class OpeningIn(Schema):
    body: str = Field(min_length=1, max_length=10000)


class ConversationPatch(Schema):
    status: str | None = None
    assignee_id: int | None = None
    # The bot answers again when this goes back to False.
    human_requested: bool | None = None


# --- Widget ---


class TeamFaceOut(Schema):
    name: str
    photo_url: str


class WidgetConfigOut(Schema):
    name: str
    website: str
    color: str
    logo_url: str
    greeting: str
    ai_enabled: bool
    # Visitors can send files: the organization connected its own bucket for them.
    uploads_enabled: bool = False
    # A few teammates with photos, for the header.
    team: list[TeamFaceOut] = []
    max_message_length: int = settings.VISITOR_MESSAGE_MAX_CHARS


AttributeValue = str | int | float | bool


class WidgetSessionIn(Schema):
    url: str = ""
    title: str = ""
    referrer: str = ""
    # From window.whileisleep.identify(): what the host page says about its signed-in user.
    name: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=254)
    attributes: dict[str, AttributeValue] = Field(default_factory=dict, max_length=20)
    # A token the host site's server signed for its user (apps.conversations.identity).
    identity_token: str | None = Field(None, max_length=4000)

    def details(self) -> dict:
        """Everything identify() sent, as attributes."""
        named = {"name": self.name, "email": self.email}
        return self.attributes | {key: value for key, value in named.items() if value}


class WidgetSessionOut(Schema):
    token: str
    visitor_id: int
    conversation_id: int | None
    # Messages newer than this id are unread by the visitor; the widget compares it to what it has.
    last_message_id: int | None


IntentValue = str | int | float | bool


class WidgetMessageIn(WithFiles):
    body: str = Field("", max_length=settings.VISITOR_MESSAGE_MAX_CHARS)
    # Set by a button on the host site that opened the chat (window.whileisleep.open(text, {intent, data})).
    intent: str = Field("", max_length=64, pattern=r"^[a-z0-9_.-]*$")
    data: dict[str, IntentValue] = Field(default_factory=dict, max_length=20)

    @field_validator("data")
    @classmethod
    def short_values(cls, data: dict) -> dict:
        for key, value in data.items():
            if len(key) > 40 or len(str(value)) > 300:
                raise ValueError("intent data keys must be at most 40 characters and values 300")
        return data


class WidgetActionIn(Schema):
    """An A2UI action event from a surface in one of the bot's messages."""

    name: str = Field(max_length=64)
    surfaceId: str = Field("", max_length=64)
    sourceComponentId: str = Field("", max_length=64)
    context: dict[str, Any] = {}


class WidgetMessagesOut(Schema):
    conversation_id: int | None
    human_requested: bool = False
    messages: list[MessageOut]


class ArticleRef(Schema):
    id: int
    title: str
    excerpt: str


class ArticleOut(Schema):
    id: int
    title: str
    body: str
