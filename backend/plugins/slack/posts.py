"""What whileisleep's messages in Slack look like."""

from urllib.parse import urlsplit

from apps.integrations.sdk import (
    Conversation,
    Message,
    display_name,
    email_is_verified,
    inbox_url,
    needs_person,
)

from .text import clip, escape, from_markdown, link

# What the buttons send back.
RESOLVE, REOPEN, TO_AI, OPEN = "resolve", "reopen", "to_ai", "open"
HOW_TO_REPLY = "Reply in this thread to answer. Start with `note:` to write to your team only."


def section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": clip(text)}}


def context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": clip(text)}]}


def button(action: str, label: str, **extra) -> dict:
    return {"type": "button", "action_id": action, "text": {"type": "plain_text", "text": label}, **extra}


def headline(conversation: Conversation) -> str:
    name = escape(conversation.visitor.display_name)
    if conversation.status == Conversation.Status.RESOLVED:
        return f":white_check_mark: Resolved: {name}"
    if needs_person(conversation):
        return f":bell: {name} needs a person"
    return f":robot_face: The AI is answering {name}"


def who(conversation: Conversation) -> str:
    visitor = conversation.visitor
    facts = []
    if visitor.email:
        facts.append(escape(visitor.email) + (" (verified)" if email_is_verified(visitor) else ""))
    if visitor.current_url:
        page = urlsplit(visitor.current_url)
        # The label says where it really goes: the address came from the visitor's browser.
        facts.append("on " + link(visitor.current_url, (page.netloc + page.path)[:80] or "a page"))
    facts.append(escape(conversation.workspace.name))
    return " · ".join(facts)


def root(conversation: Conversation, reason: str = "", mention: str = "") -> dict:
    """The message the thread hangs from. Rebuilt whenever the conversation's state changes."""
    title = f"*{headline(conversation)}*"
    resolved = conversation.status == Conversation.Status.RESOLVED
    buttons = [button(OPEN, "Open in inbox", url=inbox_url(conversation))]
    if resolved:
        buttons.append(button(REOPEN, "Reopen"))
    else:
        buttons.append(button(RESOLVE, "Resolve"))
        if conversation.human_requested and conversation.workspace.ai_enabled:
            buttons.append(button(TO_AI, "Back to AI"))
    blocks = [section(f"{mention} {title}" if mention else title)]
    if reason and not resolved:
        blocks.append(section(quote(escape(reason))))
    blocks += [context(who(conversation)), {"type": "actions", "elements": buttons}]
    return {"text": clip(headline(conversation)), "blocks": blocks}


def quote(text: str) -> str:
    return "\n".join(f">{line}" for line in text.split("\n"))


def author(message: Message) -> str:
    if message.sender == Message.Sender.VISITOR:
        return escape(message.conversation.visitor.display_name)
    if message.sender == Message.Sender.AGENT and message.author:
        return escape(display_name(message.author))
    return "AI" if message.sender == Message.Sender.BOT else "Teammate"


def content(message: Message) -> str:
    plain = message.sender == Message.Sender.VISITOR
    parts = [escape(message.body) if plain else from_markdown(message.body)] if message.body else []
    parts += [f":paperclip: {link(file.url, file.name)}" for file in message.attachments.all()]
    if message.form:
        parts.append("_(with a form to fill in)_")
    return "\n".join(parts)


def said(message: Message) -> dict:
    """One message of the conversation."""
    if message.is_note:
        label = f":memo: *Note from {author(message)}*"
    else:
        label = f"*{author(message)}*" + (" (visitor)" if message.sender == Message.Sender.VISITOR else "")
    text = clip(f"{label}\n{content(message)}")
    return {"text": text, "blocks": [section(text)]}


def transcript(messages: list[Message]) -> dict:
    """What was said before the thread began, and how to answer."""
    blocks = [section(quote(f"*{author(m)}:* {content(m)}")) for m in messages]
    return {"text": "The chat so far", "blocks": [*blocks, context(HOW_TO_REPLY)]}
