/** Questions on the homepage and the pricing page. Each answer describes what the product does today. */

export interface Question {
  q: string;
  a: string;
}

const AI_COST: Question = {
  q: "What does the AI cost?",
  a: "You add your own OpenRouter key and pick a model, so you pay your provider directly, at their price. We add nothing on top. Rules and help center answers don't call the model at all.",
};

const SAME_SOFTWARE: Question = {
  q: "Is the cloud version the same software?",
  a: "Yes. It's the same open-source code you can run yourself, hosted, updated and backed up by us.",
};

export const PRICING_QUESTIONS: Question[] = [
  AI_COST,
  SAME_SOFTWARE,
  { q: "Why is it so cheap?", a: "It's our launch price for the first customers." },
];

export const HOME_QUESTIONS: Question[] = [
  {
    q: "How do I add it to my site?",
    a: "Paste one script tag. The chat, the help center and your colors come with it, and you change them from the dashboard afterwards.",
  },
  {
    q: "Where do the answers come from?",
    a: "Your help articles, your playbooks, and the tools you connect: your own HTTP APIs or MCP servers. MCP tools arrive switched off, so the agent only uses the ones you turn on.",
  },
  {
    q: "What happens when the AI can't help?",
    a: "It hands the conversation to you, and stays quiet while a person has it. Visitors can ask for a person too. When you're done, hand the chat back to the AI.",
  },
  AI_COST,
  {
    q: "What if my AI provider is down?",
    a: "We retry brief hiccups. If it's still down, the visitor gets the best matches from your help center instead, and the reason is left as an internal note.",
  },
  {
    q: "Can the agent show someone else's data?",
    a: "Tools that need a verified visitor only accept details your server has signed. What a visitor types, or what the page claims, doesn't count as proof.",
  },
  SAME_SOFTWARE,
];
