"use client";

import { Pencil, RotateCcw, Video } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Button, ErrorText, inputClass, Spinner } from "@/components/ui";
import { api, getToken, type User } from "@/lib/api";

// Only a superuser ever loads the editor.
const DocEditor = dynamic(() => import("@/components/docs/doc-editor").then((module) => module.DocEditor), { loading: () => <Spinner /> });

/** A page's video and text (`children`). A superuser can change both. */
export function DocBody({ slug, body, edited, youtubeId, children }: { slug: string; body: string; edited: boolean; youtubeId: string; children: React.ReactNode }) {
  const router = useRouter();
  const [superuser, setSuperuser] = useState(false);
  const [mode, setMode] = useState<"" | "text" | "video">("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    let gone = false;
    // An old token is no reason to bother a reader.
    api<User>("/auth/me").then((me) => !gone && setSuperuser(me.is_superuser), () => {});
    return () => {
      gone = true;
    };
  }, []);

  function open(next: typeof mode) {
    setError("");
    setMode(next);
  }

  async function save(change: { body?: string; video_link?: string }) {
    setBusy(true);
    setError("");
    try {
      await api(`/docs/${slug}`, { method: "PATCH", body: change });
      setMode("");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function restore() {
    if (window.confirm("Bring back the original text of this page? Your edited text is deleted.")) save({ body: "" });
  }

  return (
    <>
      {superuser && mode === "" && (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => open("text")}>
            <Pencil size={14} /> Edit text
          </Button>
          <Button size="sm" variant="secondary" onClick={() => open("video")}>
            <Video size={14} /> {youtubeId ? "Change video" : "Add video"}
          </Button>
          {edited && (
            <>
              <Button size="sm" variant="ghost" disabled={busy} onClick={restore}>
                <RotateCcw size={14} /> Restore original
              </Button>
              <Badge>Edited</Badge>
            </>
          )}
        </div>
      )}
      {mode === "video" && <VideoForm youtubeId={youtubeId} busy={busy} onSave={(video_link) => save({ video_link })} onCancel={() => open("")} />}
      {superuser && <ErrorText>{error}</ErrorText>}
      {mode === "text" ? <DocEditor value={body} busy={busy} onSave={(text) => save({ body: text })} onCancel={() => open("")} /> : children}
    </>
  );
}

function VideoForm({ youtubeId, busy, onSave, onCancel }: { youtubeId: string; busy: boolean; onSave: (link: string) => void; onCancel: () => void }) {
  const [link, setLink] = useState(youtubeId ? `https://youtu.be/${youtubeId}` : "");
  return (
    <form
      className="mt-5 flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(link);
      }}
    >
      <input
        autoFocus
        className={`${inputClass} min-w-60 flex-1`}
        placeholder="https://youtu.be/…"
        aria-label="YouTube link"
        value={link}
        onChange={(e) => setLink(e.target.value)}
      />
      <Button disabled={busy || !link.trim()}>Save</Button>
      {youtubeId && (
        <Button type="button" variant="danger" disabled={busy} onClick={() => onSave("")}>
          Remove
        </Button>
      )}
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}
