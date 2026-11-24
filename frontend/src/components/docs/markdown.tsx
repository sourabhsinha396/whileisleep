import clsx from "clsx";
import type { Element, ElementContent, Root } from "hast";
import { Info, Lightbulb, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { Children, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import { CodeBlock, CodeTabs } from "@/components/docs/code-block";
import { docHref } from "@/lib/doc-text";
import { REPO_URL } from "@/lib/pricing";

const LANGUAGES: Record<string, string> = {
  html: "HTML",
  js: "JavaScript",
  text: "Text",
  python: "Python",
  php: "PHP",
  sh: "Terminal",
  json: "JSON",
};

const TONES = {
  note: { icon: Info, look: "bg-primary-soft text-primary-text" },
  tip: { icon: Lightbulb, look: "bg-success-soft text-success" },
  warning: { icon: TriangleAlert, look: "bg-warning-soft text-warning" },
};

/** Code blocks right after each other become tabs of one block. */
function groupCode() {
  return (tree: Root) => {
    const grouped: Root["children"] = [];
    const code = (nodes: Element[]): Element => ({ type: "element", tagName: "figure", properties: {}, children: nodes });
    for (const node of tree.children) {
      if (node.type === "text" && !node.value.trim()) continue;
      const previous = grouped.at(-1);
      if (!previous || previous.type !== "element" || !isElement(node, "pre")) grouped.push(node);
      else if (previous.tagName === "pre") grouped[grouped.length - 1] = code([previous, node]);
      else if (previous.tagName === "figure") previous.children.push(node);
      else grouped.push(node);
    }
    tree.children = grouped;
  };
}

/** "> [!TIP]" is a tip, as on GitHub. */
function callouts() {
  return (tree: Root) => {
    for (const node of tree.children) {
      if (!isElement(node, "blockquote")) continue;
      const first = node.children.find((child): child is Element => isElement(child, "p"));
      const text = first?.children[0];
      if (text?.type !== "text") continue;
      const match = /^\[!(NOTE|TIP|WARNING)\]\s*/.exec(text.value);
      if (!match) continue;
      text.value = text.value.slice(match[0].length);
      node.properties = { ...node.properties, "data-tone": match[1].toLowerCase() };
    }
  };
}

function isElement(node: Root["children"][number] | ElementContent, tagName: string): node is Element {
  return node.type === "element" && node.tagName === tagName;
}

function language(pre: Element | undefined): string {
  const code = pre?.children.find((child): child is Element => isElement(child, "code"));
  const classes = code?.properties.className;
  const name = Array.isArray(classes) ? classes.find((c) => String(c).startsWith("language-")) : undefined;
  return name ? String(name).replace("language-", "") : "";
}

const label = (name: string) => LANGUAGES[name] ?? name;

/** The text of a page of the docs. Raw HTML in it is not rendered. */
export function DocMarkdown({ children }: { children: string }) {
  return (
    <div className="doc-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug, callouts, groupCode, rehypeHighlight]}
        components={{
          a: DocAnchor,
          pre: ({ node, children }) => <CodeBlock label={label(language(node))}>{children}</CodeBlock>,
          figure: ({ node, children }) => (
            <CodeTabs labels={(node?.children ?? []).map((pre) => label(language(pre as Element)))}>
              {Children.toArray(children)}
            </CodeTabs>
          ),
          blockquote: ({ node, children }) => {
            const tone = TONES[node?.properties["data-tone"] as keyof typeof TONES];
            if (!tone) return <blockquote>{children}</blockquote>;
            return (
              <div role="note" className={clsx("my-5 flex gap-3 rounded-lg px-4 py-3 text-sm", tone.look)}>
                <tone.icon size={17} className="mt-0.5 shrink-0" aria-hidden />
                <div className="min-w-0 text-foreground">{children}</div>
              </div>
            );
          },
          table: ({ children }) => (
            <div className="my-5 overflow-x-auto rounded-lg border">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

function DocAnchor({ href = "", children }: ComponentProps<"a">) {
  const target = docHref(href, REPO_URL);
  // A file of the repository, when nobody said where that is.
  if (!target) return <>{children}</>;
  if (/^https?:/.test(target)) {
    return (
      <a href={target} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  }
  return <Link href={target}>{children}</Link>;
}
