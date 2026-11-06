/**
 * Shared SSE plumbing for the streaming endpoints: cookie-auth POST with a
 * single refresh-and-retry on 401, Response → ApiError conversion, and
 * blank-line-delimited SSE block parsing (`:`-prefixed lines are heartbeats
 * and ignored). `apiRequest` cannot stream, so the stream consumers fetch
 * directly through `postStream`.
 */

import { ApiError } from "../api-client";
import { refresh } from "./auth";

/** Local LLMs can be slow; heartbeats keep the connection alive meanwhile. */
export const STREAM_TIMEOUT_MS = 10 * 60_000;

/**
 * Absolute timeouts kill legitimate generations — narrate + audit on a
 * local model can outrun any fixed budget. The backend heartbeats every
 * 15s while a stream is healthy, so silence is the real death signal:
 * allow a few missed beats before declaring the stream dead.
 */
export const STREAM_IDLE_TIMEOUT_MS = 60_000;

/** Abort signal that fires only when the stream goes quiet: every
 * `bump()` (one per received chunk) re-arms the timer, so a stream that
 * keeps delivering — however slowly — never trips it. `external` (e.g.
 * page-unmount cancellation) aborts the guard immediately; `done()`
 * disarms the timer once the stream completes. */
export interface StreamIdleGuard {
  signal: AbortSignal;
  bump: () => void;
  done: () => void;
}

export function streamIdleGuard(
  idleMs: number,
  external?: AbortSignal,
): StreamIdleGuard {
  const controller = new AbortController();
  const abort = () =>
    controller.abort(new DOMException("Idle timeout", "TimeoutError"));
  let timer: ReturnType<typeof setTimeout> | undefined;
  const arm = () => {
    timer = setTimeout(abort, idleMs);
  };
  arm();
  external?.addEventListener("abort", abort, { once: true });
  return {
    signal: external
      ? AbortSignal.any([controller.signal, external])
      : controller.signal,
    bump: () => {
      if (controller.signal.aborted || external?.aborted) return;
      clearTimeout(timer);
      arm();
    },
    done: () => clearTimeout(timer),
  };
}

/** Extraction pipelines (read → LLM extract → verify) legitimately run
 * longer than a chat reply on local models, so they get their own budget. */
export const EXTRACTION_TIMEOUT_MS = 30 * 60_000;

/**
 * WebKitGTK reports every signal-aborted fetch as a bare AbortError
 * ("Fetch is aborted") rather than the spec's TimeoutError — translate it
 * into something a family member can act on.
 */
export function isStreamAbort(error: unknown): boolean {
  const name = (error as { name?: unknown } | null)?.name;
  return name === "AbortError" || name === "TimeoutError";
}

export async function postStream(
  path: string,
  init: { body?: BodyInit; signal?: AbortSignal } = {},
): Promise<Response> {
  const headers: Record<string, string> =
    typeof init.body === "string" ? { "Content-Type": "application/json" } : {};
  const send = (): Promise<Response> =>
    fetch(`/api/v1${path}`, {
      method: "POST",
      credentials: "include",
      headers,
      body: init.body,
      signal: init.signal,
    });
  let response: Response;
  try {
    response = await send();
  } catch (error) {
    if (isStreamAbort(error)) {
      throw new ApiError(0, undefined, "Stream timed out or was cancelled.");
    }
    throw error;
  }
  if (response.status === 401 && (await refresh().catch(() => false))) {
    response = await send();
  }
  return response;
}

export async function toApiError(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }
  return new ApiError(response.status, detail);
}

/** Parse one SSE block into an event, or null for heartbeats / bad payloads. */
export function parseEventBlock<T>(block: string): T | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart())
    .join("\n");
  if (!data) return null;
  try {
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}

/** Read the SSE body to completion, invoking `onEvent` per parsed event.
 * `abortMessage` replaces the raw browser abort error ("Fetch is aborted")
 * when the stream's timeout/cancel signal fires mid-read. `onActivity`
 * fires per received chunk — heartbeats included — so callers can drive
 * an idle-based stream guard. */
export async function consumeSse<T>(
  response: Response,
  onEvent: (event: T) => void,
  emptyMessage: string,
  abortMessage = "Stream timed out or was cancelled.",
  onActivity?: () => void,
): Promise<void> {
  if (!response.body) {
    throw new ApiError(0, undefined, emptyMessage);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      onActivity?.();
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const event = parseEventBlock<T>(block);
        if (event) onEvent(event);
      }
    }
    buffer += decoder.decode();
    const tail = parseEventBlock<T>(buffer);
    if (tail) onEvent(tail);
  } catch (error) {
    // Callers that cancel deliberately check their own signal.aborted and
    // stay silent — this translation is only for timeouts hitting the user.
    if (isStreamAbort(error)) {
      throw new ApiError(0, undefined, abortMessage);
    }
    throw error;
  }
}
