import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { consumeSse, streamIdleGuard } from "../sse";

function sseBody(events: unknown[]): ReadableStream<Uint8Array> {
  const payload = events
    .map((e) => `data: ${JSON.stringify(e)}\n\n`)
    .join("");
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(payload));
      controller.close();
    },
  });
}

describe("streamIdleGuard", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("aborts when nothing arrives within the idle window", async () => {
    const guard = streamIdleGuard(1000);
    const promise = vi.waitUntil(() => guard.signal.aborted);
    vi.advanceTimersByTime(1000);
    await promise;
    expect(guard.signal.aborted).toBe(true);
    guard.done();
  });

  it("stays alive while bumps keep arriving, then aborts when they stop", async () => {
    const guard = streamIdleGuard(1000);
    for (let t = 0; t < 5; t++) {
      vi.advanceTimersByTime(900);
      guard.bump();
    }
    expect(guard.signal.aborted).toBe(false);
    vi.advanceTimersByTime(1000);
    await vi.waitUntil(() => guard.signal.aborted);
    guard.done();
  });

  it("done() disarms the timer without aborting", () => {
    const guard = streamIdleGuard(1000);
    guard.done();
    vi.advanceTimersByTime(10_000);
    expect(guard.signal.aborted).toBe(false);
  });

  it("aborts immediately when the external signal fires", async () => {
    const external = new AbortController();
    const guard = streamIdleGuard(60_000, external.signal);
    external.abort();
    await vi.waitUntil(() => guard.signal.aborted);
    guard.done();
  });
});

describe("consumeSse activity reporting", () => {
  it("calls onActivity once per received chunk", async () => {
    const onActivity = vi.fn();
    await consumeSse<{ stage: string; message?: string }>(
      { body: sseBody([
        { stage: "stats", message: "gathering" },
        { stage: "complete" },
      ]) } as unknown as Response,
      () => {},
      "empty",
      undefined,
      onActivity,
    );
    expect(onActivity).toHaveBeenCalledTimes(1);
  });
});
