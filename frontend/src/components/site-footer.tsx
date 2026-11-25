import Link from "next/link";
import { Logo } from "@/components/ui";
import { operator } from "@/lib/operator";
import { SITE_PAGES, sitePages } from "@/lib/site-pages";

const page = (slug: string) => ({ href: `/${slug}`, label: SITE_PAGES[slug].label });

/** A new link is one line here, and a new group one more entry. */
const COLUMNS = [
  {
    title: "Product",
    links: [
      { href: "/pricing", label: "Pricing" },
      { href: "/#demo", label: "Try the demo" },
    ],
  },
  {
    title: "Resources",
    links: [
      { href: "/docs", label: "Docs" },
      { href: "/docs/self-hosting", label: "Self-hosting" },
    ],
  },
  { title: "Company", links: ["about", "contact"].map(page) },
  { title: "Legal", links: ["privacy", "terms", "refunds"].map(page) },
];

/** The columns, without the pages this installation doesn't have. */
function columns() {
  const here = new Set(sitePages(operator()).map(({ slug }) => `/${slug}`));
  const missing = new Set(Object.keys(SITE_PAGES).map((slug) => `/${slug}`).filter((href) => !here.has(href)));
  return COLUMNS.map(({ title, links }) => ({ title, links: links.filter(({ href }) => !missing.has(href)) })).filter(({ links }) => links.length > 0);
}

/** Under the public pages. A server component: which pages there are depends on the server's settings. */
export function SiteFooter() {
  return (
    <footer className="border-t bg-muted/40">
      <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <div className="grid gap-10 lg:grid-cols-[1fr_2fr]">
          <div>
            <Logo />
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">Customer chat that answers from your own data, and wakes you only when it should.</p>
          </div>
          <nav aria-label="Footer" className="grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-4">
            {columns().map(({ title, links }) => (
              <div key={title}>
                <h2 className="text-sm font-semibold">{title}</h2>
                <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
                  {links.map(({ href, label }) => (
                    <li key={href}>
                      <Link href={href} className="hover:text-foreground">
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>
        <p className="mt-12 border-t pt-6 text-xs text-muted-foreground">© {new Date().getFullYear()} whileisleep. Open source. Get some sleep.</p>
      </div>
    </footer>
  );
}
