import type { StorageSettings } from "@/lib/api";

export type Provider = "r2" | "s3" | "other";

/** What differs between providers: where to find each value, and whether there is a region to fill in. */
export const PROVIDERS: Record<Provider, { label: string; endpoint: string; region: string; publicUrl: string; help: string; keysUrl?: string }> = {
  r2: {
    label: "Cloudflare R2",
    endpoint: "https://<account id>.r2.cloudflarestorage.com",
    region: "",
    publicUrl: "https://files.example.com",
    help: "Create a bucket, turn on public access (a custom domain, or its r2.dev address), then create an API token with Object Read & Write for that bucket.",
    keysUrl: "https://dash.cloudflare.com/?to=/:account/r2/api-tokens",
  },
  s3: {
    label: "AWS S3",
    endpoint: "https://s3.eu-central-1.amazonaws.com",
    region: "eu-central-1",
    publicUrl: "https://my-uploads.s3.eu-central-1.amazonaws.com",
    help: "Create a bucket whose objects anyone can read (or put CloudFront in front), then create an access key that may put and delete objects in it.",
    keysUrl: "https://console.aws.amazon.com/iam/home#/users",
  },
  other: {
    label: "Other",
    endpoint: "https://fsn1.your-objectstorage.com",
    region: "fsn1",
    publicUrl: "https://my-uploads.fsn1.your-objectstorage.com",
    help: "Any S3-compatible storage works. The bucket's files must be readable by anyone, and the key must be able to write and delete.",
  },
};

/** Which provider a saved endpoint belongs to. */
export function providerOf(endpoint: string): Provider {
  let host = "";
  try {
    host = new URL(endpoint).hostname;
  } catch {
    return endpoint ? "other" : "r2";
  }
  if (host.endsWith(".r2.cloudflarestorage.com")) return "r2";
  return host.endsWith(".amazonaws.com") ? "s3" : "other";
}

export interface StorageForm {
  endpoint_url: string;
  region: string;
  bucket: string;
  access_key_id: string;
  secret_access_key: string;
  public_base_url: string;
}

export function formFor(saved: StorageSettings): StorageForm {
  return {
    endpoint_url: saved.endpoint_url,
    region: saved.region === "auto" ? "" : saved.region,
    bucket: saved.bucket,
    // Never sent back by the server; empty keeps the saved key.
    access_key_id: "",
    secret_access_key: "",
    public_base_url: saved.public_base_url,
  };
}

/** Whether there is enough to try the connection. */
export function complete(form: StorageForm, provider: Provider, connected: boolean): boolean {
  const needed = [form.endpoint_url, form.bucket, form.public_base_url];
  if (provider === "s3") needed.push(form.region);
  const key = [form.access_key_id.trim(), form.secret_access_key.trim()];
  const hasKey = key.every(Boolean) || (connected && !key.some(Boolean));
  return hasKey && needed.every((value) => value.trim() !== "");
}
