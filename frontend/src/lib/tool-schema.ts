/** Converts between the tool editor's input rows and the JSON Schema the API stores. */

export type InputType = "string" | "integer" | "number" | "boolean";

export interface InputRow {
  name: string;
  type: InputType;
  description: string;
  required: boolean;
}

interface Schema {
  type: "object";
  properties?: Record<string, unknown>;
  required?: string[];
}

const TYPES: InputType[] = ["string", "integer", "number", "boolean"];

export function rowsToSchema(rows: InputRow[]): Schema {
  const properties: Record<string, { type: InputType; description?: string }> = {};
  const required: string[] = [];
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) continue;
    properties[name] = { type: row.type, ...(row.description.trim() ? { description: row.description.trim() } : {}) };
    if (row.required) required.push(name);
  }
  return { type: "object", properties, ...(required.length ? { required } : {}) };
}

export function schemaToRows(schema: Schema | undefined): InputRow[] {
  const required = new Set(schema?.required ?? []);
  return Object.entries(schema?.properties ?? {}).map(([name, raw]) => {
    const prop = (raw ?? {}) as { type?: string; description?: string };
    return {
      name,
      type: TYPES.includes(prop.type as InputType) ? (prop.type as InputType) : "string",
      description: prop.description ?? "",
      required: required.has(name),
    };
  });
}

/** `{name}` placeholders in a URL, minus `{visitor.*}` ones the server fills. */
export function urlPlaceholders(url: string): string[] {
  return Array.from(url.matchAll(/\{([a-zA-Z_][a-zA-Z0-9_.]*)\}/g), (m) => m[1]).filter((n) => !n.startsWith("visitor."));
}
