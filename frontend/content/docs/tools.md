---
title: Tools and MCP
description: Let the agent look up orders, stock and anything else in your own systems.
seo_title: Connect APIs and MCP to AI chat
seo_description: Let the AI agent look up orders, stock and account data with your own HTTP APIs or MCP servers, without showing one customer another's data.
---

A tool is an address on your own server that the agent can call. It decides when from the tool's description, so it looks facts up instead of guessing.

## Add a tool

1. Open **AI agent › Tools** and press **Add tool**.
2. Fill in the form, for example like the one below.
3. Press **Save & test** with some inputs, and look at the answer.

| Field | Example |
|---|---|
| Name | `search_products` |
| Description | Searches our catalog by name. Returns name, price, stock and link. Use it whenever someone asks whether we have something. |
| Method and URL | `GET https://api.example.com/products` |
| Input | `q`, string, required: what the visitor is looking for |
| Header | `Authorization`: `Bearer YOUR_API_KEY` |

The inputs are sent as query parameters for `GET`, and as a JSON body for `POST`. An input in braces goes into the address itself: `/products/{sku}`. Headers are encrypted, and neither visitors nor the AI see them.

## Answer with little

Return only what helps to answer, as JSON. Short answers are cheaper and read better:

```json
{
  "products": [
    { "name": "Trail Shoe 2", "price": "89.00 EUR", "in_stock": true, "url": "https://example.com/p/trail-2" }
  ]
}
```

## Cards

When a tool answers with JSON, the agent can show a card under its reply: details such as an order's status, a short list, or the steps of a delivery. There is nothing to set up. The values come straight from your tool's answer, so write them the way a visitor should read them: `"89.00 EUR"` rather than `8900`. A price or total that is only a whole number is left out of the card, as it could be in cents. Answers longer than 8,000 characters get no card.

## A visitor's own data

To look up someone's orders, the tool must know who is asking. Put it in the URL, where the AI can't change it:

```text
https://api.example.com/orders?customer={visitor.external_id}
```

`{visitor.external_id}` and `{visitor.email}` are only filled in for a visitor your server has vouched for. Set that up first: [Verified identity](verified-identity.md). For anyone else the agent says it can't look that up in this chat.

> [!WARNING]
> Never make a tool that returns someone's data for an email or order number the AI filled in. A visitor can type anyone's.

## MCP servers

If your system has an MCP server, connect it at the bottom of **AI agent › Tools**: a name, its address, and an access token if it needs one. Its tools are imported **switched off**. Turn on those the agent may use.

- A tool marked **Can change data** may do more than look things up.
- If the server changes a tool's description, the tool pauses until you approve it again.
- MCP servers aren't told who the visitor is. Use your own tools for personal data.
