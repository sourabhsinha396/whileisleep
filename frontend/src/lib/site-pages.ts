import type { Operator } from "./operator";

/** About, contact and the legal pages. What they say must match what the product does. */

export interface SitePage {
  label: string;
  title: string;
  description: string;
  /** The line under the title. */
  intro: string;
  /** Legal pages show when they last changed. */
  updated?: string;
  /** Says who runs the site, so it only exists when that is known. */
  needsOperator: boolean;
  /** Markdown. */
  body: (by: Operator | null) => string;
}

const POLICIES_UPDATED = "November 25, 2026";

const mail = (by: Operator | null) => (by ? `[${by.email}](mailto:${by.email})` : "");

const details = (by: Operator | null) =>
  by ? [`**${by.name}**`, by.address, mail(by)].filter(Boolean).join("\\\n") : "";

export const SITE_PAGES: Record<string, SitePage> = {
  about: {
    label: "About",
    title: "About us",
    description: "whileisleep is open-source customer chat: an AI agent answers from your own data, and a person takes over when one is needed.",
    intro: "Customer chat for people who can't be online all day, and shouldn't have to be.",
    needsOperator: false,
    body: (by) => `
## Why it exists

Customers ask at any hour. Most questions have an answer already: in a help article, in an order system, in someone's head. whileisleep gives that answer right away, and wakes you only for the chats that need a person.

## What we care about

- **Answers from real data.** The agent reads your articles and calls your APIs and MCP servers, so it looks things up instead of guessing.
- **A person is always possible.** Visitors can ask for one, and the AI stays quiet while your team has the chat.
- **Your own AI key.** You pay OpenAI, Anthropic, Google or OpenRouter directly, at their price. We add nothing on top.
- **Open source.** Run it on your own server for free, with every feature, or let us host it.
${by ? `\n## Who runs this site\n\n${by.name}. Say hello on the [contact page](/contact).\n` : ""}`,
  },
  contact: {
    label: "Contact",
    title: "Contact us",
    description: "Write to us about your whileisleep account, a bill, a security problem or your data. Here is the address, and what to put in it.",
    intro: "One address for everything, read by a person.",
    needsOperator: true,
    body: (by) => `
## Write to us

${mail(by)}

| About | Please include |
|---|---|
| Your account or a bill | The email you log in with, and the receipt if it is about a payment |
| Something that doesn't work | The page, what you expected, and what happened |
| A security problem | How to reproduce it. Please tell us before anyone else |
| Your data | What you want to see, correct or delete |

Never send a password, an API key or a card number.

Were you chatting on another company's website? We can't see your order or your account there. Please ask that company.

The [docs](/docs) may already have the answer.

## Details

${details(by)}
`,
  },
  privacy: {
    label: "Privacy",
    title: "Privacy policy",
    description: "What data the hosted whileisleep keeps about customers and the visitors they chat with, where it goes, and how to have it deleted.",
    intro: "What we keep, why, and who else sees it.",
    updated: POLICIES_UPDATED,
    needsOperator: true,
    body: (by) => `
This is about the whileisleep hosted at this address by ${by?.name}. If you run whileisleep on your own server, your data is there and not with us.

## If you have an account

We keep:

- your name, email address and photo, and your password only as a hash;
- your workspaces: articles, rules, playbooks, tools, settings and team;
- API keys and other secrets you connect, encrypted;
- your plan and its payment status. Card details go to Dodo Payments and never reach us.

We use this to run the service, answer you, take payment and stop abuse.

## If you chat on a website that uses whileisleep

That website's owner decides what is collected and why. We keep it for them, and they and their team see it:

- your messages and files;
- the page you are on, the page you came from, your browser and your IP address;
- what the website tells us about you, such as your name, email, country or plan.

To see or delete any of it, ask that website. We help its owner do so.

## Who else gets data

- **AI providers.** To write a reply, the conversation, what is known about the visitor and matching articles go to the AI provider the website's owner connected, under the owner's own account.
- **What the owner connects**, such as Slack, webhooks, their own APIs and their own file storage.
- **Dodo Payments**, which sells our plans and handles cards, tax and invoices.
- **Our hosting and network providers**, which store and carry the data for us.
- **PostHog**, which records how our own site and dashboard are used, so we can fix what is confusing. See below.
- **Google**, if you log in with it: it tells us your name, email address and Google account number.
- **Google reCAPTCHA**, which checks at log-in and sign-up that you are a person. It looks at your browser and IP address, and may set a cookie of its own.
- **flagcdn.com and YouTube**, for the country flags in the inbox and the videos in the docs. Your browser loads them from there, a video only after you press play.

We don't sell data, and we don't use your conversations to train AI models. Your AI provider's terms say what it does with them.

## Files are reachable by link

Files in chats and pictures in articles are in the storage the website's owner connected. Logos and photos are in ours. Addresses are hard to guess, but anyone who has one can open the file.

## Session replays

We may record visits to this site and the dashboard with PostHog: pages, clicks, scrolling and device details, under your account's number. What you type into fields is masked. In the dashboard all text but the menus is masked too, and the inbox and visitor pages are left out. The chat on other websites is never recorded. Turn on "Do Not Track" in your browser and nothing is recorded.

## Cookies

This site, the dashboard and the chat set no tracking cookies. They keep your login, the chat's identity, PostHog's identifier (never in the chat) and small preferences in your browser's storage.

## How long we keep it

Until it is deleted: on request, or with your account. Payment records may be kept longer where the law asks for it.

## Your rights

You can ask to see, correct, export or delete your data, or object to how we use it: ${mail(by)}. You can also complain to your data protection authority.

## Changes

We change this page and its date when something changes.

## Who is responsible

${details(by)}
`,
  },
  terms: {
    label: "Terms",
    title: "Terms of service",
    description: "The terms for using the hosted whileisleep: your account, acceptable use, AI replies, plans and payment, your data, and liability.",
    intro: "The agreement between you and us when you use the hosted service.",
    updated: POLICIES_UPDATED,
    needsOperator: true,
    body: (by) => `
These terms are between you and ${by?.name}, and cover the whileisleep hosted at this address. The source code has its own license; on your own server, only that applies.

## Your account

Use your real details, keep your password to yourself, and tell us if someone else gets in. You are responsible for what happens in your account, and for who you invite to your team. You must be old enough to make a contract where you live.

## Acceptable use

Don't use whileisleep to:

- break the law, or deceive or harass people;
- send spam or malware;
- get into data or systems that aren't yours;
- overload the service, or get around its limits.

We may suspend an account that does.

## Your visitors

You decide what your chat collects, so you need the right to collect it. Tell your visitors about the chat and the AI in your own privacy policy, and answer their requests about their data.

## The AI can be wrong

Replies come from an AI model you chose, using your data and your account with its provider. They can be wrong, and you are responsible for what your chat tells people. Don't rely on it where a mistake could hurt someone, such as medical or emergency advice.

## Plans and payment

- There is a 14-day free trial, without a card. After it the AI pauses until you pick a plan; your inbox and data stay.
- Plans renew each month or year until you cancel, at the price on the [pricing page](/pricing), plus tax.
- Dodo Payments is the seller: it takes the payment and sends the invoice.
- You pay your AI provider separately.
- Nothing is shipped. Access opens once the payment is confirmed, usually within seconds.
- Cancelling and money back: see the [refund policy](/refunds).

A new price never applies to time you have already paid for.

## Your content

It stays yours. You let us store, process and show it as needed to run the service for you. The [privacy policy](/privacy) says what happens to it.

## The service

We work to keep it running, but don't promise it never stops or fails. We may change features. You can leave at any time, and we may end the service with reasonable notice so you can take your data.

## Liability

The service is provided as it is. As far as the law allows, we aren't liable for indirect losses such as lost profit or data, and our total liability is limited to what you paid us in the 12 months before. Nothing here limits rights the law says can't be limited.
${by?.jurisdiction ? `\n## Law\n\nThese terms follow the law of ${by.jurisdiction}, along with any consumer rights you have where you live.\n` : ""}
## Changes

We change this page and its date when the terms change. A change counts from that date on.

## Contact

${details(by)}
`,
  },
  refunds: {
    label: "Refunds",
    title: "Refund and cancellation policy",
    description: "How to cancel a whileisleep plan, what happens to your chat afterwards, and when a payment for the hosted version is refunded.",
    intro: "Try it free for 14 days, and cancel whenever you like.",
    updated: POLICIES_UPDATED,
    needsOperator: true,
    body: (by) => `
## Try before you pay

The trial is 14 days and needs no card. whileisleep is also open source: you can run it yourself for free, see how it works, and then buy.

## Cancelling

Open **Billing › Manage plan**. You keep the plan until the end of the time you paid for, and it doesn't renew. Then the AI pauses; your inbox, widget and data stay.

## Refunds

- **Monthly plan:** a month isn't refunded once it is paid.
- **Yearly plan:** you can ask for the months you haven't started. The month you are in isn't refunded, and the plan ends when the money is returned.
- **Duplicate payment, on either plan:** the extra payment is refunded in full.

What you pay your AI provider is between you and them.

## How to ask

Write to ${mail(by)} with the email you log in with and the receipt. An approved refund goes back to the way you paid, through Dodo Payments. Your bank may take a few days to show it.
`,
  },
};

/** The pages this installation has. */
export function sitePages(by: Operator | null): { slug: string; page: SitePage }[] {
  return Object.entries(SITE_PAGES)
    .filter(([, page]) => by !== null || !page.needsOperator)
    .map(([slug, page]) => ({ slug, page }));
}
