---
title: Playbooks
description: Teach the agent how to handle tricky conversations.
seo_title: AI agent playbooks
seo_description: Teach the AI agent how to handle refunds, cancellations and other tricky chats with step-by-step playbooks in plain words, with an example.
---

A playbook is a procedure in plain words. The AI sees each playbook's title and **When to use** line, and reads the rest only when a conversation matches. So you can have many.

## Write one

1. Open **AI agent › Playbooks** and press **Add playbook**.
2. **Title**: what it is about.
3. **When to use**: one line. This is all the AI goes by when it chooses, so be exact.
4. **Instructions**: the steps, as you would explain them to a new colleague.

## Example

```text
Title: Refund requests

When to use: The visitor asks for a refund or wants to cancel an order they paid for.

Instructions:
1. Ask for the order number if you don't have it.
2. Look the order up with the get_order tool.
3. If it was delivered less than 30 days ago, say that a teammate will
   process the refund, and hand off.
4. If it is older, explain the 30-day policy kindly. If they insist, hand off.
Never promise an amount or a date.
```

## What works well

- Say what to do when something is missing: no order number, no match, an angry customer.
- Name the [tools](tools.md) to use, by their exact names.
- Say when to stop and hand off to a person.
