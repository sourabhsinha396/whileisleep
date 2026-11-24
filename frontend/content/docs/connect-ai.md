---
title: Connect your AI
description: Add your provider's key, pick a model, and choose a fallback.
seo_title: Connect OpenAI, Claude or Gemini
seo_description: Use your own OpenAI, Anthropic, Google Gemini or OpenRouter key for customer chat, pick a model, and set a fallback for when it is down.
---

You bring your own AI account. Your provider bills you directly, at its own price. You need to be the organization's owner.

## Add a key

1. Open **Settings › AI model**.
2. Under **API keys**, paste a key from OpenAI, Anthropic, Google Gemini or OpenRouter.
3. Under **Model**, pick the provider and a model, and save. The model must support tool calling.

Keys are encrypted on the server and never shown again. Every workspace of the organization uses them.

## Pick a fallback

The fallback is a second model that takes over a reply when the first one fails. Choose one from **another provider**, so an outage doesn't stop both.

- It continues the same reply. Tools that already ran don't run again.
- Your team gets an internal note that it happened.
- The next message starts with the main model again.

If both fail, they are tried again after a few seconds. After that the visitor gets the best matches from your articles.

## Tell it how to behave

Open **AI agent › Behavior**, turn the agent on, and write its instructions: tone, what it may talk about, and facts too small for an article. For example:

```text
Be friendly and brief. Reply in the visitor's language.
We only sell to businesses. If a private person asks, say so kindly.
Never promise a delivery date. Offer a person instead.
```

> [!TIP]
> Keep facts in articles and steps in playbooks. Short instructions are followed better than long ones.
