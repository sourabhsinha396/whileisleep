"""The AI agent: answers a visitor from the knowledge base and the workspace's tools.

It runs a tool-calling loop on OpenRouter with the organization's key and model. Built-in
tools search the knowledge base and hand off to a person; each workspace adds HTTP tools
(apps.agent.models.Tool) that fetch live data from its own systems. The model finishes by
calling reply_to_visitor with the reply text, the articles worth linking, and whether to
offer a person; the server turns the last two into an A2UI surface. (A final tool works on
any tool-capable model, unlike structured-output modes.)

Without a key and model, or when OpenRouter fails, it falls back to a keyword search.
"""

import json
import logging
import threading
import uuid

from django.conf import settings
from django.db import close_old_connections

from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message
from apps.knowledge.models import Article
from apps.knowledge.search import search

from . import a2ui, http_tools, openrouter
from .models import Tool

log = logging.getLogger(__name__)

MAX_STEPS = 6
HISTORY_MESSAGES = 20
REPLY_TOOL = "reply_to_visitor"

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "The message to send the visitor."},
        "article_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Knowledge base articles worth linking under the reply (at most 3).",
        },
        "offer_human": {
            "type": "boolean",
            "description": "True when you could not fully answer and a teammate should take over.",
        },
    },
    "required": ["reply", "article_ids", "offer_human"],
}

BUILTIN_TOOLS = [
    {
        "name": REPLY_TOOL,
        "description": "Send your answer to the visitor. Always finish by calling this exactly once.",
        "input_schema": REPLY_SCHEMA,
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Search this business's help center articles. Returns matching articles with id, title "
            "and text. Use it for policies, how-tos, pricing rules, shipping, refunds and similar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Keywords to search for."}},
            "required": ["query"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Hand the conversation to a human teammate. Use it when the visitor asks for a person, "
            "is upset, or needs something you cannot do with your tools (refunds, account changes)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "One line for the teammate."}},
            "required": ["reason"],
        },
    },
]

SYSTEM_PROMPT = """You are the support assistant for {name}{website}, replying in the chat widget on its website.

Answer only from what your tools return: the knowledge base and the business's own data tools. \
When the visitor asks about anything that changes (products, availability, prices, orders, \
accounts), call the matching tool before answering. If the tools don't cover it, say you don't \
know and offer a teammate. Never guess facts about the business.

Write like a helpful person in a chat: short (one to four sentences), plain words, no headings. \
Use the visitor's language. Include links from tool results when they help, as markdown [text](url).

When you have the answer, call reply_to_visitor; don't write it as plain text.
{instructions}"""


def maybe_reply(conversation: Conversation) -> None:
    """Called after a visitor message. Replies unless the bot is off or a person took over."""
    if not conversation.workspace.ai_enabled or conversation.human_requested:
        return
    if settings.BOT_SYNC:
        reply(conversation.pk)
    else:
        threading.Thread(target=_reply_in_thread, args=(conversation.pk,), daemon=True).start()


def _reply_in_thread(conversation_id: int) -> None:
    try:
        reply(conversation_id)
    except Exception:
        log.exception("Bot failed on conversation %s", conversation_id)
    finally:
        close_old_connections()


def reply(conversation_id: int) -> Message | None:
    conversation = Conversation.objects.select_related("workspace__organization", "visitor").get(pk=conversation_id)
    history = chat_history(conversation)
    if not history:
        return None
    result = None
    if conversation.workspace.organization.llm_ready:
        try:
            result = run_agent(conversation, history)
        except openrouter.OpenRouterError as error:
            log.warning("OpenRouter failed on conversation %s: %s", conversation_id, error)
            # The team sees why the bot fell back, e.g. an expired key or no credits.
            add_message(conversation, Message.Sender.SYSTEM, f"AI agent error: {error}", is_note=True)
    if result is None:
        result = keyword_answer(conversation, history[-1]["content"])

    # The visitor may have asked for a person while the model was thinking.
    conversation.refresh_from_db(fields=["human_requested"])
    articles = list(
        Article.objects.filter(workspace=conversation.workspace, published=True, pk__in=result["article_ids"][:3])
    )
    surface = a2ui.reply_actions(
        f"reply_{uuid.uuid4().hex[:12]}", articles, result["offer_human"] and not conversation.human_requested
    )
    return add_message(conversation, Message.Sender.BOT, result["reply"], a2ui=surface)


def chat_history(conversation: Conversation) -> list[dict]:
    """The visible conversation as alternating user/assistant turns, ending with the visitor."""
    rows = list(
        conversation.messages.filter(is_note=False)
        .exclude(sender=Message.Sender.SYSTEM)
        .order_by("-id")[:HISTORY_MESSAGES]
    )
    turns: list[dict] = []
    for message in reversed(rows):
        role = "user" if message.sender == Message.Sender.VISITOR else "assistant"
        if not message.body:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + message.body
        else:
            turns.append({"role": role, "content": message.body})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    if not turns or turns[-1]["role"] != "user":
        return []
    return turns


