"use client";

import clsx from "clsx";
import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { DocSection } from "@/lib/docs";

/** Every page of the docs: beside the text, or folded above it on a small screen. */
export function DocNav({ sections }: { sections: DocSection[] }) {
  const pathname = usePathname();
  const list = (
    <div className="space-y-6">
      {sections.map((section) => (
        <div key={section.title}>
          <p className="px-3 text-xs font-semibold text-muted-foreground">{section.title}</p>
          <ul className="mt-1.5 space-y-0.5">
            {section.pages.map(({ slug, title }) => {
              const active = pathname === `/docs/${slug}`;
              return (
                <li key={slug}>
                  <Link
                    href={`/docs/${slug}`}
                    aria-current={active ? "page" : undefined}
                    className={clsx(
                      "block rounded-md px-3 py-1.5 text-sm transition-colors",
                      active ? "bg-primary-soft font-semibold text-primary-text" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
  return (
    <>
      <nav aria-label="Docs" className="hidden lg:block">
        {list}
      </nav>
      {/* A new page starts with it folded again. */}
      <details key={pathname} className="rounded-lg border bg-surface lg:hidden">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold">
          <Menu size={16} /> All pages
        </summary>
        <nav aria-label="Docs" className="border-t p-3">
          {list}
        </nav>
      </details>
    </>
  );
}
