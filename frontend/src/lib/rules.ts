/**
 * Rules as the API stores them (see backend/apps/agent/rules.py and conditions.py), and
 * what the rule editor needs on top: which fields and operators exist, how a row of the
 * editor becomes a condition, and a one-line description of a rule.
 */

export type Scalar = string | number | boolean;

export interface Test {
  field: string;
  op: string;
  value?: Scalar | Scalar[];
}

export type Condition = Test | { all: Condition[] } | { any: Condition[] } | { not: Condition };

export type Action =
  | { type: "reply"; text: string }
  | { type: "instruct"; text: string }
  | { type: "tag"; value: string }
  | { type: "set_attribute"; scope: "contact" | "conversation"; key: string; value: Scalar }
  | { type: "handoff" };

export type FieldKind = "text" | "number" | "boolean" | "tags" | "weekday" | "any";

export interface FieldOption {
  /** The field name, or a prefix ending in "." that the author completes with a key. */
  id: string;
  label: string;
  kind: FieldKind;
}

export const FIELDS: FieldOption[] = [
  { id: "message.text", label: "Message text", kind: "text" },
  { id: "message.intent", label: "Button intent", kind: "text" },
  { id: "message.is_first", label: "Is the first message", kind: "boolean" },
  { id: "message.data.", label: "Button data…", kind: "any" },
  { id: "page.url", label: "Page URL", kind: "text" },
  { id: "page.title", label: "Page title", kind: "text" },
  { id: "contact.", label: "Visitor attribute…", kind: "any" },
  { id: "contact.verified", label: "Visitor is verified", kind: "boolean" },
  { id: "conversation.", label: "Conversation attribute…", kind: "any" },
  { id: "conversation.tags", label: "Tags", kind: "tags" },
  { id: "conversation.has_human", label: "A person has the conversation", kind: "boolean" },
  { id: "time.hour", label: "Hour (0 to 23, workspace time)", kind: "number" },
  { id: "time.weekday", label: "Weekday", kind: "weekday" },
];

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const OP_LABELS: Record<string, string> = {
  contains: "contains",
  not_contains: "doesn't contain",
  contains_any: "contains any of",
  has_word: "has the word",
  has_any_word: "has any of the words",
  starts_with: "starts with",
  ends_with: "ends with",
  equals: "is",
  not_equals: "is not",
  in: "is one of",
  not_in: "is none of",
  gt: "is more than",
  gte: "is at least",
  lt: "is less than",
  lte: "is at most",
  exists: "is known",
  not_exists: "is not known",
};

const OPS_BY_KIND: Record<FieldKind, string[]> = {
  text: ["contains", "contains_any", "has_word", "has_any_word", "not_contains", "equals", "not_equals", "starts_with", "ends_with"],
  number: ["equals", "gte", "gt", "lte", "lt"],
  boolean: ["equals"],
  tags: ["equals", "not_equals"],
  weekday: ["in", "not_in"],
  any: ["equals", "not_equals", "contains", "in", "gt", "lt", "exists", "not_exists"],
};

const LIST_OPS = new Set(["contains_any", "has_any_word", "in", "not_in"]);
const NUMBER_OPS = new Set(["gt", "gte", "lt", "lte"]);
const NO_VALUE_OPS = new Set(["exists", "not_exists"]);

export const opLabel = (op: string) => OP_LABELS[op] ?? op;
export const takesList = (op: string) => LIST_OPS.has(op);
export const takesNoValue = (op: string) => NO_VALUE_OPS.has(op);

/** The catalogue entry for a field name: an exact match, else the longest matching prefix. */
export function fieldOption(field: string): FieldOption {
  const exact = FIELDS.find((option) => option.id === field);
  if (exact) return exact;
  const prefixes = FIELDS.filter((option) => option.id.endsWith(".") && field.startsWith(option.id));
  return prefixes.sort((a, b) => b.id.length - a.id.length)[0] ?? { id: field, label: field, kind: "any" };
}

export const opsFor = (field: string) => OPS_BY_KIND[fieldOption(field).kind];

// --- The editor's flat form: one group of rows ---

/** One line of the rule editor. `value` is what the author typed. */
export interface Row {
  field: string;
  op: string;
  value: string;
}

export interface Group {
  match: "all" | "any";
  rows: Row[];
}

function isTest(node: Condition): node is Test {
  return "field" in node;
}

/** A tree the editor can show as rows: one all/any group of plain tests. */
export function toGroup(tree: Condition): Group | null {
  const match = "all" in tree ? "all" : "any" in tree ? "any" : null;
  if (!match) return null;
  const children = (tree as Record<string, Condition[]>)[match];
  if (!Array.isArray(children) || !children.every(isTest)) return null;
  return { match, rows: (children as Test[]).map(toRow) };
}

export function toRow(test: Test): Row {
  const value = Array.isArray(test.value) ? test.value.join("\n") : test.value === undefined ? "" : String(test.value);
  return { field: test.field, op: test.op, value };
}

/** The condition a row stands for. Lists are split on new lines and commas. */
export function toTest(row: Row): Test {
  const field = row.field.trim();
  const kind = fieldOption(field).kind;
  if (takesNoValue(row.op)) return { field, op: row.op };
  if (takesList(row.op)) {
    const items = row.value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
    return { field, op: row.op, value: items };
  }
  if (kind === "boolean") return { field, op: row.op, value: row.value !== "false" };
  if (NUMBER_OPS.has(row.op) || kind === "number") return { field, op: row.op, value: Number(row.value) };
  return { field, op: row.op, value: row.value.trim() };
}

export function toTree(group: Group): Condition {
  const tests = group.rows.map(toTest);
  return group.match === "all" ? { all: tests } : { any: tests };
}

export function newRow(field = "message.text"): Row {
  const kind = fieldOption(field).kind;
  return { field, op: opsFor(field)[0], value: kind === "boolean" ? "true" : "" };
}

// --- Describing a rule in a sentence ---

export function describeCondition(node: Condition): string {
  if ("all" in node) return node.all.map(describeNested).join(" and ");
  if ("any" in node) return node.any.map(describeNested).join(" or ");
  if ("not" in node) return `not (${describeCondition(node.not)})`;
  const label = fieldOption(node.field);
  const name = label.id.endsWith(".") ? node.field : label.label.toLowerCase();
  if (takesNoValue(node.op)) return `${name} ${opLabel(node.op)}`;
  if (label.kind === "boolean") return node.value === false ? `not: ${name}` : name;
  const value = Array.isArray(node.value) ? node.value.join(", ") : String(node.value ?? "");
  return `${name} ${opLabel(node.op)} ${value}`;
}

function describeNested(node: Condition): string {
  return isTest(node) || "not" in node ? describeCondition(node) : `(${describeCondition(node)})`;
}

export function describeAction(action: Action): string {
  switch (action.type) {
    case "reply":
      return "fixed reply";
    case "instruct":
      return "instructs the AI";
    case "tag":
      return `tag ${action.value}`;
    case "set_attribute":
      return `set ${action.scope}.${action.key} = ${action.value}`;
    case "handoff":
      return "hand off";
  }
}

export function describeRule(rule: { conditions: Condition; actions: Action[] }): string {
  return `When ${describeCondition(rule.conditions)} → ${rule.actions.map(describeAction).join(", ")}`;
}
