"use client";

import { FileText } from "lucide-react";
import { type ChatFile, fileSize, fitted, isPicture } from "@/lib/chat-file";
import { type Inline, parse, parsePlain } from "@/lib/chat-text";
import { safeHref } from "@/widget/text";

/** A message's text with its formatting, as the visitor sees it. `plain` is for what a visitor
 * typed, which is shown as typed. */
export function ChatText({ text, plain, base }: { text: string; plain?: boolean; base?: string }) {
  const blocks = (plain ? parsePlain : parse)(text);
  return (
    <div className="space-y-2 [overflow-wrap:anywhere]">
      {blocks.map((block, i) => {
        if (block.type === "paragraph") return <p key={i}>{block.content.map((piece, j) => <Piece key={j} piece={piece} base={base} />)}</p>;
        const items = block.items.map((item, j) => (
          <li key={j}>
            {item.map((piece, k) => (
              <Piece key={k} piece={piece} base={base} />
            ))}
          </li>
        ));
        return block.ordered ? (
          <ol key={i} start={block.start} className="list-decimal space-y-0.5 pl-5">
            {items}
          </ol>
        ) : (
          <ul key={i} className="list-disc space-y-0.5 pl-5">
            {items}
          </ul>
        );
      })}
    </div>
  );
}

function Piece({ piece, base }: { piece: Inline; base?: string }) {
  if (piece.type === "break") return <br />;
  let node: React.ReactNode = piece.text;
  if (piece.italic) node = <em>{node}</em>;
  if (piece.bold) node = <strong>{node}</strong>;
  const href = piece.href && safeHref(piece.href, base);
  if (!href) return node;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
      {node}
    </a>
  );
}

/** The files sent with a message. */
export function ChatFiles({ files }: { files: ChatFile[] }) {
  return files.map((file) => {
    if (isPicture(file)) {
      const size = fitted(file.width!, file.height!, 280, 220);
      return (
        <a key={file.id} href={file.url} target="_blank" rel="noopener noreferrer" title={file.name} className="mt-1 block first:mt-0">
          {/* In the customer's bucket, so next/image can't fetch it. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={file.url}
            alt={file.name}
            width={size.width}
            height={size.height}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="max-w-full rounded-xl bg-muted object-cover ring-1 ring-border"
          />
        </a>
      );
    }
    return (
      <a
        key={file.id}
        href={file.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 flex max-w-72 items-center gap-2.5 rounded-xl border bg-surface px-3 py-2 text-sm text-foreground shadow-sm transition-colors first:mt-0 hover:bg-muted"
      >
        <FileText size={18} className="shrink-0 text-primary-text" />
        <span className="min-w-0">
          <span className="block truncate font-medium">{file.name}</span>
          <span className="block text-xs text-muted-foreground">{fileSize(file.size)}</span>
        </span>
      </a>
    );
  });
}
