"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { OrganizationOnly } from "@/components/organization-only";
import { Select } from "@/components/select";
import { Button, ErrorText, Field, PageHeader, Segmented } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { playAlert, type SoundName, SOUNDS } from "@/lib/alert-sound";
import { type AlertSettings, api, type Organization } from "@/lib/api";
import { unlockAudio } from "@/widget/sound";

const SOUND_OPTIONS = (Object.keys(SOUNDS) as SoundName[]).map((value) => ({ value, label: SOUNDS[value].label }));
const REPEATS = ["0", "30", "60", "120"] as const;
const REPEAT_LABELS = { "0": "Once", "30": "Every 30 seconds", "60": "Every minute", "120": "Every 2 minutes" };

export default function AlertsPage() {
  return (
    <>
      <PageHeader title="Alerts" docs="inbox" description="How the dashboard tells your team that a chat needs them, in all your workspaces." />
      <OrganizationOnly>{(org, setOrg) => <AlertsForm key={org.id} org={org} onSaved={setOrg} />}</OrganizationOnly>
    </>
  );
}

function AlertsForm({ org, onSaved }: { org: Organization; onSaved: (org: Organization) => void }) {
  const { reload } = useWorkspace();
  const [form, setForm] = useState<AlertSettings>({
    alert_sound: org.alert_sound,
    alert_volume: org.alert_volume,
    alert_on: org.alert_on,
    alert_repeat: org.alert_repeat,
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function change(part: Partial<AlertSettings>) {
    setForm({ ...form, ...part });
    setSaved(false);
  }

  function preview(settings: AlertSettings) {
    unlockAudio();
    playAlert(settings.alert_sound, settings.alert_volume);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      onSaved(await api<Organization>("/organization", { method: "PATCH", body: form }));
      setSaved(true);
      // The alerts themselves read the workspace.
      await reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form onSubmit={save} className="space-y-6 rounded-lg border bg-surface p-6 shadow-sm">
      <div>
        <span className="mb-1.5 block text-sm font-medium">Sound</span>
        <div className="flex items-center gap-2">
          <Select
            label="Sound"
            className="w-48"
            value={form.alert_sound}
            options={SOUND_OPTIONS}
            onChange={(alert_sound) => {
              change({ alert_sound });
              preview({ ...form, alert_sound });
            }}
          />
          <Button type="button" variant="secondary" onClick={() => preview(form)}>
            <Play size={14} /> Play
          </Button>
        </div>
      </div>
      <Field label={`Volume: ${form.alert_volume}%`} hint="0% is silent: only desktop alerts and the count in the tab's title.">
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={form.alert_volume}
          onChange={(e) => change({ alert_volume: Number(e.target.value) })}
          onPointerUp={() => preview(form)}
          className="block w-full max-w-sm accent-primary"
        />
      </Field>
      <div>
        <span className="mb-1.5 block text-sm font-medium">Alert about</span>
        <Segmented
          value={form.alert_on}
          onChange={(alert_on) => change({ alert_on })}
          options={[
            { value: "person", label: "Chats that need a person" },
            { value: "all", label: "Every visitor message" },
          ]}
        />
      </div>
      <div>
        <span className="mb-1.5 block text-sm font-medium">Ring</span>
        <Select
          label="Ring"
          className="w-48"
          value={String(form.alert_repeat) as (typeof REPEATS)[number]}
          options={REPEATS.map((value) => ({ value, label: REPEAT_LABELS[value] }))}
          onChange={(value) => change({ alert_repeat: Number(value) as AlertSettings["alert_repeat"] })}
        />
        <p className="mt-1.5 text-xs text-muted-foreground">Repeats until someone reads the chat, at most 20 times, and only for chats that need a person.</p>
      </div>
      <div className="flex items-center gap-3 border-t pt-5">
        <Button>Save</Button>
        {saved && <span role="status" className="text-sm text-success">Saved.</span>}
      </div>
      <ErrorText>{error}</ErrorText>
      <p className="text-xs text-muted-foreground">
        Each person can still switch sound and desktop alerts on or off for their own browser, in the menu under their name.
      </p>
    </form>
  );
}
