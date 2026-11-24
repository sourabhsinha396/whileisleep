import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PluginFields, PluginIcon } from "@/components/plugin-fields";
import type { PluginField } from "@/lib/api";
import { complete, eventName, finish, iconUrl, initialValues, readCallback, run, statusOf, summaryOf, toggled } from "@/lib/integrations";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const field = (name: string, more: Partial<PluginField> = {}): PluginField => ({
  name,
  label: name,
  kind: "text",
  help: "",
  placeholder: "",
  options: [],
  default: "",
  required: true,
  ...more,
});
const OPTIONS = ["a", "b", "c"].map((value) => ({ value, label: value.toUpperCase() }));

describe("values", () => {
  it("start with what was saved, else the default", () => {
    const fields = [field("room", { default: "x" }), field("mode", { default: "all" })];
    expect(initialValues(fields, { room: "r1", gone: "1" })).toEqual({ room: "r1", mode: "all" });
  });

  it("are complete when everything needed is there", () => {
    const fields = [field("room"), field("prefix", { required: false }), field("key", { kind: "secret" })];
    expect(complete(fields, { room: "r1", key: "k" })).toBe(true);
    expect(complete(fields, { room: " ", key: "k" })).toBe(false);
    expect(complete(fields, { room: "r1" })).toBe(false);
    expect(complete(fields, { room: "r1" }, ["key"])).toBe(true);
  });

  it("of several choices keep the order they are offered in", () => {
    const choices = field("events", { kind: "choices", options: OPTIONS });
    expect(toggled(choices, "", "b")).toBe("b");
    expect(toggled(choices, "c", "a")).toBe("a,c");
    expect(toggled(choices, "a,b", "b")).toBe("a");
    expect(toggled(choices, "a", "a")).toBe("");
  });
});

describe("status", () => {
  const ok = { ready: true, last_error: "" };
  const connection = (more = {}) => ({ id: 1, account_name: "Acme", settings: {}, secrets: [], ...ok, ...more });

  it("says what to look at first", () => {
    expect(statusOf(true, ok).label).toBe("Working");
    expect(statusOf(true, { ...ok, ready: false }).label).toBe("Finish setting up");
    expect(statusOf(true, { ...ok, last_error: "x" }).label).toBe("Not working");
    expect(statusOf(false, { ...ok, last_error: "x" }).label).toBe("Off on this server");
  });

  it("of several connections is the worst one's", () => {
    const connections = [connection(), connection({ ready: false }), connection({ last_error: "x" })];
    expect(summaryOf({ available: true, connections })?.label).toBe("Not working");
    expect(summaryOf({ available: true, connections: connections.slice(0, 2) })?.label).toBe("Finish setting up");
    expect(summaryOf({ available: true, connections: [connection()] })?.label).toBe("Working");
  });

  it("without a connection only matters if the server can't", () => {
    expect(summaryOf({ available: true, connections: [] })).toBeNull();
    expect(summaryOf({ available: false, connections: [] })?.label).toBe("Not set up on this server");
  });
});

it("names events in words, and leaves unknown ones as they are", () => {
  expect(eventName("person_requested")).toBe("Needs a person");
  expect(eventName("from_the_future")).toBe("from_the_future");
});

describe("coming back from the service", () => {
  it.each([
    ["?code=c&state=s", { code: "c", state: "s" }],
    ["?error=access_denied&state=s", { error: "You cancelled, so nothing was connected." }],
    ["?code=c", { error: "Nothing was connected. Try again." }],
    ["", { error: "Nothing was connected. Try again." }],
  ])("with %s", (search, expected) => {
    expect(readCallback(search)).toEqual(expected);
  });
});

