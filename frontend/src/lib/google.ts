/** A full page load, not a request: the server sends the browser on to Google. */
export const GOOGLE_START = "/api/v1/auth/google/start";

/** Why a login with Google didn't work (backend/apps/accounts/google.py). */
const REASONS: Record<string, string> = {
  google_cancelled: "You didn't finish logging in with Google.",
  google_expired: "That took too long, or cookies are blocked. Try again.",
  google_failed: "Logging in with Google didn't work. Try again in a minute.",
  google_unverified: "Google hasn't verified this email address yet.",
  google_use_password: "An account with this email already exists. Log in with its password.",
  signup_closed: "Sign-up is closed on this installation. Ask its owner for an account.",
};

/** What to say about `?error=`. Only our own words: anyone can write a link with their own. */
export function loginError(search: string): string {
  const reason = new URLSearchParams(search).get("error");
  if (!reason) return "";
  return Object.hasOwn(REASONS, reason) ? REASONS[reason] : REASONS.google_failed;
}
