// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, upload } from "@/lib/api";
import { altFromName, imageProblem, IMAGE_TYPES, MAX_IMAGE_BYTES } from "@/lib/image-file";

afterEach(() => vi.unstubAllGlobals());

describe("imageProblem", () => {
  it("accepts what the server accepts", () => {
    for (const type of IMAGE_TYPES) expect(imageProblem({ type, size: MAX_IMAGE_BYTES })).toBe("");
  });

  it.each(["image/svg+xml", "image/gif", "text/html", ""])("refuses %j", (type) => {
    expect(imageProblem({ type, size: 10 })).toContain("PNG, JPEG or WebP");
  });

  it("refuses big files", () => {
    expect(imageProblem({ type: "image/png", size: MAX_IMAGE_BYTES + 1 })).toContain("5 MB");
  });

  it("has the server's limit and formats", () => {
    const server = readFileSync("../backend/whileisleep/images.py", "utf8");
    expect(server).toContain("MAX_BYTES = 5 * 1024 * 1024");
    expect(server).toContain('FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}');
  });
});

describe("altFromName", () => {
  it.each([
    ["reset-password_button.png", "reset password button"],
    ["image.png", ""],
    ["Screenshot 2026-11-24 101500.png", ""],
    ["IMG_1234.jpg", ""],
    ["[draft].png", "draft"],
  ])("%s -> %j", (name, alt) => expect(altFromName(name)).toBe(alt));
});

describe("upload", () => {
  function stub() {
    const fetch = vi.fn(async (url: string, init?: RequestInit) => new Response(JSON.stringify({ url, method: init?.method })));
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  it("sends the file as a form and lets the browser write the content type", async () => {
    const fetch = stub();
    const file = new File(["x"], "a.png", { type: "image/png" });
    await upload("/workspaces/1/logo", file);
    const init = fetch.mock.calls[0][1]!;
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    expect(Object.keys(init.headers!)).not.toContain("Content-Type");
  });

  it("other calls still send JSON", async () => {
    const fetch = stub();
    await api("/x", { method: "POST", body: { a: 1 } });
    const init = fetch.mock.calls[0][1]!;
    expect(init.body).toBe('{"a":1}');
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});
