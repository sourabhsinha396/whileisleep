/** The widget colors a workspace can choose from. The server accepts exactly these
 * (backend/apps/workspaces/colors.py); a test keeps the two lists equal. */
export interface WidgetColor {
  value: string;
  name: string;
}

export const WIDGET_COLORS: WidgetColor[] = [
  { value: "#2563eb", name: "Blue" },
  { value: "#0369a1", name: "Ocean" },
  { value: "#4f46e5", name: "Indigo" },
  { value: "#7c3aed", name: "Violet" },
  { value: "#a21caf", name: "Plum" },
  { value: "#be185d", name: "Rose" },
  { value: "#dc2626", name: "Red" },
  { value: "#c2410c", name: "Orange" },
  { value: "#b45309", name: "Amber" },
  { value: "#15803d", name: "Green" },
  { value: "#0f766e", name: "Teal" },
  { value: "#1f2937", name: "Charcoal" },
  { value: "#22d3ee", name: "Cyan" },
  { value: "#86efac", name: "Light green" },
  { value: "#f472b6", name: "Pink" },
  { value: "#39ff14", name: "Neon green" },
];

/** The choices to show: the list, after the workspace's own color when that predates it. */
export function colorChoices(saved: string): WidgetColor[] {
  const listed = WIDGET_COLORS.some((c) => c.value === saved.toLowerCase());
  return listed ? WIDGET_COLORS : [{ value: saved, name: "Current" }, ...WIDGET_COLORS];
}