def system_prompt(workspace) -> str:
    return SYSTEM_PROMPT.format(
        name=workspace.name,
        website=f" ({workspace.website})" if workspace.website else "",
        instructions=f"\nInstructions from the business:\n{workspace.ai_instructions}"
        if workspace.ai_instructions
        else "",
    )


def tool_definitions(tools: list[Tool]) -> list[dict]:
    """Built-in and workspace tools in OpenAI function format."""
    specs = [(t["name"], t["description"], t["input_schema"]) for t in BUILTIN_TOOLS]
    for tool in tools:
        schema = tool.input_schema or {}
        specs.append((tool.name, tool.description, schema if schema.get("type") == "object" else {}))
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema or {"type": "object", "properties": {}},
            },
        }
        for name, description, schema in specs
    ]


def parse_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def final_answer(arguments: dict) -> dict:
    ids = arguments.get("article_ids") or []
    return {
        "reply": str(arguments.get("reply", "")).strip(),
        "article_ids": [int(i) for i in ids if isinstance(i, int | str) and str(i).isdigit()],
        "offer_human": bool(arguments.get("offer_human")),
    }


def run_agent(conversation: Conversation, history: list[dict]) -> dict | None:
    workspace = conversation.workspace
    organization = workspace.organization
    tools = {t.name: t for t in Tool.objects.filter(workspace=workspace, enabled=True)}
    definitions = tool_definitions(list(tools.values()))
    messages: list[dict] = [{"role": "system", "content": system_prompt(workspace)}, *history]
    trace: list[str] = []
    result = None

    for _ in range(MAX_STEPS):
        message = openrouter.complete(organization.openrouter_api_key, organization.llm_model, messages, definitions)
        calls = message.get("tool_calls") or []
        if not calls:
            # Plain text instead of reply_to_visitor: still a usable answer.
            text = (message.get("content") or "").strip()
            result = {"reply": text, "article_ids": [], "offer_human": False} if text else None
            break
        # Keep the whole message (reasoning details included) so the next turn continues it.
        messages.append({k: v for k, v in message.items() if v is not None})
        for call in calls:
            name = (call.get("function") or {}).get("name", "")
            arguments = parse_arguments((call.get("function") or {}).get("arguments"))
            if name == REPLY_TOOL:
                result = final_answer(arguments)
                content, is_error = "Sent.", False
            else:
                content, is_error = call_tool(conversation, tools, name, arguments)
                trace.append(f"{name}({json.dumps(arguments, ensure_ascii=False)}) → {content[:300]}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": ("Error: " if is_error else "") + content,
                }
            )
        if result is not None:
            break

    if trace:
        # Teammates see what the bot looked up, to check its answers.
        add_message(conversation, Message.Sender.SYSTEM, "Bot looked up:\n" + "\n".join(trace), is_note=True)
    if result is None or not result["reply"]:
        return None
    return result


def call_tool(conversation: Conversation, tools: dict[str, Tool], name: str, inputs: dict) -> tuple[str, bool]:
    if name == "search_knowledge_base":
        found = search(conversation.workspace, str(inputs.get("query", "")), limit=4)
        if not found:
            return "No matching articles.", False
        return json.dumps([{"id": a.id, "title": a.title, "text": a.body[:3000]} for a in found]), False
    if name == "handoff_to_human":
        request_human(conversation, str(inputs.get("reason", "")))
        return "Handed off. Tell the visitor a teammate will reply here.", False
    tool = tools.get(name)
    if tool is None:
        return f"Unknown tool {name}.", True
    return http_tools.run(tool, inputs, conversation.visitor)


def request_human(conversation: Conversation, reason: str = "") -> None:
    if conversation.human_requested:
        return
    conversation.human_requested = True
    conversation.unread = True
    conversation.save(update_fields=["human_requested", "unread"])
    note = "Visitor asked for a person." + (f" Reason: {reason}" if reason else "")
    add_message(conversation, Message.Sender.SYSTEM, note, is_note=True)


def keyword_answer(conversation: Conversation, question: str) -> dict:
    found = search(conversation.workspace, question)
    if found:
        return {
            "reply": "Here's what I found in our help center. Does one of these answer it?",
            "article_ids": [a.id for a in found],
            "offer_human": True,
        }
    return {
        "reply": "I couldn't find an answer to that. A teammate can help you here.",
        "article_ids": [],
        "offer_human": True,
    }
