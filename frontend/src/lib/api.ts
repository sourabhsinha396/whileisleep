"use client";

import type { A2uiMessage } from "@/lib/a2ui/surface";
import type { Action, Condition } from "@/lib/rules";

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
  // A form (a file upload) is sent as it is: the browser writes its content type.
  const form = init.body instanceof FormData;
  const response = await fetch(`/api/v1${path}`, {
    method: init.method ?? "GET",
    headers: {
      ...(form ? {} : { "Content-Type": "application/json" }),
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: init.body === undefined ? undefined : form ? (init.body as FormData) : JSON.stringify(init.body),
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

/** Uploads one file. */
export function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  return api<T>(path, { method: "POST", body });
}

// --- Types matching the Django schemas ---

export interface User {
  id: number;
  name: string;
  email: string;
  photo_url: string;
}

export interface Workspace {
  id: number;
  name: string;
  /** The workspace's name in dashboard URLs: /w/<slug>/inbox. */
  slug: string;
  public_key: string;
  website: string;
  color: string;
  logo_url: string;
  greeting: string;
  /** IANA name; rules read the local hour and weekday in it. */
  timezone: string;
  ai_enabled: boolean;
  ai_instructions: string;
  role: "owner" | "agent";
  open_count: number;
  /** The organization has a model and its provider's key. */
  llm_ready: boolean;
  is_organization_owner: boolean;
  /** The server has somewhere to store images. */
  uploads_enabled: boolean;
  /** Articles can have images: the organization connected its own bucket for them. */
  article_uploads_enabled: boolean;
}

/** A step of the "Get started" guide; lib/get-started has its words and link. */
export interface SetupStep {
  key: string;
  done: boolean;
}

export type ProviderId = "openai" | "anthropic" | "google" | "openrouter";

export interface LlmProvider {
  id: ProviderId;
  name: string;
  /** Where its keys are made. */
  keys_url: string;
  has_key: boolean;
  key_hint: string;
}

export interface LlmModel {
  id: string;
  name: string;
}

export interface Organization {
  id: number;
  name: string;
  providers: LlmProvider[];
  llm_provider: ProviderId;
  llm_model: string;
  /** "" when there is no fallback. */
  fallback_provider: ProviderId | "";
  fallback_model: string;
  llm_ready: boolean;
  workspace_count: number;
}

/** The organization's own bucket. The key itself never comes back. */
export interface StorageSettings {
  connected: boolean;
  endpoint_url: string;
  region: string;
  bucket: string;
  key_hint: string;
  public_base_url: string;
  image_count: number;
}

export interface KeyCheck {
  ok: boolean;
  message: string;
  label: string;
  usage: number | null;
  limit_remaining: number | null;
}

/** A named value about a visitor or a conversation, and who said so. */
export interface Attribute {
  key: string;
  value: string | number | boolean;
  source: "verified" | "agent" | "rule" | "host" | "visitor" | "ai";
}

export interface Visitor {
  id: number;
  name: string;
  email: string;
  /** The host site signed for this visitor's identity. */
  verified: boolean;
  attributes: Attribute[];
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
  author_photo: string;
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
  attributes: Attribute[];
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
  /** Set when the tool comes from an MCP server, which defines it. */
  mcp_server_id: number | null;
  /** The server's own claim that the tool changes nothing. */
  read_only: boolean;
  /** An MCP tool whose definition changed since it was approved: not offered to the agent. */
  needs_review: boolean;
}

export interface McpServer {
  id: number;
  name: string;
  url: string;
  header_names: string[];
  enabled: boolean;
  tool_count: number;
  active_tool_count: number;
  last_synced_at: string | null;
  last_error: string;
}

export interface Rule {
  id: number;
  name: string;
  enabled: boolean;
  position: number;
  /** When it applies and what it does; see lib/rules.ts. */
  conditions: Condition;
  actions: Action[];
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
  photo_url: string;
}
