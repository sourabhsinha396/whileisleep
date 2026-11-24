"use client";

import { useState } from "react";
import { OrganizationOnly } from "@/components/organization-only";
import { Button, Field, inputClass, PageHeader } from "@/components/ui";
import { api, type Organization } from "@/lib/api";

export default function OrganizationPage() {
  return (
    <>
      <PageHeader title="Organization" description="The organization your workspaces belong to." />
      <OrganizationOnly>{(org, setOrg) => <NameForm key={org.id} org={org} onSaved={setOrg} />}</OrganizationOnly>
    </>
  );
}

function NameForm({ org, onSaved }: { org: Organization; onSaved: (org: Organization) => void }) {
  const [name, setName] = useState(org.name);
  const [saved, setSaved] = useState(false);
  return (
    <form
      className="space-y-3 rounded-lg border bg-surface p-6 shadow-sm"
      onSubmit={async (e) => {
        e.preventDefault();
        onSaved(await api<Organization>("/organization", { method: "PATCH", body: { name } }));
        setSaved(true);
      }}
    >
      <Field label="Name">
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="flex items-center gap-3">
        <Button>Save</Button>
        {saved && <span className="text-sm text-success">Saved.</span>}
      </div>
    </form>
  );
}
