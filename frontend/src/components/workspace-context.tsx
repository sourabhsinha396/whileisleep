"use client";

import { createContext, useContext } from "react";
import type { User, Workspace } from "@/lib/api";

export interface WorkspaceState {
  me: User;
  workspace: Workspace;
  workspaces: Workspace[];
  reload: () => Promise<void>;
}

export const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function useWorkspace(): WorkspaceState {
  const state = useContext(WorkspaceContext);
  if (!state) throw new Error("useWorkspace outside a workspace page");
  return state;
}
