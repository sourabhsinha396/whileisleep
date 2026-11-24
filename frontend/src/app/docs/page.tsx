import Link from "next/link";
import { docSections } from "@/lib/docs";
import { publicMetadata } from "@/lib/seo";

export const generateMetadata = () =>
  publicMetadata({
    title: "Docs: set up your AI support chat",
    description: "Guides for whileisleep: install the chat widget, connect your AI model, write articles and rules, and connect your APIs, Slack and webhooks.",
    path: "/docs",
  });

export default function DocsPage() {
  return (
    <main>
      <h1 className="text-3xl font-extrabold tracking-tight">Docs</h1>
      <p className="mt-2 text-muted-foreground">Set it up, teach the AI agent, and connect your own systems.</p>
      {docSections().map((section) => (
        <section key={section.title} className="mt-10">
          <h2 className="text-lg font-bold tracking-tight">{section.title}</h2>
          <ul className="mt-4 grid gap-4 sm:grid-cols-2">
            {section.pages.map(({ slug, title, description }) => (
              <li key={slug}>
                <Link href={`/docs/${slug}`} className="block h-full rounded-xl border bg-surface p-4 transition-colors hover:border-primary/40">
                  <span className="font-semibold">{title}</span>
                  <span className="mt-1 block text-sm text-muted-foreground">{description}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
