"use client";

import type { A2uiMessage } from "@/lib/a2ui/surface";

const TOKEN_KEY = "whileisleep:token";

export function getToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Calls /api/v1 with the dashboard token. 401 sends you to the login page. */
export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: init.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !path.startsWith("/auth/")) {
    setToken("");
    // Not in a component, so no router here; a full load also clears stale state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join(", ") : "";
    throw new ApiError(message || `Request failed (${response.status})`, response.status);
  }
  return data as T;
}

// --- Types matching the Django schemas ---

export interface User {
  id: number;
  name: string;
  email: string;
}

export interface Workspace {
  id: number;
  name: string;
  public_key: string;
  website: string;
  color: string;
  greeting: string;
  ai_enabled: boolean;
  ai_instructions: string;
  role: "owner" | "agent";
  open_count: number;
  /** The organization has an OpenRouter key and model. */
  llm_ready: boolean;
  is_organization_owner: boolean;
}

export interface Organization {
  id: number;
  name: string;
  has_openrouter_key: boolean;
  key_hint: string;
  llm_model: string;
  llm_ready: boolean;
  workspace_count: number;
}

export interface KeyCheck {
  ok: boolean;
  message: string;
  label: string;
  usage: number | null;
  limit_remaining: number | null;
}

export interface Visitor {
  id: number;
  name: string;
  email: string;
  online: boolean;
  current_url: string;
  page_title: string;
  referrer: string;
  user_agent: string;
  first_seen: string;
  last_seen: string;
  conversation_id: number | null;
}

export interface Message {
  id: number;
  sender: "visitor" | "agent" | "bot" | "system";
  author_name: string;
  body: string;
  a2ui: A2uiMessage[] | null;
  is_note: boolean;
  /** Label a host-site button attached (rules match on it). */
  intent: string;
  created_at: string;
}

export interface ConversationRow {
  id: number;
  status: "open" | "resolved";
  unread: boolean;
  human_requested: boolean;
  tags: string[];
  assignee_id: number | null;
  last_message_at: string;
  preview: string;
  visitor: Visitor;
}

export interface ConversationDetail extends ConversationRow {
  messages: Message[];
}

export interface Article {
  id: number;
  title: string;
  body: string;
  published: boolean;
  updated_at: string;
}

export interface Tool {
  id: number;
  name: string;
  description: string;
  method: "GET" | "POST";
  url: string;
  input_schema: { type: "object"; properties?: Record<string, unknown>; required?: string[] };
  header_names: string[];
  enabled: boolean;
}

export interface Rule {
  id: number;
  name: string;
  enabled: boolean;
  position: number;
  intent: string;
  keywords: string;
  page_contains: string;
  first_message_only: boolean;
  reply: string;
  ai_instruction: string;
  tag: string;
  handoff: boolean;
  also_when_human: boolean;
  match_count: number;
  last_matched_at: string | null;
}

export interface Playbook {
  id: number;
  title: string;
  when_to_use: string;
  instructions: string;
  enabled: boolean;
  updated_at: string;
}

export interface Member {
  user_id: number;
  name: string;
  email: string;
  role: string;
}
