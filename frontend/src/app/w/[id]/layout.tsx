"use client";

import clsx from "clsx";
import { BookOpen, Bot, Building2, ChevronsUpDown, Eye, Inbox, LogOut, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { WorkspaceContext } from "@/components/workspace-context";
import { api, getToken, setToken, type User, type Workspace } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

const NAV = [
  { href: "inbox", label: "Inbox", icon: Inbox },
  { href: "visitors", label: "Visitors", icon: Eye },
  { href: "knowledge", label: "Knowledge base", icon: BookOpen },
  { href: "ai", label: "AI agent & tools", icon: Bot },
  { href: "settings", label: "Settings & widget", icon: Settings },
  { href: "organization", label: "Organization & LLM", icon: Building2 },
];

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const [switcher, setSwitcher] = useState(false);
  // Polled so the open-conversation counts stay fresh.
  const { data, reload } = usePoll(
    useCallback(async () => {
      const [me, workspaces] = await Promise.all([api<User>("/auth/me"), api<Workspace[]>("/workspaces")]);
      return { me, workspaces };
    }, []),
    15000,
  );
  const workspace = data?.workspaces.find((w) => String(w.id) === id);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else if (data && !workspace) router.replace("/");
  }, [data, workspace, router]);

  if (!data || !workspace) return <div className="p-10 text-sm text-gray-500">Loading…</div>;
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
      <div className="flex h-screen">
        <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200 bg-[#fafaf8] p-3">
          <p className="px-3 py-3 text-lg font-bold">
            <span className="text-brand">while</span>isleep
          </p>
          <nav className="mt-2 space-y-0.5">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = pathname.startsWith(`/w/${id}/${href}`);
              return (
                <Link
                  key={href}
                  href={`/w/${id}/${href}`}
                  className={clsx(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
                    active ? "bg-white font-semibold shadow-sm ring-1 ring-gray-200" : "text-gray-700 hover:bg-gray-100",
                  )}
                >
                  <Icon size={17} />
                  <span className="flex-1">{label}</span>
                  {href === "inbox" && workspace.open_count > 0 && (
                    <span className="rounded-full bg-brand-soft px-2 text-xs font-semibold text-brand">{workspace.open_count}</span>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="mt-auto space-y-2">
            <div className="rounded-xl border border-gray-200 bg-white p-3 text-xs text-gray-600">
              AI agent is <strong className={workspace.ai_enabled ? "text-green-700" : "text-gray-700"}>{workspace.ai_enabled ? "on" : "off"}</strong>{" "}
              for this workspace.
              {workspace.ai_enabled && !workspace.llm_ready && (
                <span className="mt-1 block text-amber-700">No LLM set up yet, so it answers by keyword search.</span>
              )}
            </div>
            <div className="relative">
              <button
                onClick={() => setSwitcher(!switcher)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-gray-100"
                aria-expanded={switcher}
              >
                <span className="grid h-8 w-8 place-items-center rounded-md bg-gray-200 text-xs font-bold" style={{ background: workspace.color, color: "white" }}>
                  {workspace.name.slice(0, 2).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{workspace.name}</span>
                  <span className="block text-xs text-gray-500 capitalize">{workspace.role}</span>
                </span>
                <ChevronsUpDown size={15} className="text-gray-400" />
              </button>
              {switcher && (
                <div className="absolute bottom-12 left-0 z-10 w-full rounded-xl border border-gray-200 bg-white p-1 shadow-lg">
                  {workspaces.map((w) => (
                    <Link
                      key={w.id}
                      href={`/w/${w.id}/inbox`}
                      onClick={() => setSwitcher(false)}
                      className={clsx("flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-gray-50", w.id === workspace.id && "font-semibold")}
                    >
                      <span className="truncate">{w.name}</span>
                      {w.open_count > 0 && <span className="text-xs text-gray-500">{w.open_count}</span>}
                    </Link>
                  ))}
                  <Link href="/new" className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-brand hover:bg-gray-50">
                    <Plus size={15} /> New workspace
                  </Link>
                  <hr className="my-1 border-gray-100" />
                  <p className="truncate px-3 py-1 text-xs text-gray-500">{me.email}</p>
                  <button onClick={logout} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-gray-50">
                    <LogOut size={15} /> Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </WorkspaceContext.Provider>
  );
}
