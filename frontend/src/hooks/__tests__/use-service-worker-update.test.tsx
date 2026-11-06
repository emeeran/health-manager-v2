import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useServiceWorkerUpdate } from "../use-service-worker-update";

function makeRegistration() {
  let onStateChange: (() => void) | null = null;
  const worker = {
    state: "installing",
    postMessage: vi.fn(),
    addEventListener: (type: string, handler: () => void) => {
      if (type === "statechange") onStateChange = handler;
    },
    removeEventListener: (type: string) => {
      if (type === "statechange") onStateChange = null;
    },
  };
  const listeners = new Map<string, (event: unknown) => void>();
  const registration = {
    installing: worker as unknown as ServiceWorker,
    waiting: null,
    addEventListener: (type: string, handler: (event: unknown) => void) => {
      listeners.set(type, handler);
    },
    removeEventListener: (type: string) => {
      listeners.delete(type);
    },
  };
  function emitUpdateFound() {
    listeners.get("updatefound")?.({});
  }
  function setState(next: string) {
    worker.state = next;
    onStateChange?.();
  }
  return { registration, worker, emitUpdateFound, setState };
}

function stubServiceWorker(overrides: Record<string, unknown> = {}) {
  const sw = {
    register: vi.fn(),
    getRegistrations: vi.fn(async (): Promise<unknown[]> => []),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    controller: null,
    ...overrides,
  };
  Object.defineProperty(navigator, "serviceWorker", {
    value: sw,
    configurable: true,
  });
  return sw;
}

afterEach(() => {
  // Remove the stubbed property entirely (mirrors the v1 desktop tests).
  delete (navigator as unknown as Record<string, unknown>).serviceWorker;
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  sessionStorage.clear();
});

describe("useServiceWorkerUpdate", () => {
  it("unregisters and purges caches in dev (vite serves live modules)", async () => {
    // vitest runs with import.meta.env.DEV = true — the purge path applies.
    const sw = stubServiceWorker();
    const unregister = vi.fn(async () => true);
    sw.getRegistrations.mockResolvedValue([{ unregister }]);
    vi.stubGlobal("caches", {
      keys: vi.fn(async () => ["fhm-v2-shell-v1"]),
      delete: vi.fn(async () => undefined),
    });

    renderHook(() => useServiceWorkerUpdate());

    await waitFor(() => expect(unregister).toHaveBeenCalled());
    expect(sw.register).not.toHaveBeenCalled();
  });

  it("flags an update when an installed worker is waiting on a controlled page", async () => {
    vi.stubEnv("DEV", false);
    const { registration, worker, emitUpdateFound, setState } =
      makeRegistration();
    const sw = stubServiceWorker();
    sw.register.mockResolvedValue(registration);
    // A controller means this is an update, not the first install.
    (sw as { controller: unknown }).controller = { scriptURL: "/sw.js" };

    const { result } = renderHook(() => useServiceWorkerUpdate());
    await waitFor(() => expect(sw.register).toHaveBeenCalledWith("/sw.js"));

    expect(result.current.updateReady).toBe(false);
    act(() => {
      emitUpdateFound();
      setState("installed");
    });

    await waitFor(() => expect(result.current.updateReady).toBe(true));

    result.current.applyUpdate();
    expect(worker.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
  });

  it("does not flag an update on the very first install (no controller)", async () => {
    vi.stubEnv("DEV", false);
    const { registration, emitUpdateFound, setState } = makeRegistration();
    const sw = stubServiceWorker();
    sw.register.mockResolvedValue(registration);

    const { result } = renderHook(() => useServiceWorkerUpdate());
    await waitFor(() => expect(sw.register).toHaveBeenCalled());

    act(() => {
      emitUpdateFound();
      setState("installed");
    });

    expect(result.current.updateReady).toBe(false);
  });

  it("unregisters any service worker inside the Tauri desktop shell", async () => {
    const sw = stubServiceWorker();
    const unregister = vi.fn(async () => true);
    sw.getRegistrations.mockResolvedValue([{ unregister }]);
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    vi.stubGlobal("caches", {
      keys: vi.fn(async () => ["fhm-v2-shell-v1"]),
      delete: vi.fn(async () => undefined),
    });

    renderHook(() => useServiceWorkerUpdate());

    await waitFor(() => expect(unregister).toHaveBeenCalled());
    expect(sw.register).not.toHaveBeenCalled();
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("does nothing when service workers are unsupported", () => {
    const { result } = renderHook(() => useServiceWorkerUpdate());
    expect(result.current.updateReady).toBe(false);
    expect(result.current.applyUpdate).toBeTypeOf("function");
  });
});
