import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { closeTopOverlay, pushEscClose } from "../esc-stack";

describe("esc-stack", () => {
  let unregisterFns: Array<() => void>;

  beforeEach(() => {
    unregisterFns = [];
  });

  // The stack is module-level shared state — drain anything a case left.
  afterEach(() => {
    for (const unregister of unregisterFns) unregister();
  });

  function push(fn: () => void) {
    const unregister = pushEscClose(fn);
    unregisterFns.push(unregister);
    return unregister;
  }

  it("closes the topmost overlay first (LIFO)", () => {
    const inner = vi.fn();
    const outer = vi.fn();
    push(inner);
    push(outer);

    expect(closeTopOverlay()).toBe(true);
    expect(outer).toHaveBeenCalledTimes(1);
    expect(inner).not.toHaveBeenCalled();

    expect(closeTopOverlay()).toBe(true);
    expect(inner).toHaveBeenCalledTimes(1);

    expect(closeTopOverlay()).toBe(false);
  });

  it("stops closing an overlay after it unregisters", () => {
    const onClose = vi.fn();
    const unregister = pushEscClose(onClose);
    unregister();

    expect(closeTopOverlay()).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("tolerates double-unregister", () => {
    const onClose = vi.fn();
    const unregister = pushEscClose(onClose);
    unregister();
    expect(() => unregister()).not.toThrow();
  });
});
