"""Collects what one pass of the reply pipeline did, then saves it as a Turn."""

import time
from decimal import Decimal

from apps.conversations.models import Conversation, Message
from apps.realtime import events

from .models import Rule, Turn
from .openrouter import Completion

# Tool results can be long; the Turn keeps enough to see what came back.
RESULT_CHARS = 500

# What the widget and the inbox show while a step runs. The workspace's own tools get a
# generic line: their names are internal ("get_order_v2") and not for visitors.
STATUS = {
    "retrieval": "Searching the help center",
    "model": "Writing a reply",
    "search_knowledge_base": "Searching the help center",
    "read_playbook": "Checking our guidelines",
    "handoff_to_human": "Getting a teammate",
}
TOOL_STATUS = "Looking that up"


def status_text(kind: str, name: str = "") -> str:
    if kind == "tool":
        return STATUS.get(name, TOOL_STATUS)
    return STATUS.get(kind, "")


class Recorder:
    """Start one when a visitor message arrives, tell it what happens, and `finish` it.

    Nothing is written until `finish`, so a pipeline that crashes half-way leaves no
    half-true record.
    """

    def __init__(self, conversation: Conversation, trigger: Message | None = None):
        self.conversation = conversation
        self.trigger = trigger
        self.started = time.monotonic()
        self.steps: list[dict] = []
        self.model = ""
        self.llm_calls = 0
        self.input_tokens = 0
        self.cached_tokens = 0
        self.output_tokens = 0
        self.cost: Decimal | None = None
        self.status = ""

    def completion(self, completion: Completion, model: str) -> None:
        """Counts one model call."""
        self.model = model
        self.llm_calls += 1
        self.input_tokens += completion.input_tokens
        self.cached_tokens += completion.cached_tokens
        self.output_tokens += completion.output_tokens
        if completion.cost is not None:
            self.cost = (self.cost or Decimal(0)) + completion.cost

    def doing(self, kind: str, name: str = "") -> None:
        """Announces the step about to run (a step kind, or "model" for a model call) to the
        widget and the inbox. Repeats of the same text aren't sent again."""
        text = status_text(kind, name)
        if text and text != self.status:
            self.status = text
            events.bot_status(self.conversation, text)

    def step(self, kind: str, **details) -> None:
        self.steps.append({"type": kind, **details})

    def tool(self, name: str, arguments: dict, result: str, is_error: bool, started: float) -> None:
        self.step(
            "tool",
            name=name,
            arguments=arguments,
            result=result[:RESULT_CHARS],
            is_error=is_error,
            ms=int((time.monotonic() - started) * 1000),
        )

    def finish(self, stage: str, reply: Message | None = None, rule: Rule | None = None, error: str = "") -> Turn:
        if self.status:
            # Done: the reply (if any) has been published by now, so the status can clear.
            self.status = ""
            events.bot_status(self.conversation, "")
        return Turn.objects.create(
            workspace_id=self.conversation.workspace_id,
            conversation=self.conversation,
            trigger=self.trigger,
            reply=reply,
            stage=stage,
            rule=rule,
            model=self.model,
            llm_calls=self.llm_calls,
            input_tokens=self.input_tokens,
            cached_tokens=self.cached_tokens,
            output_tokens=self.output_tokens,
            cost=self.cost,
            duration_ms=int((time.monotonic() - self.started) * 1000),
            steps=self.steps,
            error=error,
        )
