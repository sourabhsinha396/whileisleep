"use client";

import clsx from "clsx";
import { Check, ChevronsUpDown, LogOut, Plus, Bot } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { GetStarted, useGuide } from "@/components/get-started";
import { Avatar, CoverImage, Logo, Spinner, ThemeToggle } from "@/components/ui";
import { WorkspaceContext } from "@/components/workspace-context";
import { api, getToken, setToken, type User, type Workspace } from "@/lib/api";
import { textOn } from "@/lib/contrast";
import { isActive, MAIN_NAV, type NavItem, SETTINGS_LINK } from "@/lib/nav";
import { useDismiss } from "@/lib/use-dismiss";
import { usePoll } from "@/lib/use-poll";

function SidebarLink({ item, slug, pathname, count = 0 }: { item: NavItem; slug: string; pathname: string; count?: number }) {
  const active = isActive(pathname, slug, item);
  return (
    <Link
      href={`/w/${slug}/${item.href}`}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
        active ? "bg-surface font-semibold text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <item.icon size={17} className={active ? "text-primary-text" : undefined} />
      <span className="flex-1">{item.label}</span>
      {count > 0 && (
        <span className="grid min-w-5 place-items-center rounded-full bg-primary px-1.5 text-[11px] leading-5 font-bold text-primary-foreground">
          {count}
        </span>
      )}
    </Link>
  );
}

