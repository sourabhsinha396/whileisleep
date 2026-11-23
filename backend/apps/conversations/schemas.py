from datetime import datetime
from typing import Any

from ninja import Schema
from pydantic import Field


class VisitorOut(Schema):
    id: int
    name: str
    email: str
    online: bool
    current_url: str
    page_title: str
    referrer: str
    user_agent: str
    first_seen: datetime
    last_seen: datetime
    conversation_id: int | None = None


class MessageOut(Schema):
    id: int
    sender: str
    author_name: str = ""
    body: str
    a2ui: list[dict[str, Any]] | None = None
    is_note: bool
    created_at: datetime


class ConversationRow(Schema):
    id: int
    status: str
    unread: bool
    human_requested: bool
    assignee_id: int | None
    last_message_at: datetime
    preview: str
    visitor: VisitorOut


class ConversationDetail(ConversationRow):
    messages: list[MessageOut]


class ReplyIn(Schema):
    body: str = Field(min_length=1, max_length=10000)
    is_note: bool = False


class ConversationPatch(Schema):
    status: str | None = None
    assignee_id: int | None = None
    # The bot answers again when this goes back to False.
    human_requested: bool | None = None


# --- Widget ---


class WidgetConfigOut(Schema):
    name: str
    website: str
    color: str
    greeting: str
    ai_enabled: bool


class WidgetSessionIn(Schema):
    url: str = ""
    title: str = ""
    referrer: str = ""
    name: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=254)


class WidgetSessionOut(Schema):
    token: str
    visitor_id: int
    conversation_id: int | None
    # Messages newer than this id are unread by the visitor; the widget compares it to what it has.
    last_message_id: int | None


class WidgetMessageIn(Schema):
    body: str = Field(min_length=1, max_length=5000)


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
