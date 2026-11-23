/** Message length counter and readable API errors for the widget. */

/** Shown once the visitor is near the limit, e.g. "420/500"; empty before that. */
export function counterText(length: number, max: number): string {
  return length >= max * 0.8 ? `${length}/${max}` : "";
}

/** A sentence for the visitor from an API error body (Django Ninja sends a string, or a list on 422). */
export function errorMessage(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { type?: string; ctx?: { max_length?: number }; msg?: string };
    if (first.type === "string_too_long") {
      return `That message is too long. Please keep it under ${first.ctx?.max_length ?? 500} characters.`;
    }
    if (first.msg) return first.msg;
  }
  return status >= 500 ? "Something went wrong on our side. Please try again." : `Request failed (${status}).`;
}
