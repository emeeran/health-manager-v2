import { apiRequest, ApiError } from "../api-client";
import type { Insight, InsightKind } from "../types/insight";
import {
  consumeSse,
  postStream,
  STREAM_IDLE_TIMEOUT_MS,
  streamIdleGuard,
  toApiError,
} from "./sse";

/**
 * URL path segment for a report kind's stream endpoint. The two original
 * kinds have contracted slugs; later kinds derive theirs from the kind name.
 */
export function reportKindPath(kind: InsightKind): string {
  if (kind === "smart_report") return "smart";
  return kind.replace(/_/g, "-");
}

export function getLatestInsight(
  memberId: string,
  kind: InsightKind,
): Promise<Insight | null> {
  return apiRequest<Insight | null>(
    `/members/${encodeURIComponent(memberId)}/reports/latest?kind=${encodeURIComponent(kind)}`,
  );
}

export interface StreamInsightOptions {
  signal?: AbortSignal;
}

export interface InsightStreamEvent {
  stage: "stats" | "narrating" | "verifying" | "complete" | "error";
  message?: string;
  delta?: string;
  report?: Insight;
}

/**
 * Generate an insight of `kind` and consume the SSE response incrementally.
 * Resolves with the `complete` event's saved insight; rejects on stream,
 * HTTP, or `error`-stage failures.
 *
 * `apiRequest` cannot stream, so this performs the fetch directly — keeping
 * the same cookie auth and a single refresh-and-retry on 401 (same shape as
 * `streamReport`).
 */
export async function streamInsight(
  memberId: string,
  kind: InsightKind,
  onEvent: (event: InsightStreamEvent) => void,
  { signal }: StreamInsightOptions = {},
): Promise<Insight> {
  const path = `/members/${encodeURIComponent(memberId)}/reports/${reportKindPath(kind)}/stream`;
  // Idle-based, not absolute: narrate + audit on a local model can
  // legitimately outlast any fixed budget, and the backend heartbeats
  // keep healthy streams delivering bytes throughout.
  const guard = streamIdleGuard(STREAM_IDLE_TIMEOUT_MS, signal);
  try {
    const response = await postStream(path, { signal: guard.signal });
    if (!response.ok) {
      throw await toApiError(response);
    }

    let report: Insight | null = null;
    await consumeSse<InsightStreamEvent>(
      response,
      (event) => {
        if (event.stage === "complete" && event.report) report = event.report;
        if (event.stage === "error") {
          throw new ApiError(0, undefined, event.message ?? "Report failed.");
        }
        onEvent(event);
      },
      "Empty report stream.",
      undefined,
      guard.bump,
    );

    if (!report) {
      throw new ApiError(0, undefined, "Report stream ended without a report.");
    }
    return report;
  } finally {
    guard.done();
  }
}

/** Past insights for a member, newest first; optional kind filter. */
export function listInsights(
  memberId: string,
  kind?: InsightKind,
): Promise<Insight[]> {
  const query = new URLSearchParams({ member_id: memberId });
  if (kind) query.set("kind", kind);
  return apiRequest<Insight[]>(`/insights?${query.toString()}`);
}
