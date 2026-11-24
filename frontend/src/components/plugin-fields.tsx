"use client";

import { Select } from "@/components/select";
import { Field, inputClass } from "@/components/ui";
import type { PluginField } from "@/lib/api";
import { iconUrl, toggled, type Values } from "@/lib/integrations";

export function PluginIcon({ svg, size = 28 }: { svg: string; size?: number }) {
  // An inline SVG: there is nothing for next/image to make smaller.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={iconUrl(svg)} alt="" width={size} height={size} className="shrink-0" />;
}

interface FieldsProps {
  fields: PluginField[];
  values: Values;
  onChange: (values: Values) => void;
  /** Secrets that are saved already. */
  secrets?: string[];
  /** Tells apart the radio buttons of two forms on one page. */
  id?: string;
}

/** The fields a plugin asked for (backend/apps/integrations/plugin.py). */
export function PluginFields({ fields, values, onChange, secrets = [], id = "" }: FieldsProps) {
  return (
    <>
      {fields.map((field) => (
        <PluginInput
          key={field.name}
          id={`${id}${field.name}`}
          field={field}
          saved={secrets.includes(field.name)}
          value={values[field.name] ?? ""}
          onChange={(value) => onChange({ ...values, [field.name]: value })}
        />
      ))}
    </>
  );
}

interface InputProps {
  id: string;
  field: PluginField;
  value: string;
  saved: boolean;
  onChange: (value: string) => void;
}

function PluginInput({ id, field, value, saved, onChange }: InputProps) {
  if (field.kind === "choice" || field.kind === "choices") {
    const many = field.kind === "choices";
    const chosen = value.split(",");
    return (
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">{field.label}</legend>
        <div className="space-y-1.5">
          {field.options.map((option) => (
            <label key={option.value} className="flex items-center gap-2 text-sm">
              <input
                type={many ? "checkbox" : "radio"}
                name={id}
                className="accent-primary"
                checked={many ? chosen.includes(option.value) : value === option.value}
                onChange={() => onChange(many ? toggled(field, value, option.value) : option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
        {field.help && <p className="mt-1.5 text-xs text-muted-foreground">{field.help}</p>}
      </fieldset>
    );
  }
  if (field.kind === "select") {
    const known = field.options.some((option) => option.value === value);
    // What was chosen before may be gone, or not chosen yet.
    const options = known ? field.options : [{ value, label: value ? "No longer there: pick another" : "Choose one" }, ...field.options];
    return (
      <Field label={field.label} hint={field.help}>
        <Select value={value} options={options} onChange={onChange} />
      </Field>
    );
  }
  const secret = field.kind === "secret";
  return (
    <Field label={field.label} hint={saved ? "Saved, and not shown again. Leave empty to keep it." : field.help}>
      <input
        className={inputClass}
        type={secret ? "password" : "text"}
        autoComplete={secret ? "new-password" : "off"}
        spellCheck={false}
        placeholder={field.placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}
