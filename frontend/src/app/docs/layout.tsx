import Link from "next/link";
import { DocNav } from "@/components/docs/doc-nav";
import { Logo, ThemeToggle } from "@/components/ui";
import { docSections } from "@/lib/docs";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <Link href="/" className="rounded" aria-label="whileisleep home">
              <Logo />
            </Link>
            <Link href="/docs" className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold text-muted-foreground hover:text-foreground">
              Docs
            </Link>
          </div>
          <nav className="flex items-center gap-1 sm:gap-2">
            <ThemeToggle />
            <Link
              href="/app"
              className="inline-flex items-center rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              Open inbox
            </Link>
          </nav>
        </div>
      </header>
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-12">
        <aside className="lg:sticky lg:top-8 lg:max-h-[calc(100vh-4rem)] lg:self-start lg:overflow-y-auto">
          <DocNav sections={docSections()} />
        </aside>
        {children}
      </div>
    </div>
  );
}
