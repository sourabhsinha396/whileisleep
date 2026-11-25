import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocMarkdown } from "@/components/docs/markdown";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { operator } from "@/lib/operator";
import { publicMetadata } from "@/lib/seo";
import { sitePages } from "@/lib/site-pages";

type Props = { params: Promise<{ page: string }> };

/** About, contact and the legal pages. Any other address that no folder of `app` answers also ends here. */
async function load({ params }: Props) {
  const { page: slug } = await params;
  const by = operator();
  const found = sitePages(by).find((one) => one.slug === slug);
  if (!found) notFound();
  return { ...found, by };
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { slug, page } = await load(props);
  return publicMetadata({ title: page.title, description: page.description, path: `/${slug}` });
}

export default async function SitePage(props: Props) {
  const { page, by } = await load(props);
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 pt-8 pb-20 sm:px-6 lg:pt-14">
        <h1 className="text-4xl leading-[1.08] font-extrabold tracking-tight text-balance sm:text-5xl">{page.title}</h1>
        <p className="mt-5 text-lg text-muted-foreground">{page.intro}</p>
        {page.updated && <p className="mt-3 text-sm text-muted-foreground">Last updated {page.updated}</p>}
        <DocMarkdown>{page.body(by)}</DocMarkdown>
      </main>
      <SiteFooter />
    </div>
  );
}
