/** Who runs this installation, for the contact and legal pages. */
export interface Operator {
  name: string;
  email: string;
  address: string;
  /** Whose law the terms follow, e.g. "India". Empty: the terms don't say. */
  jurisdiction: string;
}

/**
 * From the server's environment, read while it runs. Null when nobody said who runs this one: anyone can host
 * whileisleep, and must not publish someone else's legal pages. Development shows stand-ins instead.
 */
export function operator(): Operator | null {
  const name = process.env.COMPANY_NAME?.trim() ?? "";
  const email = process.env.COMPANY_EMAIL?.trim() ?? "";
  const address = process.env.COMPANY_ADDRESS?.trim() ?? "";
  const jurisdiction = process.env.COMPANY_JURISDICTION?.trim() ?? "";
  if (name && email) return { name, email, address, jurisdiction };
  if (process.env.NODE_ENV === "development") {
    return { name: "Example Company", email: "hello@example.com", address: "Example address", jurisdiction: "" };
  }
  return null;
}