function WorkspaceBadge({ workspace, size = 36 }: { workspace: Workspace; size?: number }) {
  return (
    <span
      className="relative grid shrink-0 place-items-center rounded-md text-xs font-bold shadow-sm"
      style={{ background: workspace.color, color: textOn(workspace.color), width: size, height: size }}
    >
      {workspace.name.slice(0, 2).toUpperCase()}
      <CoverImage src={workspace.logo_url} className="rounded-md" />
    </span>
  );
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { slug } = useParams<{ slug: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const [switcher, setSwitcher] = useState(false);
  const [account, setAccount] = useState(false);
  const switcherRef = useDismiss(switcher, useCallback(() => setSwitcher(false), []));
  const accountRef = useDismiss(account, useCallback(() => setAccount(false), []));
  // Polled so the open-conversation counts stay fresh.
  const { data, reload } = usePoll(
    useCallback(async () => {
      const [me, workspaces] = await Promise.all([api<User>("/auth/me"), api<Workspace[]>("/workspaces")]);
      return { me, workspaces };
    }, []),
    15000,
  );
  const workspace = data?.workspaces.find((w) => w.slug === slug);
  const steps = useGuide(workspace);
  const lastId = useRef<number>(undefined);

  useEffect(() => {
    if (!getToken()) return router.replace("/login");
    if (!data) return;
    if (workspace) {
      lastId.current = workspace.id;
      return;
    }
    // Its address was changed while this page was open, or the link is from before slugs (/w/34/inbox).
    const moved = data.workspaces.find((w) => w.id === lastId.current || String(w.id) === slug);
    router.replace(moved ? pathname.replace(`/w/${slug}`, `/w/${moved.slug}`) : "/app");
  }, [data, workspace, pathname, slug, router]);

  if (!data || !workspace) return <div className="h-screen"><Spinner /></div>;
  const { workspaces, me } = data;
  const load = async () => {
    await reload();
  };

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    setToken("");
    router.replace("/login");
  }

  return (
    <WorkspaceContext.Provider value={{ me, workspace, workspaces, reload: load }}>
      <div className="flex h-screen bg-muted/50">
        <aside className="flex w-64 shrink-0 flex-col px-3 pt-4 pb-3">
          <div className="flex items-center justify-between px-2">
            <Link href={`/w/${slug}/inbox`} className="rounded">
              <Logo />
            </Link>
            <ThemeToggle />
          </div>

          {/* Workspace switcher */}
          <div className="relative mt-5" ref={switcherRef}>
            <button
              onClick={() => setSwitcher(!switcher)}
              className="flex w-full items-center gap-2.5 rounded-lg border bg-surface px-2.5 py-2 text-left shadow-sm transition-colors hover:border-primary/40"
              aria-expanded={switcher}
              aria-haspopup="menu"
            >
              <WorkspaceBadge workspace={workspace} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{workspace.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {workspace.website.replace(/^https?:\/\//, "").replace(/\/$/, "") || workspace.role}
                </span>
              </span>
              <ChevronsUpDown size={15} className="text-muted-foreground" />
            </button>
            {switcher && (
              <div role="menu" className="absolute top-full left-0 z-30 mt-1.5 w-full rounded-lg border bg-surface p-1 shadow-lg">
                <p className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Workspaces</p>
                {workspaces.map((w) => (
                  <Link
                    key={w.id}
                    href={`/w/${w.slug}/inbox`}
                    onClick={() => setSwitcher(false)}
                    className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <WorkspaceBadge workspace={w} size={24} />
                    <span className="flex-1 truncate">{w.name}</span>
                    {w.open_count > 0 && <span className="text-xs text-muted-foreground">{w.open_count}</span>}
                    {w.id === workspace.id && <Check size={15} className="text-primary-text" />}
                  </Link>
                ))}
                <div className="my-1 h-px bg-border" />
                <Link href="/new" className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-primary-text hover:bg-muted">
                  <Plus size={15} /> New workspace
                </Link>
              </div>
            )}
          </div>

          <nav aria-label="Workspace" className="mt-5 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-px">
            {MAIN_NAV.map((item) => (
              <SidebarLink key={item.href} item={item} slug={slug} pathname={pathname} count={item.href === "inbox" ? workspace.open_count : 0} />
            ))}
            <div className="mt-auto pt-4">
              <SidebarLink item={SETTINGS_LINK} slug={slug} pathname={pathname} />
            </div>
          </nav>

          <div className="space-y-2 pt-3">
            {steps.length > 0 && <GetStarted key={workspace.id} steps={steps} workspaceId={workspace.id} />}

            {/* Only when the agent needs attention: switched off, or on without an LLM (unless
                connecting one is already a step of the guide). */}
            {(!workspace.ai_enabled || (!workspace.llm_ready && !steps.some((step) => step.key === "ai"))) && (
              <Link
                href={`/w/${slug}/ai/behavior`}
                className="block rounded-lg border bg-surface p-3 text-xs shadow-sm transition-colors hover:border-primary/40"
              >
                <span className="flex items-center gap-2 font-semibold">
                  <Bot size={14} className="text-primary-text" />
                  AI agent
                  <span
                    className={clsx(
                      "ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold uppercase",
                      workspace.ai_enabled ? "bg-success-soft text-success" : "bg-muted text-muted-foreground",
                    )}
                  >
                    {workspace.ai_enabled ? "On" : "Off"}
                  </span>
                </span>
                <span className="mt-1.5 block text-muted-foreground">
                  {workspace.ai_enabled ? (
                    <span className="text-warning">No LLM set up yet, so it answers by keyword search.</span>
                  ) : (
                    "Turn it on to answer them automatically."
                  )}
                </span>
              </Link>
            )}

            <div className="relative" ref={accountRef}>
              <button
                onClick={() => setAccount(!account)}
                className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-muted"
                aria-expanded={account}
                aria-haspopup="menu"
              >
                <Avatar name={me.name || me.email} src={me.photo_url} online size={34} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{me.name || "You"}</span>
                  <span className="block truncate text-xs text-muted-foreground">{me.email}</span>
                </span>
              </button>
              {account && (
                <div role="menu" className="absolute bottom-full left-0 z-30 mb-1.5 w-full rounded-lg border bg-surface p-1 shadow-lg">
                  <p className="px-3 py-2 text-xs text-muted-foreground">
                    Signed in as <span className="capitalize">{workspace.role}</span> of {workspace.name}
                  </p>
                  <div className="my-1 h-px bg-border" />
                  <button onClick={logout} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted">
                    <LogOut size={15} className="text-muted-foreground" /> Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </aside>
        <main className="my-2 mr-2 min-w-0 flex-1 overflow-y-auto rounded-xl border bg-background shadow-sm">{children}</main>
      </div>
    </WorkspaceContext.Provider>
  );
}
