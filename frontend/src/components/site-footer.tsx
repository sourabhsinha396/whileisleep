import Link from "next/link";
import { Logo } from "@/components/ui";
import { operator } from "@/lib/operator";
import { sitePages } from "@/lib/site-pages";

/** Under the public pages. A server component: which pages there are depends on the server's settings. */
export function SiteFooter() {
  const links = [
    { href: "/pricing", label: "Pricing" },
    { href: "/docs", label: "Docs" },
    ...sitePages(operator()).map(({ slug, page }) => ({ href: `/${slug}`, label: page.label })),
  ];
  return (
    <footer className="border-t">
      <div className="mx-auto max-w-7xl px-4 py-8 text-sm text-muted-foreground sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-5">
          <Logo />
          <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
            {links.map(({ href, label }) => (
              <Link key={href} href={href} className="hover:text-foreground">
                {label}
              </Link>
            ))}
          </nav>
        </div>
        <p className="mt-6">Open source. Self-host it, bring your own LLM. Get some sleep.</p>
      </div>
    </footer>
  );
}
