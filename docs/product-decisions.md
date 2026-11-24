# Product decisions

Product decisions made by the project owner, newest first. Each says what was decided and, when
given, why. A reversed decision stays here, marked as replaced, with a link to the new one.
Technical decisions are in [tech-decisions.md](tech-decisions.md).

## 2026-11-24: The AI pauses after a 14-day trial

**Decision.** On the hosted version the AI pauses after 14 days if the customer doesn't pay. Customers bring their
own AI API keys.

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
