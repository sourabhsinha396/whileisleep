import { describe, expect, it, vi } from "vitest";
import { renderSurface } from "@/lib/a2ui/render";
import { applyMessages, getPointer, setPointer, type A2uiMessage, type Json } from "@/lib/a2ui/surface";

const CATALOG = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json";

/** The same shape the backend's a2ui.email_form builds. */
function emailForm(): A2uiMessage[] {
  return [
    { version: "1.0", createSurface: { surfaceId: "email_1", catalogId: CATALOG, dataModel: { email: "" } } },
    {
      version: "1.0",
      updateComponents: {
        surfaceId: "email_1",
        components: [
          { id: "root", component: "Column", children: ["prompt", "email", "save"] },
          { id: "prompt", component: "Text", text: "Leave your email" },
          { id: "email", component: "TextField", label: "Email", variant: "shortText", value: { "@path": "/email" } },
          {
            id: "save",
            component: "Button",
            child: "save_label",
            variant: "primary",
            action: { event: { name: "save_email", context: { email: { "@path": "/email" } } } },
          },
          { id: "save_label", component: "Text", text: "Save email" },
        ],
      },
    },
  ];
}

describe("applyMessages", () => {
  it("creates surfaces and adds components", () => {
    const surface = applyMessages(emailForm()).get("email_1")!;
    expect(surface.components.size).toBe(5);
    expect(surface.dataModel).toEqual({ email: "" });
  });

  it("ignores updates for unknown surfaces", () => {
    const surfaces = applyMessages([{ version: "1.0", updateComponents: { surfaceId: "nope", components: [] } }]);
    expect(surfaces.size).toBe(0);
  });

  it("updates and deletes data model keys", () => {
    const surfaces = applyMessages([
      ...emailForm(),
      { version: "1.0", updateDataModel: { surfaceId: "email_1", path: "/user/name", value: "Sofia" } },
    ]);
    expect(getPointer(surfaces.get("email_1")!.dataModel as Json, "/user/name")).toBe("Sofia");
    applyMessages([{ version: "1.0", updateDataModel: { surfaceId: "email_1", path: "/user/name", value: null } }], surfaces);
    expect(surfaces.get("email_1")!.dataModel).toEqual({ email: "", user: {} });
  });

  it("deletes surfaces", () => {
    const surfaces = applyMessages([...emailForm(), { version: "1.0", deleteSurface: { surfaceId: "email_1" } }]);
    expect(surfaces.has("email_1")).toBe(false);
  });
});

describe("JSON pointers", () => {
  it("handles escaped tokens", () => {
    const data: { [k: string]: Json } = {};
    setPointer(data, "/a~1b/c~0d", 1);
    expect(data).toEqual({ "a/b": { "c~d": 1 } });
    expect(getPointer(data, "/a~1b/c~0d")).toBe(1);
  });
});

describe("renderSurface", () => {
  it("renders text, fields and buttons", () => {
    const node = renderSurface(applyMessages(emailForm()).get("email_1")!);
    expect(node.querySelector(".a2ui-text")!.textContent).toBe("Leave your email");
    expect(node.querySelector("input")).not.toBeNull();
    expect(node.querySelector("button")!.textContent).toBe("Save email");
  });

  it("sends the typed value in the action context", () => {
    const onAction = vi.fn();
    const node = renderSurface(applyMessages(emailForm()).get("email_1")!, { onAction });
    const input = node.querySelector("input")!;
    input.value = "sofia@example.com";
    input.dispatchEvent(new Event("input"));
    node.querySelector("button")!.click();
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "save_email",
        surfaceId: "email_1",
        sourceComponentId: "save",
        context: { email: "sofia@example.com" },
      }),
    );
  });

  it("never renders agent strings as HTML", () => {
    const surface = applyMessages([
      { version: "1.0", createSurface: { surfaceId: "x" } },
      {
        version: "1.0",
        updateComponents: {
          surfaceId: "x",
          components: [
            { id: "root", component: "Column", children: ["t", "img", "evil"] },
            { id: "t", component: "Text", text: "<img src=x onerror=alert(1)>" },
            { id: "img", component: "Image", url: "javascript:alert(1)" },
            { id: "evil", component: "Script", src: "https://evil.example.com" },
          ],
        },
      },
    ]).get("x")!;
    const node = renderSurface(surface);
    expect(node.querySelector("img")).toBeNull();
    expect(node.querySelector("script")).toBeNull();
    expect(node.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("disables controls in read-only mode", () => {
    const node = renderSurface(applyMessages(emailForm()).get("email_1")!, { disabled: true });
    expect(node.querySelector("button")!.disabled).toBe(true);
    expect(node.querySelector("input")!.disabled).toBe(true);
  });

  it("stops at cycles", () => {
    const surface = applyMessages([
      { version: "1.0", createSurface: { surfaceId: "c" } },
      { version: "1.0", updateComponents: { surfaceId: "c", components: [{ id: "root", component: "Column", children: ["root"] }] } },
    ]).get("c")!;
    expect(() => renderSurface(surface)).not.toThrow();
  });
});
