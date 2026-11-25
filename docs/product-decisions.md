# Product decisions

Product decisions made by the project owner, newest first. Each says what was decided and, when
given, why. A reversed decision stays here, marked as replaced, with a link to the new one.
Technical decisions are in [tech-decisions.md](tech-decisions.md).

## 2026-11-25: The footer has groups of links

**Decision.** The footer is columns of links under headings, not one row.

**Why.** Lots of options will be added to it later.

## 2026-11-24: Workspaces and organizations set their own AI limits

**Decision.** The daily limits of AI replies, per visitor and for all visitors together, are settings of the workspace
in the dashboard, so people can decide for themselves. An organization can also limit all its workspaces together.

## 2026-11-24: The docs are easy to give to an LLM

**Decision.** Each page of the docs has a "Copy page" button, and the site has `llms.txt` and the basics of SEO.

**Why.** People can just copy a page and give it to their LLM.

## 2026-11-24: Docs with videos, edited in place by a superuser

**Decision.** The product has basic docs of how the platform works, with code snippets. A superuser can put a YouTube
video on a page by pasting its link, and edit a page's text in a simple what-you-see-is-what-you-get editor. The text
is written first; the owner makes and uploads the videos later.

## 2026-11-24: A visitor's country comes from the website

**Decision.** The country is the `country` attribute the website sends with identify(); unsigned is fine. The inbox shows
a small flag, as Crisp does, and the panel on the right shows the flag and the country's name.

**Why.** It isn't a big feature, and a paid lookup would add to expenses. The right panel has more space.

## 2026-11-24: Slack and webhooks are the first integrations

**Decision.** Slack comes first, then webhooks: like Slack, but general, for any system. No Telegram. Later ones are
chosen by what is used most at Fin, Intercom and Crisp.

## 2026-11-24: Billing is in the main sidebar

**Decision.** Billing gets its own entry in the main sidebar, above Settings.

## 2026-11-24: Integrations are in the main sidebar

**Decision.** Integrations get their own entry in the main sidebar, not one under Settings.

**Why.** They belong to one workspace, like everything else in that sidebar.

## 2026-11-24: Answers from real data work with any system

**Decision.** Integrations don't supply customer data, so there is no Shopify or Stripe plugin for it. Questions such as
"where is my order?" and "why was I charged?" are answered by the agent's tools, rules, playbooks and later features,
with A2UI, from any system.

**Why.** That is the whole point of the chatbot and A2UI.

## 2026-11-24: The widget has a background and a color mode

**Decision.** Owners pick the chatbox background, as in Crisp, and one more important option. Color mode (light, dark
or the visitor's own) was chosen for it. The pattern is only on the header, not behind the messages, and is a drawn
design rather than plain dots or a grid.

## 2026-11-24: The widget is clean, with minimal text

**Decision.** The header shows the workspace's logo and the team's photos, overlapping and centered, without the
workspace's name or a line of text. The bot icon alone marks the AI's messages: no "AI" label beside the name.

**Why.** People already understand what the bot icon means.

## 2026-11-24: A small editor in the inbox, files in the widget

**Decision.** Teammates write replies in a minimal what-you-see-is-what-you-get box that takes less height, without
hints such as "Enter to send". Visitors get file upload, and no formatting.

**Why.** People know how Enter works.

## 2026-11-24: Short, opinionated lists of models

**Decision.** The OpenRouter dropdown offers at most 20 models, low and mid tier, with one high-tier model each from
OpenAI, Anthropic and Gemini. The lists of OpenAI, Anthropic and Gemini themselves are shortened the same way.

**Why.** The full list is very long.

## 2026-11-24: The AI pauses after a 14-day trial

**Decision.** On the hosted version the AI pauses after 14 days if the customer doesn't pay. Customers bring their
own AI API keys.

## 2026-11-24: Several AI providers, and one fallback model

**Decision.** Customers can use OpenAI, Anthropic, OpenRouter and one more provider (Google Gemini was chosen), not
only OpenRouter. They can also pick a fallback model, from any provider. There is never more than one fallback.

**Why.** When the chosen model is down, say OpenAI's, another one such as Anthropic's Haiku should answer.

## 2026-11-24: Images in articles are only ever in the customer's own bucket

**Decision.** A help article's images go to the bucket the customer connected, never to ours. Until they connect one,
articles are text, which is enough to get started.

**Why.** Files in our bucket are public. If something important in a customer's article were public in our storage, they
would hold us responsible for it.

## 2026-11-24: Customers bring their own integrations, and the sidebar guides them

**Decision.** Services that cost money with use (the AI, file storage such as S3 or R2) are integrations the customer
connects. None is mandatory: the product works without storage. A "Get started" guide shows the next step until
they are done: one slim row with a progress bar in the sidebar, which opens a panel, not a card.

**Why.** The price is too low to carry a large customer's usage, such as 100,000 photos a month in our storage.

## 2026-11-24: Help articles are written in a small visual editor

**Decision.** A minimal what-you-see-is-what-you-get editor, from a popular toolkit, with only 5 or 6 controls.
It is Tiptap, with bold, heading, bullet list, numbered list, link and image.

## 2026-11-24: The README has one GIF and two images

**Decision.** At most one GIF (or interactive demo) and two images, with the inbox captured on a large screen.

**Why.** On a small screen the chat looked narrow.

## 2026-11-24: One Settings entry with groups inside it

**Decision.** The sidebar holds the daily work (inbox, visitors, knowledge base, AI agent), and everything set up
once sits behind one Settings entry, in groups with sub-settings the way Crisp does it. Related settings are merged.

**Why.** The sidebar was not arranged well: organization and LLM settings sat beside the daily pages.

## 2026-11-24: The README is for visitors, not a code reference

**Decision.** The README shows what whileisleep does and how the UI looks, and lets the reader explore.
It has no references to code, and at most 10 important commands (ideally 5).

**Why.** Nobody reads code today, so code references in the README don't help the people who land on
the GitHub page.
