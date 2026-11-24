"use client";

import { useRef, useState } from "react";
import { Avatar, Button, ErrorText } from "@/components/ui";
import { api, upload } from "@/lib/api";
import { IMAGE_TYPES, imageProblem } from "@/lib/image-file";

/** One image that is saved as soon as it is picked: a logo, a photo. */
export function ImageUpload<T>({
  label,
  hint,
  path,
  src,
  fallback,
  disabled = false,
  enabled,
  onDone,
}: {
  label: string;
  hint: string;
  /** POST a file here to set the image, DELETE to remove it. */
  path: string;
  src: string;
  /** Whose initials show without an image. */
  fallback: string;
  disabled?: boolean;
  /** Whether the server can store images. */
  enabled: boolean;
  onDone: (saved: T) => unknown;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(request: () => Promise<T>) {
    setBusy(true);
    setError("");
    try {
      await onDone(await request());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(file: File | undefined) {
    if (!file) return;
    const problem = imageProblem(file);
    if (problem) setError(problem);
    else run(() => upload<T>(path, file));
  }

  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <div className="flex items-center gap-4">
        <Avatar name={fallback} src={src} size={56} />
        <div className="space-y-2">
          <div className="flex gap-2">
            {/* type="button": this can sit inside a form. */}
            <Button type="button" variant="secondary" disabled={disabled || busy || !enabled} onClick={() => input.current?.click()}>
              {busy ? "Saving…" : src ? "Change" : "Upload"}
            </Button>
            {src && (
              <Button type="button" variant="danger" disabled={disabled || busy} onClick={() => run(() => api<T>(path, { method: "DELETE" }))}>
                Remove
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">{enabled ? hint : "Image uploads are off: file storage isn't set up on this server."}</p>
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept={IMAGE_TYPES.join(",")}
        aria-label={`${label} file`}
        className="hidden"
        onChange={(e) => {
          pick(e.target.files?.[0]);
          // So picking the same file again counts as a change.
          e.target.value = "";
        }}
      />
      <ErrorText>{error}</ErrorText>
    </div>
  );
}
