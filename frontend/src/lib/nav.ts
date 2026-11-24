import {
  BookOpen,
  BookText,
  Bot,
  Building2,
  Code2,
  Cpu,
  Eye,
  HardDrive,
  Inbox,
  type LucideIcon,
  MessageCircle,
  Palette,
  Plug,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  Zap,
} from "lucide-react";
import type { Workspace } from "@/lib/api";

/** Where everything in a workspace lives. Every href is below /w/<slug>/. */
export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** The part of the dashboard this opens, when it has pages of its own ("ai" for "ai/behavior"). */
  area?: string;
}

export interface NavGroup {
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

/** What you work with every day. */
export const MAIN_NAV: NavItem[] = [
  { href: "inbox", label: "Inbox", icon: Inbox },
  { href: "visitors", label: "Visitors", icon: Eye },
  { href: "knowledge", label: "Knowledge base", icon: BookOpen },
  { href: "ai/behavior", label: "AI agent", icon: Bot, area: "ai" },
];

/** What you set up once, pinned to the bottom of the sidebar. */
export const SETTINGS_LINK: NavItem = { href: "settings/general", label: "Settings", icon: Settings, area: "settings" };

export const AI_NAV: NavGroup[] = [
  {
    label: "Agent",
    icon: Bot,
    items: [
      { href: "ai/behavior", label: "Behavior", icon: SlidersHorizontal },
      { href: "ai/tools", label: "Tools", icon: Plug },
    ],
  },
  {
    label: "Automation",
    icon: Zap,
    items: [
      { href: "ai/rules", label: "Rules", icon: Zap },
      { href: "ai/playbooks", label: "Playbooks", icon: BookText },
    ],
  },
];

/** The settings this person can use: the identity secret is for workspace owners, the organization for its owner. */
export function settingsNav(workspace: Pick<Workspace, "role" | "is_organization_owner">): NavGroup[] {
  const groups: NavGroup[] = [
    {
      label: "Workspace",
      icon: Settings,
      items: [
        { href: "settings/general", label: "General", icon: SlidersHorizontal },
        { href: "settings/team", label: "Team", icon: Users },
      ],
    },
    {
      label: "Chat widget",
      icon: MessageCircle,
      items: [
        { href: "settings/install", label: "Install", icon: Code2 },
        { href: "settings/appearance", label: "Appearance", icon: Palette },
      ],
    },
  ];
  if (workspace.role === "owner") {
    groups[1].items.push({ href: "settings/identity", label: "Verified identity", icon: ShieldCheck });
  }
  if (workspace.is_organization_owner) {
    groups.push({
      label: "Organization",
      icon: Building2,
      items: [
        { href: "settings/organization", label: "Details", icon: Building2 },
        { href: "settings/ai-model", label: "AI model", icon: Cpu },
        { href: "settings/storage", label: "Storage", icon: HardDrive },
      ],
    });
  }
  return groups;
}

/** Whether the page at `pathname` is this item, or belongs to its area. */
export function isActive(pathname: string, slug: string, item: NavItem): boolean {
  const base = `/w/${slug}/${item.area ?? item.href}`;
  return pathname === base || pathname.startsWith(`${base}/`);
}
