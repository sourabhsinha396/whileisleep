---
title: Slack
description: Chats that need a person become threads in your channel. Replies there reach the visitor.
---

## Connect it

1. Open **Integrations › Slack** and press **Connect Slack**. Slack asks which workspace to use.
2. Pick a channel, and press **Save and send a test**. For a private channel, invite whileisleep to it in Slack first.

Each whileisleep workspace has its own connection, so two sites can post to two channels of the same Slack.

| In Slack | What happens |
|---|---|
| Reply in the thread | The visitor gets it, under your name and photo. A tick on your message says it went. |
| Reply that starts with `note:` | Saved as an internal note. The visitor never sees it. |
| **Resolve**, **Reopen**, **Back to AI** | Changes the chat, and the first message shows it |
| **Open in inbox** | Opens the chat in the dashboard |

Visitors' messages, the AI's and your teammates' from the inbox appear in the same thread.

Good to know:

- **Everyone in the channel can read these chats.** Only members of the whileisleep workspace can answer: the email in Slack must be the one they sign in to whileisleep with. Others get a private message saying nothing was sent. People from another company's Slack, in a shared channel, can't answer.
- Files can't be sent from Slack yet; attach them in the inbox. Visitors' files show in Slack as links.
- Editing or deleting a message in Slack doesn't change what the visitor got.
- With **Chats that need a person**, a thread starts when the AI, a rule or the visitor asks for one, or when the AI is off.
- In a Slack Enterprise organization, install it in one workspace, not in the whole organization.

## Set it up on your own server

You need a Slack app of your own, once per server. The server needs a public `https://` address.

1. Open [api.slack.com/apps](https://api.slack.com/apps), press **Create New App**, then **From a manifest**.
2. Paste [`manifest.json`](../../../backend/plugins/slack/manifest.json) with `YOUR_DOMAIN` replaced by your server's domain, in all three places. The server must be running for Slack to accept the addresses: if it doesn't, do step 3 and press **Retry** under **Event Subscriptions**.
3. From **Basic Information**, copy three values into the server's `.env` as `PLUGIN_SLACK_CLIENT_ID`, `PLUGIN_SLACK_CLIENT_SECRET` and `PLUGIN_SLACK_SIGNING_SECRET`, and restart it.
4. To connect a Slack other than the one the app was made in, turn on **Manage Distribution › Public Distribution**.

On your own machine Slack can't reach `localhost`: run a tunnel with an `https://` address, use it in the manifest, and set `SITE_URL` to it.
