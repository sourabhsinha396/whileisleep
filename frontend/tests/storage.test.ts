import { describe, expect, it } from "vitest";
import type { StorageSettings } from "@/lib/api";
import { complete, formFor, providerOf, type StorageForm } from "@/lib/storage";

const FORM: StorageForm = {
  endpoint_url: "https://s3.eu-central-1.amazonaws.com",
  region: "eu-central-1",
  bucket: "my-uploads",
  access_key_id: "id",
  secret_access_key: "secret",
  public_base_url: "https://files.example.com",
};

describe("provider", () => {
  it.each([
    ["", "r2"],
    ["https://abc.r2.cloudflarestorage.com", "r2"],
    ["https://abc.eu.r2.cloudflarestorage.com", "r2"],
    ["https://s3.eu-central-1.amazonaws.com", "s3"],
    ["https://fsn1.your-objectstorage.com", "other"],
    ["https://r2.cloudflarestorage.com.example.com", "other"],
    ["not an address", "other"],
  ])("of %s is %s", (endpoint, provider) => {
    expect(providerOf(endpoint)).toBe(provider);
  });
});

describe("form", () => {
  it("never holds a saved key, and hides R2's made-up region", () => {
    const saved: StorageSettings = {
      connected: true,
      endpoint_url: "https://abc.r2.cloudflarestorage.com",
      region: "auto",
      bucket: "my-uploads",
      key_hint: "…1234",
      public_base_url: "https://files.example.com",
      image_count: 0,
      file_count: 0,
    };
    expect(formFor(saved)).toMatchObject({ bucket: "my-uploads", region: "", access_key_id: "", secret_access_key: "" });
  });

  it("needs a key to connect, but keeps the saved one when both halves are empty", () => {
    const empty = { ...FORM, access_key_id: "", secret_access_key: "" };
    expect(complete(FORM, "s3", false)).toBe(true);
    expect(complete(empty, "s3", false)).toBe(false);
    expect(complete(empty, "s3", true)).toBe(true);
    expect(complete({ ...FORM, secret_access_key: " " }, "s3", true)).toBe(false);
  });

  it("asks for a region only where there is one", () => {
    const noRegion = { ...FORM, region: "" };
    expect(complete(noRegion, "s3", false)).toBe(false);
    expect(complete(noRegion, "r2", false)).toBe(true);
    expect(complete(noRegion, "other", false)).toBe(true);
  });
});
