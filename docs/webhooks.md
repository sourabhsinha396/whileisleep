# Webhooks

Tell any system what happens in your chats, and let it answer them. Works with your own server, Zapier, Make and n8n.

Connect one in **Settings › Integrations › Webhooks**: enter an `https://` address, choose what to send, and save. Saving
sends a `test` event; if your endpoint doesn't answer with a 2xx status, nothing is saved. A workspace can have five
endpoints, each with its own events and secret.

## What you get

```json
{
  "id": "msg_4821",
  "type": "conversation.needs_person",
  "created_at": "2026-11-24T02:14:09.120000+00:00",
  "workspace": { "id": 1, "name": "Acme Shop", "slug": "acme-shop" },
  "data": {
    "conversation": {
      "id": 311,
      "url": "https://chat.example.com/w/acme-shop/inbox?c=311",
      "status": "open",
      "needs_person": true,
      "assignee": null,
      "tags": ["refund"],
      "attributes": { "order_number": "1042" },
      "created_at": "2026-11-24T02:12:40.004000+00:00"
    },
    "contact": {
      "id": 77,
      "external_id": "u_7",
      "name": "Maya",
      "email": "maya@example.com",
      "email_verified": true,
      "attributes": { "name": "Maya", "email": "maya@example.com", "plan": "pro" },
      "page": { "url": "https://acme.com/orders/1042", "title": "Your order" }
    },
    "reason": "Wants a refund"
  }
}
```

| `type` | Sent when | Also in `data` |
|---|---|---|
| `conversation.started` | A chat starts | `by`, if a teammate wrote first |
| `conversation.needs_person` | The AI, a rule or the visitor asks for a person | `reason` |
| `contact.updated` | A visitor leaves their name, email or phone in a form | `changed` |
| `conversation.resolved`, `conversation.reopened` | It is resolved or reopened | `by`, if a teammate did it |
| `conversation.returned_to_ai` | A teammate gives it back to the AI | `by` |
| `message.created` | Anyone writes: `message.from` is `visitor`, `ai` or `teammate` | `message`, `by` |
| `note.created` | A teammate writes an internal note | `message`, `by` |
| `test` | You save the settings | |

`email_verified` is true only if your server vouched for the email (Settings › Verified identity). Anything else was typed,
so don't act on it as proof. New fields may be added; none will change or disappear.

## Answer quickly, and expect repeats

- Answer with a 2xx status within 5 seconds, and do slow work afterwards.
- Anything else is tried again after 10 seconds, then 1, 5, 30 and 120 minutes. `410` and redirects are not.
- The same event may arrive twice. Its `webhook-id` (and `id`) stays the same: skip one you have seen.
- Events of one chat arrive in order. Events of different chats may not.
- **Sent lately** on the settings page shows the last week, with each answer, and can send one again.

## Check that it came from us

Requests are signed as [Standard Webhooks](https://www.standardwebhooks.com) describes, so its libraries work. Your
endpoint's secret is on the settings page.

```python
from standardwebhooks import Webhook

event = Webhook("whsec_...").verify(request.body, request.headers)  # raises if it isn't genuine
```

```js
import { Webhook } from "standardwebhooks";

const event = new Webhook("whsec_...").verify(rawBody, req.headers); // throws if it isn't genuine
```

## Answer a chat

Send a JSON object to the **Answer at** address, signed with the same secret. Add one header, `webhook-endpoint`, with
your **Endpoint id**.

```python
import datetime, json, uuid, requests
from standardwebhooks import Webhook

body = json.dumps({"action": "reply", "conversation_id": 311, "text": "Hi Maya, it's refunded."})
id, now = f"msg_{uuid.uuid4()}", datetime.datetime.now(datetime.timezone.utc)
requests.post(
    "https://chat.example.com/api/v1/integrations/webhooks/webhook",
    data=body.encode(),
    headers={
        "content-type": "application/json",
        "webhook-endpoint": "YOUR_ENDPOINT_ID",
        "webhook-id": id,
        "webhook-timestamp": str(int(now.timestamp())),
        "webhook-signature": Webhook("whsec_...").sign(id, now, body),
    },
)
```

| `action` | Does | Needs |
|---|---|---|
| `reply` | Writes to the visitor. The AI then leaves the chat to people. | `text`, up to 10,000 characters |
| `note` | Writes an internal note | `text` |
| `resolve`, `reopen` | Resolves or reopens the chat | |
| `give_to_ai` | Gives the chat back to the AI | |

It is done as the person who connected the endpoint, or as the teammate in `author_email`. The answer is `{"ok": true}` once
the request is accepted. Repeating one with the same `webhook-id` does nothing. Your endpoint isn't told about what it did
itself; your other endpoints are.
