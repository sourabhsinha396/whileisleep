import { headers } from "next/headers";

/** The address this installation is reached under: there is no setting for it here. */
export async function siteOrigin(): Promise<string> {
  const sent = await headers();
  const proto = sent.get("x-forwarded-proto")?.split(",")[0].trim() || "http";
  return `${proto}://${sent.get("host")}`;
}
