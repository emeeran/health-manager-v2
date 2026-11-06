import { ApiError } from "../api-client";
import type { BatchStreamEvent } from "../batch-stream";
import { consumeSse, postStream, toApiError } from "./sse";

// Multi-file AI extraction can take minutes on local models; heartbeats keep
// the connection alive meanwhile.
const BATCH_TIMEOUT_MS = 15 * 60_000;

export interface StreamBatchOptions {
  signal?: AbortSignal;
}

/**
 * Upload several documents and consume the SSE extraction stream, invoking
 * `onEvent` per parsed event (`start` / `file_complete` / `done` / `error`).
 *
 * `apiRequest` cannot stream multipart uploads, so this performs the fetch
 * directly — same cookie auth and single refresh-and-retry on 401 as
 * `streamReport`.
 */
export async function streamBatchExtract(
  memberId: string,
  files: File[],
  onEvent: (event: BatchStreamEvent) => void,
  { signal }: StreamBatchOptions = {},
): Promise<void> {
  if (files.length === 0) return;
  const timeout = AbortSignal.timeout(BATCH_TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }

  const response = await postStream(
    `/extract/batch/stream?member_id=${encodeURIComponent(memberId)}`,
    { body: form, signal: combined },
  );
  if (!response.ok) {
    throw await toApiError(response);
  }

  await consumeSse<BatchStreamEvent>(
    response,
    (event) => {
      // Per-file failures carry an index and ride through as normal events;
      // only a stream-level error (no index) aborts the batch.
      if (event.stage === "error" && typeof event.index !== "number") {
        throw new ApiError(
          0,
          undefined,
          event.message ?? "Batch extraction failed.",
        );
      }
      onEvent(event);
    },
    "Empty batch stream.",
  );
}
