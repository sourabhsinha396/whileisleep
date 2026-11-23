"""Collects what one pass of the reply pipeline did, then saves it as a Turn."""

import time
from decimal import Decimal

from apps.conversations.models import Conversation, Message

from .models import Rule, Turn
from .openrouter import Completion

# Tool results can be long; the Turn keeps enough to see what came back.
RESULT_CHARS = 500


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

    def completion(self, completion: Completion, model: str) -> None:
        """Counts one model call."""
        self.model = model
        self.llm_calls += 1
        self.input_tokens += completion.input_tokens
        self.cached_tokens += completion.cached_tokens
        self.output_tokens += completion.output_tokens
        if completion.cost is not None:
            self.cost = (self.cost or Decimal(0)) + completion.cost

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
