import { describe, expect, it } from "vitest";
import { mergeDirection, reasonLabel } from "../types/hygiene";
import type { DuplicatePair } from "../types/hygiene";

const pair: DuplicatePair = {
  primary_id: "primary-1",
  duplicate_id: "duplicate-1",
  reason: "identical_content,same_attachment",
  score: 3,
};

describe("mergeDirection", () => {
  it("merges the duplicate into the recommended primary", () => {
    expect(mergeDirection(pair, pair.primary_id)).toEqual({
      duplicateId: "duplicate-1",
      primaryId: "primary-1",
    });
  });

  it("supports overriding the keeper to the duplicate", () => {
    expect(mergeDirection(pair, pair.duplicate_id)).toEqual({
      duplicateId: "primary-1",
      primaryId: "duplicate-1",
    });
  });

  it("rejects a keeper outside the pair", () => {
    expect(mergeDirection(pair, "other-record")).toBeNull();
  });
});

describe("reasonLabel", () => {
  it("translates backend reason tokens", () => {
    expect(reasonLabel(pair.reason)).toBe(
      "Identical content · Same attachment",
    );
  });

  it("passes through unknown tokens", () => {
    expect(reasonLabel("custom_reason")).toBe("custom_reason");
  });
});
