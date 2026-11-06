import { describe, expect, it } from "vitest";
import { a5NoteFrom, a5NoteToText } from "../types/insight";
import type { Insight } from "../types/insight";

function insightWith(note: unknown): Insight {
  return {
    id: "i1",
    kind: "pre_consultation",
    content: "",
    sources: { a5_note: note },
    verification_id: null,
    provider_used: null,
    created_at: "2026-11-07T00:00:00",
  };
}

describe("a5NoteFrom", () => {
  it("extracts a valid payload with lists sanitized", () => {
    const note = a5NoteFrom(
      insightWith({
        date: "2026-11-10",
        member_name: "Asha",
        chronic_conditions: ["T2D", 42, null],
        chief_complaints: ["burning feet"],
        to_discuss: ["HbA1c control"],
        current_medications: ["Metformin 500 mg"],
      }),
    );
    expect(note).not.toBeNull();
    expect(note?.chronic_conditions).toEqual(["T2D"]);
    expect(note?.to_discuss).toEqual(["HbA1c control"]);
  });

  it("returns null for missing/invalid payloads (prose-era insights)", () => {
    expect(a5NoteFrom(insightWith("narrative text"))).toBeNull();
    expect(a5NoteFrom(insightWith({ member_name: "Asha" }))).toBeNull();
    expect(a5NoteFrom(null)).toBeNull();
  });
});

describe("a5NoteToText (WhatsApp export)", () => {
  it("renders the A5 sheet layout in plain text", () => {
    const text = a5NoteToText({
      date: "2026-11-10",
      member_name: "Asha",
      chronic_conditions: ["T2D", "HTN"],
      chief_complaints: ["burning feet", "palpitations"],
      to_discuss: ["HbA1c control", "Switch Met XL"],
      current_medications: ["Metformin 500 mg"],
    });
    expect(text).toBe(
      [
        "Date: 2026-11-10",
        "Member Name: Asha",
        "Chronic: T2D, HTN",
        "C/c: burning feet; palpitations",
        "",
        "To discuss with doctor",
        "1. HbA1c control",
        "2. Switch Met XL",
        "",
        "Current medications: Metformin 500 mg",
      ].join("\n"),
    );
  });

  it("omits empty sections", () => {
    const text = a5NoteToText({
      date: "2026-11-10",
      member_name: "Asha",
      chronic_conditions: [],
      chief_complaints: [],
      to_discuss: ["General review"],
      current_medications: [],
    });
    expect(text).toBe(
      ["Date: 2026-11-10", "Member Name: Asha", "", "To discuss with doctor", "1. General review"].join(
        "\n",
      ),
    );
  });
});
