---
title: Widget in code
description: Say who your users are, and open the chat from your own buttons.
---

The script sets `window.whileisleep`. It loads in the background, so wait for it once:

```js
function whenChatReady(run) {
  if (window.whileisleep) run();
  else window.addEventListener("whileisleep:ready", run, { once: true });
}
```

## Say who the user is

```js
whenChatReady(() => {
  window.whileisleep.identify({
    name: "Maya Rao",
    email: "maya@example.com",
    attributes: { plan: "pro", country: "IN" },
  });
});
```

Your team sees these details next to the chat, and [rules](rules.md) can use them. A country shows as a flag.

> [!WARNING]
> Anyone can type this into a browser console, so it isn't proof. To let the agent look up a user's own data, use [Verified identity](verified-identity.md).

## Open it from your own button

```html
<button onclick="window.whileisleep?.open('I have a question about the Pro plan')">
  Ask us
</button>
```

You can add an intent and data that rules can match:

```js
window.whileisleep.open("Where is my order?", { intent: "order_status", data: { order: "1042" } });
```

## Everything it can do

| Call | What it does |
|---|---|
| `open(message, { intent, data })` | Opens the chat, with the message typed in. All of it is optional. |
| `close()` | Closes it |
| `hide()` and `show()` | Removes the button from a page, and brings it back |
| `identify({ name, email, attributes })` | Says who the user is |
| `identify({ token })` | Proves who the user is |
| `restart()` | Clears the chat and starts a new conversation |
| `reset()` | Forgets the visitor. Call it when your user signs out. |
