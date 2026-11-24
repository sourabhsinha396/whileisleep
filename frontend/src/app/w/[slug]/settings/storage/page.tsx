"use client";

import { CheckCircle2, HardDrive } from "lucide-react";
import { useCallback, useState } from "react";
import { OrganizationOnly } from "@/components/organization-only";
import { Button, ErrorText, Field, inputClass, PageHeader, Segmented, Spinner } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type StorageSettings } from "@/lib/api";
import { complete, formFor, type Provider, PROVIDERS, providerOf, type StorageForm } from "@/lib/storage";
import { usePoll } from "@/lib/use-poll";

/** The organization's own bucket for uploaded images. */
export default function StoragePage() {
  return (
    <>
      <PageHeader title="Storage" description="Your own Cloudflare R2, AWS S3 or other S3-compatible bucket, for the images in your articles. Optional." />
      <OrganizationOnly>{() => <Load />}</OrganizationOnly>
    </>
  );
}

function Load() {
  const { data, setData, error } = usePoll(useCallback(() => api<StorageSettings>("/organization/storage"), []), 3600000);
  if (!data) return error ? <ErrorText>{error}</ErrorText> : <Spinner />;
  // A new form after connecting or disconnecting, so no typed key stays in it.
  return <Connection key={`${data.connected} ${data.endpoint_url} ${data.bucket}`} saved={data} onChange={setData} />;
}

function Connection({ saved, onChange }: { saved: StorageSettings; onChange: (saved: StorageSettings) => void }) {
  const { reload } = useWorkspace();
  const [provider, setProvider] = useState<Provider>(providerOf(saved.endpoint_url));
  const [form, setForm] = useState<StorageForm>(formFor(saved));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { endpoint, region, publicUrl, help, keysUrl } = PROVIDERS[provider];
  const field = (name: keyof StorageForm) => ({
    value: form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value }),
    className: inputClass,
    autoComplete: "off",
    spellCheck: false,
  });

  async function run(request: () => Promise<StorageSettings>, note: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const next = await request();
      onChange(next);
      setForm(formFor(next));
      setMessage(note);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function connect(e: React.FormEvent) {
    e.preventDefault();
    // R2 has one region, so a value left over from another provider would only break it.
    const body = provider === "r2" ? { ...form, region: "" } : form;
    run(() => api<StorageSettings>("/organization/storage", { method: "PUT", body }), "It works, and is saved.");
  }

  function disconnect() {
    const question = "Disconnect this bucket? Images already in it stay there and keep showing. New articles are text only.";
    if (window.confirm(question)) run(() => api<StorageSettings>("/organization/storage", { method: "DELETE" }), "Disconnected.");
  }

  return (
    <form onSubmit={connect} className="space-y-5 rounded-lg border bg-surface p-6 shadow-sm">
      <div className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${saved.connected ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}>
        {saved.connected ? <CheckCircle2 size={16} className="shrink-0" /> : <HardDrive size={16} className="shrink-0" />}
        {saved.connected
          ? `Connected: article images go to ${saved.bucket}. ${saved.image_count} stored there so far.`
          : "Your articles are text only. Connect a bucket to add images; they stay in your bucket, never in ours."}
      </div>

      <div className="space-y-2">
        <Segmented<Provider>
          value={provider}
          onChange={setProvider}
          options={(Object.keys(PROVIDERS) as Provider[]).map((value) => ({ value, label: PROVIDERS[value].label }))}
        />
        <p className="text-sm text-muted-foreground">
          {help}{" "}
          {keysUrl && (
            <a className="text-primary-text hover:underline" href={keysUrl} target="_blank" rel="noreferrer">
              Create a key
            </a>
          )}
        </p>
      </div>

      <Field label="Endpoint" hint="The storage's S3 API address.">
        <input {...field("endpoint_url")} placeholder={endpoint} inputMode="url" />
      </Field>
      <div className={provider === "r2" ? "" : "grid gap-5 sm:grid-cols-2"}>
        <Field label="Bucket">
          <input {...field("bucket")} placeholder="my-uploads" />
        </Field>
        {provider !== "r2" && (
          <Field label="Region">
            <input {...field("region")} placeholder={region} />
          </Field>
        )}
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Access key ID" hint={saved.connected ? `Saved, ending ${saved.key_hint}. Leave both empty to keep it.` : undefined}>
          <input {...field("access_key_id")} />
        </Field>
        <Field label="Secret access key" hint="Encrypted on the server; never shown again.">
          <input {...field("secret_access_key")} type="password" autoComplete="new-password" />
        </Field>
      </div>
      <Field label="Public address" hint="Where anyone can open the bucket's files: your custom domain or the bucket's public URL.">
        <input {...field("public_base_url")} placeholder={publicUrl} inputMode="url" />
      </Field>

      <div className="flex flex-wrap items-center gap-2 border-t pt-5">
        <Button disabled={busy || !complete(form, provider, saved.connected)}>{busy ? "Testing…" : saved.connected ? "Test and save" : "Test and connect"}</Button>
        {saved.connected && (
          <Button type="button" variant="danger" disabled={busy} onClick={disconnect}>
            Disconnect
          </Button>
        )}
        <span role="status" className="text-sm text-success">
          {message}
        </span>
      </div>
      <ErrorText>{error}</ErrorText>
      <p className="text-xs text-muted-foreground">
        Testing writes one small file to the bucket, opens its public address and deletes it. Images in articles are public to anyone with
        the link. Your logo and profile photos, which the chat shows everyone, stay in our storage.
      </p>
    </form>
  );
}
