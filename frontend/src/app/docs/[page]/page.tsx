import { ArrowLeft, ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { DocBody } from "@/components/docs/doc-body";
import { DocMarkdown } from "@/components/docs/markdown";
import { DocVideo } from "@/components/docs/video";
import { headings } from "@/lib/doc-text";
import { DOC_SLUGS, docEdits, docFile, docSections } from "@/lib/docs";

type Props = { params: Promise<{ page: string }> };

async function slugOf(params: Props["params"]): Promise<string> {
  const { page } = await params;
  // Also keeps the address from naming any other file.
  if (!DOC_SLUGS.includes(page)) notFound();
  return page;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { title, description } = docFile(await slugOf(params));
  return { title, description };
}

export default async function DocPage({ params }: Props) {
  const slug = await slugOf(params);
  // An edit shows at once, and the API isn't there while the app is built.
  await connection();
  const file = docFile(slug);
  const edits = await docEdits(slug);
  const body = edits.body || file.body;
  const onPage = headings(body);
  const pages = docSections().flatMap((section) => section.pages);
  const at = pages.findIndex((page) => page.slug === slug);
  const previous = pages[at - 1];
  const next = pages[at + 1];

  return (
    <div className="grid gap-12 xl:grid-cols-[minmax(0,1fr)_13rem]">
      <main className="max-w-3xl min-w-0">
        <h1 className="text-3xl font-extrabold tracking-tight text-balance">{file.title}</h1>
        <p className="mt-2 text-muted-foreground">{file.description}</p>
        {/* A new page starts closed, and unedited. */}
        <DocBody key={slug} slug={slug} body={body} edited={Boolean(edits.body)} youtubeId={edits.youtube_id}>
          {edits.youtube_id && <DocVideo key={edits.youtube_id} id={edits.youtube_id} title={file.title} />}
          <DocMarkdown>{body}</DocMarkdown>
        </DocBody>
        <nav aria-label="More pages" className="mt-14 flex justify-between gap-4 border-t pt-6 text-sm font-medium">
          {previous ? (
            <Link href={`/docs/${previous.slug}`} className="inline-flex items-center gap-2 text-primary-text hover:underline">
              <ArrowLeft size={15} className="shrink-0" /> {previous.title}
            </Link>
          ) : (
            <span />
          )}
          {next && (
            <Link href={`/docs/${next.slug}`} className="inline-flex items-center gap-2 text-right text-primary-text hover:underline">
              {next.title} <ArrowRight size={15} className="shrink-0" />
            </Link>
          )}
        </nav>
      </main>
      {onPage.length > 1 && (
        <nav aria-label="On this page" className="sticky top-8 hidden max-h-[calc(100vh-4rem)] self-start overflow-y-auto text-sm xl:block">
          <p className="text-xs font-semibold text-muted-foreground">On this page</p>
          <ul className="mt-2 space-y-1.5">
            {onPage.map(({ id, text, level }) => (
              <li key={id} className={level === 3 ? "pl-3" : undefined}>
                <a href={`#${id}`} className="text-muted-foreground hover:text-foreground">
                  {text}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}
