"use client";

import { useCallback, useState } from "react";
import { ColorPicker } from "@/components/color-picker";
import { ImageUpload } from "@/components/image-upload";
import { Select } from "@/components/select";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { WidgetPreview } from "@/components/widget-preview";
import { useWorkspace } from "@/components/workspace-context";
import { api, type ColorMode, type Member, type WidgetBackground, type Workspace } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";
import { useSaveWorkspace } from "@/lib/use-save-workspace";

const BACKGROUNDS: { value: WidgetBackground; label: string }[] = [
  { value: "plain", label: "Plain" },
  { value: "dots", label: "Dots" },
  { value: "grid", label: "Grid" },
  { value: "stripes", label: "Stripes" },
  { value: "bubbles", label: "Bubbles" },
];

const MODES: { value: ColorMode; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "auto", label: "Match visitor's device" },
];

export default function AppearancePage() {
  const { workspace, reload } = useWorkspace();
  const owner = workspace.role === "owner";
  const { save, message, error } = useSaveWorkspace();
  const [form, setForm] = useState({
    greeting: workspace.greeting,
    color: workspace.color,
    background: workspace.background,
    color_mode: workspace.color_mode,
  });
  const { data: members } = usePoll(useCallback(() => api<Member[]>(`/workspaces/${workspace.id}/members`), [workspace.id]), 3600000);
  // As the server picks them for the widget: with a photo, owners first, at most three.
  const team = (members ?? [])
    .filter((member) => member.photo_url)
    .sort((a, b) => Number(b.role === "owner") - Number(a.role === "owner"))
    .slice(0, 3)
    .map(({ name, photo_url }) => ({ name, photo_url }));

  return (
    <>
      <PageHeader title="Appearance" description="How the chat widget looks and greets visitors." />
      <div className="mx-auto flex max-w-5xl flex-wrap items-start gap-8 p-8">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save(form);
          }}
          className="min-w-72 flex-1 space-y-4 rounded-lg border bg-surface p-6 shadow-sm"
        >
          <ImageUpload<Workspace>
            label="Logo"
            hint="Shown at the top of the widget. A square image works best; PNG, JPEG or WebP, up to 5 MB."
            path={`/workspaces/${workspace.id}/logo`}
            src={workspace.logo_url}
            fallback={workspace.name}
            disabled={!owner}
            enabled={workspace.uploads_enabled}
            onDone={reload}
          />
          <Field label="Greeting" hint="The first message visitors see.">
            <input className={inputClass} disabled={!owner} value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })} />
          </Field>
          <ColorPicker value={form.color} saved={workspace.color} disabled={!owner} onChange={(color) => setForm({ ...form, color })} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Background" hint="The pattern behind the messages.">
              <Select label="Background" value={form.background} options={BACKGROUNDS} disabled={!owner} onChange={(background) => setForm({ ...form, background })} />
            </Field>
            <Field label="Color mode" hint="For dark sites, or visitors who prefer dark.">
              <Select label="Color mode" value={form.color_mode} options={MODES} disabled={!owner} onChange={(color_mode) => setForm({ ...form, color_mode })} />
            </Field>
          </div>
          <ErrorText>{error}</ErrorText>
          {owner && (
            <div className="flex items-center gap-3">
              <Button>Save</Button>
              <span className="text-sm text-success">{message}</span>
            </div>
          )}
        </form>
        <WidgetPreview look={{ ...form, name: workspace.name, logo_url: workspace.logo_url, team }} />
      </div>
    </>
  );
}
