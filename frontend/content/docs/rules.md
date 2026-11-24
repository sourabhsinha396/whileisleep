---
title: Rules
description: Exact replies, tags and hand-offs that run before the AI.
---

A rule says **when** it applies and **what** to do. Rules are checked on every visitor message, in order, before the AI. The first match wins.

## Make a rule

1. Open **AI agent › Rules** and press **Add rule**.
2. Under **When**, add conditions.
3. Under **Then**, choose what happens.
4. Check how many recent messages it would have matched, then save.

## When

Conditions can look at:

- the message: its text, and whether it is the first one
- the page the visitor is on: its address and title
- what you know about the visitor, like their plan, and whether they are verified
- the conversation: its tags and attributes, and whether a person has it
- the time: the hour and weekday in your workspace's timezone

## Then

| Action | What happens |
|---|---|
| **Reply** | Sends your exact text. The AI stays quiet. |
| **Instruction for the AI** | The AI answers, with one extra instruction for this message |
| **Tag** | Labels the chat, so you can search for it |
| **Hand off** | Marks the chat as needing a person |
| **Remember** | Saves an attribute that later rules and tools can use |

Replies can include what you know: `We're back at 9:00, {contact.name}.`

## Examples

| Goal | When | Then |
|---|---|---|
| Set expectations at night | Hour is at least 18 | Instruction: say that the team replies in the morning |
| Send legal questions to a person | Message has any of the words: lawyer, lawsuit, court | Hand off, tag `legal` |
| Look after paying customers | Visitor attribute `plan` is `pro` | Tag `pro` |
| A fixed answer about prices | Message contains any of: discount, coupon | Reply with your exact policy |

> [!TIP]
> Use a rule when the answer must never vary. For everything that needs judgement, use a [playbook](playbooks.md).
