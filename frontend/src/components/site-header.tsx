import Link from "next/link";
import { Logo, ThemeToggle } from "@/components/ui";

const link = "hidden rounded-full px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground sm:block";

/** Over the public pages, except the homepage, which has its own. */
export function SiteHeader() {
  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-5 sm:px-6">
      <Link href="/" className="rounded" aria-label="whileisleep home">
        <Logo />
      </Link>
      <nav className="flex items-center gap-1 sm:gap-2">
        <Link href="/pricing" className={link}>
          Pricing
        </Link>
        <Link href="/docs" className={link}>
          Docs
        </Link>
        <ThemeToggle />
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
        >
          Log in
        </Link>
      </nav>
    </header>
  );
}
