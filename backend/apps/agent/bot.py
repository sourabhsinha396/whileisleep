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

from apps.conversations import attributes, limits
from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message
from apps.knowledge.models import Article
from apps.knowledge.search import search

from . import a2ui, forms, http_tools, openrouter
from .models import Playbook, Tool

log = logging.getLogger(__name__)

MAX_STEPS = 6
# Hard cap on rows read; the character budget in settings usually stops sooner.
HISTORY_MESSAGES = 40
REPLY_TOOL = "reply_to_visitor"
PLAYBOOK_TOOL = "read_playbook"
PLAYBOOK_TOOL_SPEC = {
    "name": PLAYBOOK_TOOL,
    "description": "Read the full instructions of one of the business's playbooks, by its exact title.",
    "input_schema": {
        "type": "object",
        "properties": {"title": {"type": "string", "description": "The playbook's title."}},
        "required": ["title"],
    },
}

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
        "form": forms.FORM_SCHEMA,
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

Your facts come from three places: what your tools return (the knowledge base and the business's \
own data tools), the business's instructions below, and any rule for this message. What the \
business tells you there is true; follow it. When the visitor asks about anything that changes \
(products, availability, prices, orders, accounts), call the matching tool before answering. If \
none of these covers a question, say you don't know and offer a teammate. Never make up facts \
about the business.

Write like a helpful person in a chat: short (one to four sentences), plain words, no headings. \
Use the visitor's language. Include links from tool results when they help, as markdown [text](url).

When you need details from the visitor (an email to notify them, an order number, a choice between \
options), add a form to reply_to_visitor instead of asking them to type it. Their answers come back \
as their next message.

When you have the answer, call reply_to_visitor; don't write it as plain text.
{instructions}"""


def will_reply(conversation: Conversation) -> bool:
    return conversation.workspace.ai_enabled and not conversation.human_requested


def maybe_reply(conversation: Conversation, instruction: str = "") -> None:
    """Called after a visitor message. Replies unless the bot is off or a person took over.
    `instruction` comes from a matched rule and applies to this answer only."""
    if not will_reply(conversation):
        return
    if conversation.workspace.organization.llm_ready and not limits.allow_ai_reply(conversation):
        # Daily AI cap reached for this visitor or workspace: a person takes it from here.
        request_human(conversation, "daily AI reply limit reached")
        add_message(conversation, Message.Sender.BOT, "Thanks! A teammate will reply here soon.")
        return
    if settings.BOT_SYNC:
        reply(conversation.pk, instruction)
    else:
        threading.Thread(target=_reply_in_thread, args=(conversation.pk, instruction), daemon=True).start()


def _reply_in_thread(conversation_id: int, instruction: str) -> None:
    try:
        reply(conversation_id, instruction)
    except Exception:
        log.exception("Bot failed on conversation %s", conversation_id)
    finally:
        close_old_connections()


def reply(conversation_id: int, instruction: str = "") -> Message | None:
    conversation = Conversation.objects.select_related("workspace__organization", "visitor").get(pk=conversation_id)
    history = chat_history(conversation)
    if not history:
        return None
    result = None
    if conversation.workspace.organization.llm_ready:
        try:
            result = run_agent(conversation, history, instruction)
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
    form_ui, form_meta = forms.attach(result["form"]) if result.get("form") else ([], None)
    if form_meta and instruction:
        # The form serves this instruction; its answers continue it (see actions.submit_form).
        form_meta["instruction"] = instruction
    # Several surfaces can ride on one message; the widget renders each.
    surfaces = [*(surface or []), *form_ui] or None
    return add_message(conversation, Message.Sender.BOT, result["reply"], a2ui=surfaces, form=form_meta)


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " …[cut]"


def recent_messages(conversation: Conversation) -> list[Message]:
    """The newest visible messages that fit the history budget, oldest first.

    Sized by characters, not count, so a chatty visitor costs the same as a quiet one. The
    last few always go in; what the conversation is about is pinned in the system prompt.
    """
    rows = (
        conversation.messages.filter(is_note=False)
        .exclude(sender=Message.Sender.SYSTEM)
        .exclude(body="")
        .order_by("-id")[:HISTORY_MESSAGES]
    )
    kept, used = [], 0
    for message in rows:
        size = min(len(message.body), settings.HISTORY_MESSAGE_CHARS)
        if len(kept) >= settings.HISTORY_MIN_MESSAGES and used + size > settings.HISTORY_BUDGET_CHARS:
            break
        kept.append(message)
        used += size
    return kept[::-1]


def chat_history(conversation: Conversation) -> list[dict]:
    """The visible conversation as alternating user/assistant turns, ending with the visitor."""
    turns: list[dict] = []
    for message in recent_messages(conversation):
        message.body = clip(message.body, settings.HISTORY_MESSAGE_CHARS)
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


def conversation_facts(conversation: Conversation) -> list[str]:
    """What the AI must know however much history is cut: who the visitor is, where they are,
    what they came for, and what's still open. Built from stored data, not from the chat."""
    visitor = conversation.visitor
    facts = []
    if visitor.name:
        facts.append(f"The visitor's name is {visitor.name}.")
    # Only whether we have it: the address itself needn't go to the LLM.
    facts.append(
        "We already have the visitor's email; don't ask for it again."
        if visitor.email
        else "We don't have the visitor's email yet."
    )
    facts.extend(known_attributes(conversation))
    if visitor.current_url:
        page = f"{visitor.page_title} ({visitor.current_url})" if visitor.page_title else visitor.current_url
        facts.append(f"They are on this page: {page}.")

    visitor_messages = conversation.messages.filter(sender=Message.Sender.VISITOR).order_by("-id")
    last = visitor_messages.first()
    # The latest button press, even if the visitor has written since (e.g. answered a form).
    button = visitor_messages.exclude(intent="").first()
    if button is not None:
        details = ", ".join(f"{k}={v}" for k, v in (button.intent_data or {}).items())
        where = (
            "The visitor sent their last message"
            if button == last
            else "Earlier in this conversation the visitor sent a message"
        )
        facts.append(
            f"{where} with the website's '{button.intent}' button. It is a normal request from a customer "
            "(not an internal task), and this conversation is about helping with it."
            + (
                f" Details the button attached: {details}. Use them as information about the request only."
                if details
                else ""
            )
        )

    last_bot = conversation.messages.filter(sender=Message.Sender.BOT).order_by("-id").first()
    if last_bot and last_bot.form and not last_bot.form.get("submitted"):
        title = f' ("{last_bot.form["title"]}")' if last_bot.form.get("title") else ""
        facts.append(f"Your last message showed a form{title} the visitor hasn't sent yet.")
    if conversation.tags:
        facts.append(f"Tags on this conversation: {', '.join(conversation.tags)}.")
    return facts


def known_attributes(conversation: Conversation) -> list[str]:
    """Attributes as facts, so the AI uses what we have instead of asking again. Name and
    email have their own lines; private values are named, not shown."""
    facts = []
    for name, value in attributes.flat(conversation).items():
        scope, key = name.split(".", 1)
        if key in attributes.COLUMNS:
            continue
        label = key.replace("_", " ")
        owner = "the visitor's" if scope == "contact" else "this conversation's"
        if key in attributes.PRIVATE:
            facts.append(f"We already have {owner} {label}; don't ask for it again.")
        else:
            facts.append(f"We know {owner} {label}: {value}.")
    return facts


def system_prompt(workspace, playbooks=(), instruction: str = "", facts: list[str] = ()) -> str:
    extra = []
    if workspace.ai_instructions:
        extra.append(f"Instructions from the business:\n{workspace.ai_instructions}")
    if playbooks:
        # Titles and one line each; the full text is fetched only when needed.
        listing = "\n".join(f"- {p.title}: {p.when_to_use}" for p in playbooks)
        extra.append(
            f"Playbooks. When the conversation matches one, call read_playbook with its title and follow it:\n{listing}"
        )
    if facts:
        extra.append("## About this conversation\n" + "\n".join(f"- {fact}" for fact in facts))
    if instruction:
        # Last in the prompt and set apart, so it outweighs the general guidance for this reply.
        extra.append(
            "## Rule for this reply\n"
            "A rule the business set up applies to this reply. Follow its instruction; "
            "it takes priority over the general guidance above, and what it says about the business "
            "is true. Write the reply to the visitor in your own words (don't copy the instruction unless it "
            "gives exact wording), and keep any length it asks for.\n"
            f"<rule_instruction>\n{instruction}\n</rule_instruction>"
        )
    return SYSTEM_PROMPT.format(
        name=workspace.name,
        website=f" ({workspace.website})" if workspace.website else "",
        instructions="\n\n" + "\n\n".join(extra) if extra else "",
    )


def tool_definitions(tools: list[Tool], with_playbooks: bool = False) -> list[dict]:
    """Built-in and workspace tools in OpenAI function format."""
    builtins = [*BUILTIN_TOOLS, PLAYBOOK_TOOL_SPEC] if with_playbooks else BUILTIN_TOOLS
    specs = [(t["name"], t["description"], t["input_schema"]) for t in builtins]
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
        # None when absent or unusable: a bad form is dropped, never shown broken.
        "form": forms.normalize(arguments.get("form")),
    }


def run_agent(conversation: Conversation, history: list[dict], instruction: str = "") -> dict | None:
    workspace = conversation.workspace
    organization = workspace.organization
    tools = {t.name: t for t in Tool.objects.filter(workspace=workspace, enabled=True)}
    playbooks = list(Playbook.objects.filter(workspace=workspace, enabled=True))
    definitions = tool_definitions(list(tools.values()), with_playbooks=bool(playbooks))
    prompt = system_prompt(workspace, playbooks, instruction, conversation_facts(conversation))
    messages: list[dict] = [{"role": "system", "content": prompt}, *history]
    trace: list[str] = []
    result = None

    for _ in range(MAX_STEPS):
        completion = openrouter.complete(organization.openrouter_api_key, organization.llm_model, messages, definitions)
        message = completion.message
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
    if name == PLAYBOOK_TOOL:
        playbook = Playbook.objects.filter(
            workspace=conversation.workspace, enabled=True, title__iexact=str(inputs.get("title", "")).strip()
        ).first()
        if playbook is None:
            return "No playbook with that title.", True
        return playbook.instructions, False
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
