import { apiRequest, ApiError } from "../api-client";
import type { ExtractEvent, ExtractionResult, Verification } from "../types/ai";
import {
  consumeSse,
  EXTRACTION_TIMEOUT_MS,
  postStream,
  toApiError,
} from "./sse";

export interface StreamExtractOptions {
  signal?: AbortSignal;
  /** Link the extraction's verification to this record (provenance). */
  recordId?: string;
}

/**
 * Upload a document for AI extraction and consume the SSE response
 * incrementally, invoking `onEvent` per parsed event. Resolves with the
 * `complete` event's result; rejects on stream, HTTP, or `error`-stage
 * failures.
 *
 * `apiRequest` cannot stream, so this performs the fetch directly — keeping
 * the same cookie auth and a single refresh-and-retry on 401.
 */
export async function streamExtract(
  memberId: string,
  file: File,
  onEvent: (event: ExtractEvent) => void,
  { signal, recordId }: StreamExtractOptions = {},
): Promise<ExtractionResult> {
  const form = new FormData();
  form.append("file", file);
  if (recordId) form.append("record_id", recordId);

  const path = `/members/${encodeURIComponent(memberId)}/records/extract/stream`;
  const timeout = AbortSignal.timeout(EXTRACTION_TIMEOUT_MS);

  const response = await postStream(path, {
    body: form,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }

  let result: ExtractionResult | null = null;
  await consumeSse<ExtractEvent>(
    response,
    (event) => {
      if (event.stage === "complete") result = event.result;
      if (event.stage === "error") {
        throw new ApiError(0, undefined, event.message);
      }
      onEvent(event);
    },
    "Empty extraction stream.",
    "AI extraction timed out after 30 minutes — the model was too slow. " +
      "Try again, or switch to a faster model in Settings → AI providers.",
  );

  if (!result) {
    throw new ApiError(
      0,
      undefined,
      "Extraction stream ended without a result.",
    );
  }
  return result;
}

export function getVerification(verificationId: string): Promise<Verification> {
  return apiRequest<Verification>(
    `/verifications/${encodeURIComponent(verificationId)}`,
  );
}
