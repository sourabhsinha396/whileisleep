"""The organization's model, and its fallback when that one can't answer.

One reply is one Chain. It asks the main model until a call fails, for whatever reason: the
provider is down, the key was revoked, the balance is empty, the model was retired. The
visitor doesn't care which, so the fallback takes over at once, from the same point in the
conversation, and finishes the reply. The next reply starts with the main model again.
"""

import logging

from apps.workspaces.models import LlmChoice

from . import providers

log = logging.getLogger(__name__)


class Chain:
    def __init__(self, choices: list[LlmChoice]):
        self.choices = list(choices)
        # Models share one call's time, so a fallback never makes the visitor wait longer
        # than a single model may (the reply's deadline and lock are set by that).
        self.timeout = providers.TIMEOUT_SECONDS / max(len(choices), 1)
        self.failures: list[tuple[LlmChoice, providers.ProviderError]] = []

    @property
    def current(self) -> LlmChoice:
        return self.choices[len(self.failures)]

    def complete(self, messages: list[dict], tools: list[dict]) -> providers.Completion:
        """One model call. Raises ProviderError once no model is left to ask."""
        while True:
            choice = self.current
            try:
                return providers.complete(choice.provider, choice.api_key, choice.model, messages, tools, self.timeout)
            except providers.ProviderError as error:
                self.failures.append((choice, error))
                if len(self.failures) < len(self.choices):
                    log.warning("%s failed, trying %s: %s", choice.label, self.current.label, error)
                    continue
                raise self.failure() from error

    def failure(self) -> providers.ProviderError:
        """Everything that went wrong, as one error."""
        errors = [error for _, error in self.failures]
        if len(errors) == 1:
            return errors[0]
        return providers.ProviderError(
            f"{errors[0]} The fallback failed too: {errors[1]}",
            # If either may be back in a few seconds, another try is worth it.
            transient=any(error.transient for error in errors),
        )
