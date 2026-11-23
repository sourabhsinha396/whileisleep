/**
 * A small A2UI v1.0 client (https://a2ui.org): applies agent messages to surfaces and
 * resolves data bindings. No DOM here; see render.ts.
 *
 * Supported messages: createSurface, updateComponents, updateDataModel, deleteSurface.
 * Function calls (`@call`) are not supported; they resolve to undefined.
 */

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export interface Component {
  id: string;
  component: string;
  [prop: string]: unknown;
}

export interface Surface {
  surfaceId: string;
  catalogId?: string;
  components: Map<string, Component>;
  dataModel: { [key: string]: Json };
}

export type A2uiMessage =
  | { version: string; createSurface: { surfaceId: string; catalogId?: string; components?: Component[]; dataModel?: { [key: string]: Json } } }
  | { version: string; updateComponents: { surfaceId: string; components: Component[] } }
  | { version: string; updateDataModel: { surfaceId: string; path?: string; value: Json } }
  | { version: string; deleteSurface: { surfaceId: string } };

export interface ActionEvent {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  timestamp: string;
  context: { [key: string]: Json };
}

/** Applies a stream of messages. Returns the surfaces that exist afterwards, in creation order. */
export function applyMessages(messages: A2uiMessage[], surfaces = new Map<string, Surface>()): Map<string, Surface> {
  for (const message of messages) {
    if ("createSurface" in message) {
      const { surfaceId, catalogId, components = [], dataModel = {} } = message.createSurface;
      const surface: Surface = { surfaceId, catalogId, components: new Map(), dataModel: structuredClone(dataModel) };
      for (const c of components) surface.components.set(c.id, c);
      surfaces.set(surfaceId, surface);
    } else if ("updateComponents" in message) {
      const surface = surfaces.get(message.updateComponents.surfaceId);
      if (!surface) continue;
      for (const c of message.updateComponents.components) surface.components.set(c.id, c);
    } else if ("updateDataModel" in message) {
      const surface = surfaces.get(message.updateDataModel.surfaceId);
      if (!surface) continue;
      setPointer(surface.dataModel, message.updateDataModel.path ?? "/", message.updateDataModel.value);
    } else if ("deleteSurface" in message) {
      surfaces.delete(message.deleteSurface.surfaceId);
    }
  }
  return surfaces;
}

function unescape(token: string): string {
  return token.replace(/~1/g, "/").replace(/~0/g, "~");
}

/** Reads a JSON Pointer ("/user/name") from the data model. */
export function getPointer(data: Json, path: string): Json | undefined {
  if (path === "" || path === "/") return data;
  let node: Json | undefined = data;
  for (const token of path.replace(/^\//, "").split("/").map(unescape)) {
    if (node === null || typeof node !== "object") return undefined;
    node = Array.isArray(node) ? node[Number(token)] : node[token];
  }
  return node;
}

/** Writes a JSON Pointer. A null value deletes the key, as the spec says. */
export function setPointer(data: { [key: string]: Json }, path: string, value: Json): void {
  const tokens = path.replace(/^\//, "").split("/").filter((t) => t !== "").map(unescape);
  if (tokens.length === 0) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      for (const key of Object.keys(data)) delete data[key];
      Object.assign(data, value);
    }
    return;
  }
  let node: { [key: string]: Json } = data;
  for (const token of tokens.slice(0, -1)) {
    const next = node[token];
    if (next === null || typeof next !== "object" || Array.isArray(next)) node[token] = {};
    node = node[token] as { [key: string]: Json };
  }
  const last = tokens[tokens.length - 1];
  if (value === null) delete node[last];
  else node[last] = value;
}

/** Resolves a prop that may be a literal or a `{"@path": ...}` binding. */
export function resolve(value: unknown, surface: Surface): Json | undefined {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const v = value as { [key: string]: unknown };
    if (typeof v["@path"] === "string") return getPointer(surface.dataModel, v["@path"]);
    if ("@call" in v) return undefined;
  }
  return value as Json;
}

/** Builds the event sent to the agent when a component with an `action.event` fires. */
export function actionEvent(component: Component, surface: Surface): ActionEvent | null {
  const action = component.action as { event?: { name?: string; context?: { [key: string]: unknown } } } | undefined;
  const event = action?.event;
  if (!event?.name) return null;
  const context: { [key: string]: Json } = {};
  for (const [key, raw] of Object.entries(event.context ?? {})) {
    const value = resolve(raw, surface);
    if (value !== undefined) context[key] = value;
  }
  return {
    name: event.name,
    surfaceId: surface.surfaceId,
    sourceComponentId: component.id,
    timestamp: new Date().toISOString(),
    context,
  };
}
