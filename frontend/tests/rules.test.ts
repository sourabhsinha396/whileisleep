import { describe, expect, it } from "vitest";
import {
  type Condition,
  describeCondition,
  describeRule,
  fieldOption,
  newRow,
  opsFor,
  toGroup,
  toRow,
  toTest,
  toTree,
} from "@/lib/rules";

describe("fields", () => {
  it("finds fixed fields and keyed ones by prefix", () => {
    expect(fieldOption("message.text").kind).toBe("text");
    expect(fieldOption("contact.plan").label).toBe("Visitor attribute…");
    expect(fieldOption("message.data.exam_code").label).toBe("Button data…");
    // A fixed name wins over the prefix it also matches.
    expect(fieldOption("contact.verified").kind).toBe("boolean");
    expect(fieldOption("conversation.tags").kind).toBe("tags");
  });

  it("falls back for names it doesn't know", () => {
    expect(fieldOption("something.else")).toEqual({ id: "something.else", label: "something.else", kind: "any" });
  });

  it("offers operators that fit the field", () => {
    expect(opsFor("time.hour")).toContain("gte");
    expect(opsFor("time.hour")).not.toContain("contains");
    expect(opsFor("message.is_first")).toEqual(["equals"]);
    expect(opsFor("contact.plan")).toContain("exists");
  });
});

describe("rows and tests", () => {
  it("splits lists on new lines and commas", () => {
    expect(toTest({ field: "message.text", op: "contains_any", value: "refund\nmoney back, , chargeback " })).toEqual({
      field: "message.text",
      op: "contains_any",
      value: ["refund", "money back", "chargeback"],
    });
  });

  it("turns numbers and booleans into their own types", () => {
    expect(toTest({ field: "time.hour", op: "gte", value: "18" }).value).toBe(18);
    expect(toTest({ field: "contact.seats", op: "gt", value: "10" }).value).toBe(10);
    expect(toTest({ field: "message.is_first", op: "equals", value: "true" }).value).toBe(true);
    expect(toTest({ field: "contact.verified", op: "equals", value: "false" }).value).toBe(false);
  });

  it("keeps text as typed, trimmed", () => {
    expect(toTest({ field: "contact.plan", op: "equals", value: " pro " })).toEqual({ field: "contact.plan", op: "equals", value: "pro" });
  });

  it("sends no value for presence tests", () => {
    expect(toTest({ field: "contact.email", op: "exists", value: "ignored" })).toEqual({ field: "contact.email", op: "exists" });
  });

  it("round-trips a test through a row", () => {
    const tests = [
      { field: "message.text", op: "contains_any", value: ["refund", "money back"] },
      { field: "time.hour", op: "lt", value: 9 },
      { field: "message.is_first", op: "equals", value: true },
      { field: "contact.plan", op: "not_exists" },
    ];
    for (const test of tests) expect(toTest(toRow(test))).toEqual(test);
  });

  it("starts a new row with an operator that fits", () => {
    expect(newRow()).toEqual({ field: "message.text", op: "contains", value: "" });
    expect(newRow("message.is_first")).toEqual({ field: "message.is_first", op: "equals", value: "true" });
  });
});

describe("groups and trees", () => {
  const flat: Condition = {
    any: [
      { field: "time.hour", op: "lt", value: 9 },
      { field: "time.weekday", op: "in", value: ["sat", "sun"] },
    ],
  };

  it("shows a flat tree as rows and builds it back", () => {
    const group = toGroup(flat);
    expect(group?.match).toBe("any");
    expect(group?.rows).toHaveLength(2);
    expect(toTree(group!)).toEqual(flat);
  });

  it("leaves nested trees to the JSON editor", () => {
    expect(toGroup({ all: [flat] })).toBeNull();
    expect(toGroup({ not: { field: "contact.plan", op: "exists" } })).toBeNull();
    expect(toGroup({ field: "contact.plan", op: "exists" })).toBeNull();
  });
});

describe("describing", () => {
  it("reads like a sentence", () => {
    const tree: Condition = {
      all: [
        { field: "message.text", op: "contains_any", value: ["refund", "money back"] },
        { any: [{ field: "contact.plan", op: "equals", value: "pro" }, { field: "page.url", op: "contains", value: "/pricing" }] },
        { not: { field: "conversation.tags", op: "equals", value: "vip" } },
        { field: "message.is_first", op: "equals", value: true },
      ],
    };
    expect(describeCondition(tree)).toBe(
      "message text contains any of refund, money back and (contact.plan is pro or page url contains /pricing) and not (tags is vip) and is the first message",
    );
  });

  it("describes a whole rule", () => {
    expect(
      describeRule({
        conditions: { all: [{ field: "message.intent", op: "equals", value: "exam_request" }] },
        actions: [
          { type: "tag", value: "exam-request" },
          { type: "set_attribute", scope: "conversation", key: "topic", value: "exams" },
          { type: "handoff" },
          { type: "reply", text: "On it." },
        ],
      }),
    ).toBe("When button intent is exam_request → tag exam-request, set conversation.topic = exams, hand off, fixed reply");
  });
});
