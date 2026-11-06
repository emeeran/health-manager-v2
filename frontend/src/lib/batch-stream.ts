/**
 * Pure helpers for the streaming batch extraction flow
 * (`POST /extract/batch/stream`). Kept separate from the React component so
 * the event-accumulation logic is unit-testable with synthetic SSE feeds.
 *
 * The backend processes files sequentially and creates a record per file:
 * - `file_start` / `complete` / `error` events carry the file's 0-based
 *   `index`, so results land in a pre-sized array at their upload-order slot
 *   and the progress list stays stable.
 * - Records are persisted server-side; `complete` carries `record_id`.
 */

import { parseEventBlock } from "./api/sse";

export interface BatchExtractionResult {
  record_id: string | null;
  content_hash?: string | null;
  clinical_data?: Record<string, unknown> | null;
  summary?: string | null;
  provider_used?: string | null;
}

export type BatchFileStatus = "pending" | "extracting" | "complete" | "error";

export interface BatchFileItem {
  filename: string;
  status: BatchFileStatus;
  error?: string | null;
  result?: BatchExtractionResult | null;
}

export interface BatchStreamEvent {
  stage?: string;
  index?: number;
  total?: number;
  filename?: string;
  message?: string;
  result?: BatchExtractionResult;
}

/** Pre-sized to the total file count; all slots start `pending`. */
export function createBatchItems(
  total: number,
  filenames: string[],
): BatchFileItem[] {
  return Array.from({ length: total }, (_, index) => ({
    filename: filenames[index] ?? `file ${index + 1}`,
    status: "pending" as const,
  }));
}

/**
 * Fold a streaming event into the item list. Idempotent for late duplicates:
 * a slot's terminal state (`complete`/`error`) is never overwritten.
 */
export function applyBatchStreamEvent(
  items: BatchFileItem[],
  event: BatchStreamEvent,
): BatchFileItem[] {
  if (
    typeof event.index !== "number" ||
    event.index < 0 ||
    event.index >= items.length
  ) {
    return items;
  }
  const index = event.index;
  const current = items[index];
  const next = [...items];

  if (event.stage === "file_start") {
    if (current.status === "pending") {
      next[index] = {
        ...current,
        status: "extracting",
        filename: event.filename || current.filename,
      };
    }
    return next;
  }

  if (event.stage === "complete") {
    next[index] = {
      ...current,
      status: "complete",
      filename: event.filename || current.filename,
      result: event.result ?? null,
      error: null,
    };
    return next;
  }

  if (event.stage === "error" && current.status !== "complete") {
    next[index] = {
      ...current,
      status: "error",
      filename: event.filename || current.filename,
      error: event.message ?? "Extraction failed",
    };
    return next;
  }

  return items;
}

export function countBatchCompleted(items: BatchFileItem[]): number {
  return items.filter(
    (item) => item.status === "complete" || item.status === "error",
  ).length;
}

/**
 * Fill slots that never received a terminal event (aborted stream / missed
 * event) with error items so callers never observe a pending leftover.
 */
export function finalizeBatchItems(
  items: BatchFileItem[],
  fallbackNames: string[],
): BatchFileItem[] {
  return items.map((item, index) =>
    item.status === "complete" || item.status === "error"
      ? item
      : {
          ...item,
          status: "error" as const,
          filename: fallbackNames[index] ?? item.filename,
          error: "Extraction incomplete",
        },
  );
}

/**
 * Parse one SSE block (blank-line-delimited) into its `data:` payload.
 * `:`-prefixed keepalive comment lines yield null; malformed JSON yields null.
 */
export function parseSseBlock(block: string): BatchStreamEvent | null {
  return parseEventBlock<BatchStreamEvent>(block);
}
