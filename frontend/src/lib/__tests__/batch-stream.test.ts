import { describe, expect, it } from "vitest";
import {
  applyBatchStreamEvent,
  countBatchCompleted,
  createBatchItems,
  finalizeBatchItems,
  parseSseBlock,
} from "../batch-stream";

function items() {
  return createBatchItems(3, ["a.pdf", "b.pdf", "c.pdf"]);
}

describe("parseSseBlock", () => {
  it("parses a data payload", () => {
    expect(parseSseBlock('data: {"stage":"file_start","index":0}')).toEqual({
      stage: "file_start",
      index: 0,
    });
  });

  it("joins multi-line data payloads", () => {
    const block = 'data: {"stage":\ndata: "file_start"}';
    expect(parseSseBlock(block)).toEqual({ stage: "file_start" });
  });

  it("returns null for keepalive comments, blank blocks, and malformed JSON", () => {
    expect(parseSseBlock(": ping")).toBeNull();
    expect(parseSseBlock("")).toBeNull();
    expect(parseSseBlock("data: {broken")).toBeNull();
  });
});

describe("batch item folding", () => {
  it("marks the matching slot extracting on file_start", () => {
    const result = applyBatchStreamEvent(items(), {
      stage: "file_start",
      index: 1,
      filename: "b.pdf",
    });
    expect(result[1].status).toBe("extracting");
    expect(result[0].status).toBe("pending");
  });

  it("stores results by upload-order index regardless of completion order", () => {
    let result = items();
    result = applyBatchStreamEvent(result, {
      stage: "complete",
      index: 2,
      filename: "c.pdf",
      result: { record_id: "r2", summary: "s2" },
    });
    result = applyBatchStreamEvent(result, {
      stage: "complete",
      index: 0,
      filename: "a.pdf",
      result: { record_id: "r0" },
    });
    expect(result[2].status).toBe("complete");
    expect(result[2].result?.record_id).toBe("r2");
    expect(result[0].result?.record_id).toBe("r0");
    expect(result[1].status).toBe("pending");
    expect(countBatchCompleted(result)).toBe(2);
  });

  it("marks per-file errors without failing other slots", () => {
    const result = applyBatchStreamEvent(items(), {
      stage: "error",
      index: 1,
      filename: "b.pdf",
      message: "unsupported type",
    });
    expect(result[1].status).toBe("error");
    expect(result[1].error).toBe("unsupported type");
    expect(result[0].status).toBe("pending");
  });

  it("never overwrites a terminal slot", () => {
    let result = items();
    result = applyBatchStreamEvent(result, {
      stage: "complete",
      index: 0,
      result: { record_id: "r0" },
    });
    result = applyBatchStreamEvent(result, {
      stage: "error",
      index: 0,
      message: "late failure",
    });
    expect(result[0].status).toBe("complete");
  });

  it("ignores out-of-range indices", () => {
    const result = applyBatchStreamEvent(items(), {
      stage: "complete",
      index: 9,
      result: { record_id: "x" },
    });
    expect(result).toHaveLength(3);
    expect(countBatchCompleted(result)).toBe(0);
  });
});

describe("finalizeBatchItems", () => {
  it("fills missing slots with error items", () => {
    let result = items();
    result = applyBatchStreamEvent(result, {
      stage: "complete",
      index: 1,
      result: { record_id: "r1" },
    });
    const finalized = finalizeBatchItems(result, ["a.pdf", "b.pdf", "c.pdf"]);
    expect(finalized[1].status).toBe("complete");
    expect(finalized[0]).toMatchObject({
      status: "error",
      error: "Extraction incomplete",
    });
    expect(finalized[2]).toMatchObject({ status: "error" });
  });
});
