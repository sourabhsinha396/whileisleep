---
title: How it works
description: What happens between a visitor's question and the answer.
seo_title: How the AI support agent works
seo_description: How whileisleep answers a visitor, with rules first, then an AI agent that reads your articles and calls your APIs, and a person when one is needed.
---

whileisleep is a chat for your website. An AI agent answers from what you give it, and passes a chat to your team when a person is needed.

## Who does what

- **Visitors** write in the chat widget on your site.
- **The AI agent** answers from your articles, your instructions and your own systems.
- **Your team** reads every chat in the inbox, and can take one over at any time.

## What happens to a message

The cheapest way to answer goes first. Each step only runs if the one before it didn't settle the message.

1. **Rules.** If one matches and has an exact reply, that reply is sent. The AI isn't used, so it costs nothing.
2. **Is it the AI's turn?** If the AI is off, or a person has the chat, it waits for your team.
3. **Daily limits.** Past the limit of AI replies for the day, the chat goes to your team. You [set the limits](connect-ai.md#limit-what-it-costs).
4. **The AI answers.** It reads the best passages of your articles, looks things up with your tools, and follows a playbook when one fits.
5. **A person.** When the AI can't answer, or the visitor asks for a person, the chat is marked **Needs a person**.

> [!TIP]
> Nothing is required to begin. Without an AI model, the agent searches your articles and shows the best matches.

## What to give the agent

| You have | Use |
|---|---|
| Facts that rarely change, like shipping times | [Knowledge base](knowledge-base.md) |
| A reply that must be word for word | [Rules](rules.md) |
| Steps to follow in a tricky case, like refunds | [Playbooks](playbooks.md) |
| Live data, like orders or stock | [Tools](tools.md) |
| Tone, and what to stay away from | **AI agent › Behavior** |

## Workspaces and organizations

A **workspace** is one website, with its own inbox, team, articles, tools and widget. An **organization** owns workspaces, and holds what they share: the AI model, the storage and the plan.
