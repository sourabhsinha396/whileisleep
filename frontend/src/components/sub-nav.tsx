"use client";

import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, useState } from "react";
import { isActive, type NavGroup } from "@/lib/nav";

/** A second panel beside the sidebar, for an area with pages of its own (AI agent, Settings). */
export function WithSubNav({ title, slug, groups, children }: { title: string; slug: string; groups: NavGroup[]; children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col lg:flex-row">
      <SubNav title={title} slug={slug} groups={groups} />
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}

/** Groups that open and close. On narrow screens, every page in a row that wraps instead. */
function SubNav({ title, slug, groups }: { title: string; slug: string; groups: NavGroup[] }) {
  const pathname = usePathname();
  const [closed, setClosed] = useState<string[]>([]);
  const id = useId();

  return (
    <nav
      aria-label={title}
      className="flex shrink-0 flex-wrap gap-1 border-b bg-muted/30 px-3 py-2 lg:w-60 lg:flex-col lg:flex-nowrap lg:gap-3 lg:overflow-y-auto lg:border-r lg:border-b-0 lg:py-5"
    >
      <p className="hidden px-3 pb-1 text-lg font-bold tracking-tight lg:block">{title}</p>
      {groups.map(({ label, icon: GroupIcon, items }) => {
        const open = !closed.includes(label);
        return (
          <div key={label} className="contents lg:block">
            <button
              type="button"
              onClick={() => setClosed(open ? [...closed, label] : closed.filter((l) => l !== label))}
              aria-expanded={open}
              aria-controls={`${id}-${label}`}
              className="hidden w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm font-semibold transition-colors hover:bg-muted lg:flex"
            >
              <GroupIcon size={16} />
              <span className="flex-1">{label}</span>
              <ChevronDown size={15} className={clsx("text-muted-foreground transition-transform", open && "rotate-180")} />
            </button>
            <div id={`${id}-${label}`} className={clsx("contents lg:mt-0.5 lg:flex-col lg:gap-0.5 lg:pl-4", open ? "lg:flex" : "lg:hidden")}>
              {items.map((item) => {
                const active = isActive(pathname, slug, item);
                return (
                  <Link
                    key={item.href}
                    href={`/w/${slug}/${item.href}`}
                    aria-current={active ? "page" : undefined}
                    className={clsx(
                      "flex shrink-0 items-center gap-2.5 rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
                      active ? "bg-surface font-semibold text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <item.icon size={15} className={active ? "text-primary-text" : undefined} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}