describe("jobs", () => {
  const answers = (...bodies: object[]) => {
    const fetch = vi.fn<(path: string) => Promise<Response>>(async () => new Response(JSON.stringify(bodies.length > 1 ? bodies.shift() : bodies[0])));
    vi.stubGlobal("fetch", fetch);
    return fetch;
  };
  afterEach(() => vi.unstubAllGlobals());
  const soon = async () => {};

  it("are waited for", async () => {
    const fetch = answers({ done: false, error: "", result: {} }, { done: false, error: "", result: {} }, { done: true, error: "", result: { a: 1 } });
    expect(await finish("j1", soon)).toEqual({ a: 1 });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/integrations/jobs/j1");
  });

  it("that fail say why", async () => {
    answers({ done: true, error: "That key doesn't work.", result: {} });
    await expect(finish("j1", soon)).rejects.toThrow("That key doesn't work.");
  });

  it("that never end are given up on", async () => {
    const fetch = answers({ done: false, error: "", result: {} });
    await expect(finish("j1", soon)).rejects.toThrow("taking too long");
    expect(fetch.mock.calls.length).toBeLessThan(100);
  });

  it("are started and waited for", async () => {
    answers({ job: "j2" }, { done: true, error: "", result: { ok: 1 } });
    expect(await run("/x", { method: "PUT" })).toEqual({ ok: 1 });
  });
});

describe("a plugin's fields", () => {
  let root: Root;
  let box: HTMLElement;
  beforeEach(() => {
    box = document.createElement("div");
    document.body.appendChild(box);
    root = createRoot(box);
  });
  afterEach(() => {
    act(() => root.unmount());
    box.remove();
  });
  const show = (node: React.ReactNode) => act(() => root.render(node));

  it("are drawn by their kind", () => {
    const fields = [
      field("name"),
      field("key", { kind: "secret" }),
      field("mode", { kind: "choice", options: OPTIONS }),
      field("events", { kind: "choices", options: OPTIONS }),
    ];
    show(<PluginFields fields={fields} values={{ mode: "b", events: "a,c" }} onChange={() => {}} secrets={["key"]} />);
    expect(box.querySelectorAll("input[type=text]")).toHaveLength(1);
    expect(box.querySelector<HTMLInputElement>("input[type=password]")!.value).toBe("");
    expect(box.textContent).toContain("Leave empty to keep it");
    const checked = (type: string) => [...box.querySelectorAll<HTMLInputElement>(`input[type=${type}]`)].map((i) => i.checked);
    expect(checked("radio")).toEqual([false, true, false]);
    expect(checked("checkbox")).toEqual([true, false, true]);
  });

  it("change one value at a time", () => {
    const onChange = vi.fn();
    const fields = [field("mode", { kind: "choice", options: OPTIONS }), field("events", { kind: "choices", options: OPTIONS })];
    show(<PluginFields fields={fields} values={{ mode: "a", events: "a" }} onChange={onChange} />);
    act(() => box.querySelectorAll<HTMLInputElement>("input[type=radio]")[2].click());
    expect(onChange).toHaveBeenLastCalledWith({ mode: "c", events: "a" });
    act(() => box.querySelectorAll<HTMLInputElement>("input[type=checkbox]")[1].click());
    expect(onChange).toHaveBeenLastCalledWith({ mode: "a", events: "a,b" });
  });

  it("of two forms don't share their radio buttons", () => {
    const fields = [field("mode", { kind: "choice", options: OPTIONS })];
    show(
      <>
        <PluginFields id="1-" fields={fields} values={{ mode: "a" }} onChange={() => {}} />
        <PluginFields id="2-" fields={fields} values={{ mode: "b" }} onChange={() => {}} />
      </>,
    );
    expect(new Set([...box.querySelectorAll<HTMLInputElement>("input")].map((i) => i.name)).size).toBe(2);
  });

  it("say when what was chosen is gone", () => {
    show(<PluginFields fields={[field("room", { kind: "select", options: OPTIONS })]} values={{ room: "z" }} onChange={() => {}} />);
    expect(box.textContent).toContain("No longer there");
  });

  it("show the icon as an image, so nothing in it runs", () => {
    show(<PluginIcon svg={'<svg onload="alert(1)"></svg>'} />);
    expect(box.querySelector("svg")).toBeNull();
    expect(box.querySelector("img")!.getAttribute("src")).toBe(iconUrl('<svg onload="alert(1)"></svg>'));
  });
});
