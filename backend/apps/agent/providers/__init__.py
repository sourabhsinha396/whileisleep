"""The LLM providers an organization can choose from, each behind the same few functions:

complete(api_key, model, messages, tools, timeout)  one model call (see base for the messages)
check_key(api_key)                                  raises ProviderError if it doesn't work
list_models(api_key)                                what the key can use, for the model picker
"""

from . import anthropic, google, openai, openrouter
from .base import TIMEOUT_SECONDS, Completion, ProviderError, parse_arguments

# The keys match apps.workspaces.models.Provider.
PROVIDERS = {"openai": openai, "anthropic": anthropic, "google": google, "openrouter": openrouter}

__all__ = ["PROVIDERS", "TIMEOUT_SECONDS", "Completion", "ProviderError", "complete", "parse_arguments"]


def complete(
    provider: str,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    timeout: float = TIMEOUT_SECONDS,
) -> Completion:
    """One model call. A `native` answer among the messages is passed on only to the provider
    and model that wrote it."""
    author = [provider, model]
    readable = []
    for message in messages:
        native = message.get("native")
        message = {key: value for key, value in message.items() if key != "native"}
        if native and native["by"] == author:
            message["native"] = native["data"]
        readable.append(message)
    completion = PROVIDERS[provider].complete(api_key, model, readable, tools, timeout)
    if completion.native is not None:
        completion.native = {"by": author, "data": completion.native}
    return completion
