import { describe, expect, it } from "vitest";
import { counterText, errorMessage } from "@/widget/limits";

describe("counterText", () => {
  it("stays hidden until 80% of the limit", () => {
    expect(counterText(399, 500)).toBe("");
    expect(counterText(400, 500)).toBe("400/500");
    expect(counterText(500, 500)).toBe("500/500");
  });
});

describe("errorMessage", () => {
  it("uses a plain detail string", () => {
    expect(errorMessage({ detail: "You already sent this form." }, 400)).toBe("You already sent this form.");
  });

  it("explains a too-long message instead of showing the raw validation list", () => {
    const detail = [{ type: "string_too_long", loc: ["body", "payload", "body"], msg: "String should have at most 500 characters", ctx: { max_length: 500 } }];
    expect(errorMessage({ detail }, 422)).toBe("That message is too long. Please keep it under 500 characters.");
  });

  it("falls back to the first validation message, then the status", () => {
    expect(errorMessage({ detail: [{ msg: "Bad intent" }] }, 422)).toBe("Bad intent");
    expect(errorMessage({}, 503)).toBe("Something went wrong on our side. Please try again.");
    expect(errorMessage(null, 404)).toBe("Request failed (404).");
  });
});
