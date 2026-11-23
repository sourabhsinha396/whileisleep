/**
 * Renders an A2UI surface to plain DOM, for the widget (no framework) and the dashboard.
 *
 * Implements part of the basic catalog: Column, Row, Card, Text, Button, TextField,
 * CheckBox, Divider, Image. Unknown components render nothing, so an agent can never
 * inject markup: every string goes in as text, and image URLs must be http(s).
 * Styling uses `a2ui-*` class names that the host styles.
 */

import { actionEvent, resolve, setPointer, type ActionEvent, type Component, type Json, type Surface } from "./surface";

export interface RenderOptions {
  onAction?: (event: ActionEvent) => void;
  /** Read-only preview: inputs and buttons are disabled. */
  disabled?: boolean;
}

const MAX_DEPTH = 20;

export function renderSurface(surface: Surface, options: RenderOptions = {}): HTMLElement {
  const root = document.createElement("div");
  root.className = "a2ui-surface";
  root.dataset.surfaceId = surface.surfaceId;
  const node = renderComponent("root", surface, options, 0);
  if (node) root.appendChild(node);
  return root;
}

function el(tag: string, className: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  return node;
}

function asText(value: Json | undefined): string {
  if (value === undefined || value === null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function childIds(component: Component): string[] {
  const children = component.children;
  if (Array.isArray(children)) return children.filter((c): c is string => typeof c === "string");
  return typeof component.child === "string" ? [component.child] : [];
}

function renderComponent(id: string, surface: Surface, options: RenderOptions, depth: number): HTMLElement | null {
  const component = surface.components.get(id);
  if (!component || depth > MAX_DEPTH) return null;
  const children = () =>
    childIds(component)
      .map((child) => renderComponent(child, surface, options, depth + 1))
      .filter((n): n is HTMLElement => n !== null);

  switch (component.component) {
    case "Column":
    case "Row":
    case "Card": {
      const node = el("div", `a2ui-${component.component.toLowerCase()}`);
      node.append(...children());
      return node;
    }
    case "Text": {
      const node = el("p", `a2ui-text${component.variant ? ` a2ui-text-${component.variant}` : ""}`);
      node.textContent = asText(resolve(component.text, surface));
      return node;
    }
    case "Divider":
      return el("hr", "a2ui-divider");
    case "Image": {
      const url = asText(resolve(component.url, surface));
      if (!/^https?:\/\//.test(url)) return null;
      const node = el("img", "a2ui-image") as HTMLImageElement;
      node.src = url;
      node.alt = asText(resolve(component.altText ?? component.alt, surface));
      return node;
    }
    case "Button": {
      const node = el("button", `a2ui-button a2ui-button-${component.variant ?? "default"}`) as HTMLButtonElement;
      node.type = "button";
      node.dataset.componentId = component.id;
      node.append(...children());
      node.disabled = !!options.disabled;
      node.addEventListener("click", () => {
        const event = actionEvent(component, surface);
        if (event && options.onAction) options.onAction(event);
      });
      return node;
    }
    case "TextField": {
      const wrap = el("label", "a2ui-field");
      const label = el("span", "a2ui-field-label");
      label.textContent = asText(resolve(component.label, surface));
      const multiline = component.variant === "longText";
      const input = el(multiline ? "textarea" : "input", "a2ui-input") as HTMLInputElement;
      if (!multiline) input.type = component.variant === "obscured" ? "password" : "text";
      input.value = asText(resolve(component.value, surface));
      input.disabled = !!options.disabled;
      const binding = (component.value as { "@path"?: string } | undefined)?.["@path"];
      input.addEventListener("input", () => {
        // Inputs write to the local data model; the agent sees it only through an action.
        if (binding) setPointer(surface.dataModel, binding, input.value);
      });
      wrap.append(label, input);
      return wrap;
    }
    case "CheckBox": {
      const wrap = el("label", "a2ui-checkbox");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = resolve(component.value, surface) === true;
      input.disabled = !!options.disabled;
      const binding = (component.value as { "@path"?: string } | undefined)?.["@path"];
      input.addEventListener("change", () => {
        if (binding) setPointer(surface.dataModel, binding, input.checked);
      });
      const text = el("span", "");
      text.textContent = asText(resolve(component.label, surface));
      wrap.append(input, text);
      return wrap;
    }
    default:
      return null;
  }
}
