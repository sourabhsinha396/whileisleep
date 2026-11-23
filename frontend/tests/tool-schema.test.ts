import { describe, expect, it } from "vitest";
import { rowsToSchema, schemaToRows, urlPlaceholders } from "@/lib/tool-schema";

describe("tool input schema", () => {
  it("round-trips rows through JSON Schema", () => {
    const rows = [
      { name: "q", type: "string" as const, description: "Search words", required: true },
      { name: "limit", type: "integer" as const, description: "", required: false },
    ];
    const schema = rowsToSchema(rows);
    expect(schema).toEqual({
      type: "object",
      properties: { q: { type: "string", description: "Search words" }, limit: { type: "integer" } },
      required: ["q"],
    });
    expect(schemaToRows(schema)).toEqual(rows);
  });

  it("skips unnamed rows and unknown types", () => {
    expect(rowsToSchema([{ name: " ", type: "string", description: "", required: true }])).toEqual({ type: "object", properties: {} });
    expect(schemaToRows({ type: "object", properties: { x: { type: "array" } } })[0].type).toBe("string");
  });

  it("finds url placeholders but not visitor ones", () => {
    expect(urlPlaceholders("https://a.example.com/exams/{code}?email={visitor.email}")).toEqual(["code"]);
  });
});
