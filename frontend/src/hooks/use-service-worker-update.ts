import { useCallback, useEffect, useState } from "react";
import { isDesktopApp } from "../lib/desktop";

export interface UseServiceWorkerUpdateResult {
  /** A new service worker is installed and waiting to take control. */
  updateReady: boolean;
  /**
   * Accept the update: posts SKIP_WAITING to the waiting worker; when it
   * activates and takes control, the controllerchange listener reloads once.
   */
  applyUpdate: () => void;
}

/**
 * Registers the app shell service worker and surfaces waiting updates.
 *
 * Deliberately NO skipWaiting in the SW itself: a new deploy installs in the
 * background, and once it is waiting (and an older SW already controls the
 * page) we expose `updateReady` so the app can show an "Update available —
 * reload" toast. The user chooses when to activate it, so we never reload
 * mid-edit.
 *
 * In the Tauri desktop shell — and in the vite dev server — the SW is
 * unregistered entirely and its caches purged. Desktop is served same-origin
 * from the local sidecar backend; dev serves live modules. In both, a
 * persisted SW can only ever serve a stale app shell (its origin-scoped
 * caches survive rebuilds and even a different server taking over the same
 * port), so we self-heal: unregister, purge every cache, reload once.
 * Fresh desktop installs never register one; dev never keeps one.
 */
export function useServiceWorkerUpdate(): UseServiceWorkerUpdateResult {
  const [updateReady, setUpdateReady] = useState(false);
  const [waitingWorker, setWaitingWorker] = useState<ServiceWorker | null>(
    null,
  );

  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }

    if (isDesktopApp() || import.meta.env.DEV) {
      // Self-heal upgrades: unregister any leftover SW and purge every cache
      // it filled, then reload once so the app never keeps running an old
      // shell. sessionStorage guards against a reload loop.
      navigator.serviceWorker
        .getRegistrations()
        .then(async (registrations) => {
          if (registrations.length === 0) return;
          await Promise.all(
            registrations.map((registration) => registration.unregister()),
          );
          await Promise.all(
            (await caches.keys()).map((key) => caches.delete(key)),
          );
          if (sessionStorage.getItem("sw-purge-reloaded")) return;
          sessionStorage.setItem("sw-purge-reloaded", "1");
          window.location.reload();
        })
        .catch(() => {
          // Non-critical — the app still works without cleanup.
        });
      return;
    }

    let refreshing = false;
    // When the new SW takes control (after the user accepts the update),
    // reload once so the page picks up the new assets.
    const onControllerChange = () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener(
      "controllerchange",
      onControllerChange,
    );

    let cancelled = false;
    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        if (cancelled) return;
        // A waiting worker from a previous page load (rare, but possible if
        // the toast was dismissed) should be surfaced again immediately.
        if (registration.waiting && navigator.serviceWorker.controller) {
          setWaitingWorker(registration.waiting);
          setUpdateReady(true);
        }
        registration.addEventListener("updatefound", () => {
          const newWorker = registration.installing;
          if (!newWorker) return;
          newWorker.addEventListener("statechange", () => {
            if (cancelled) return;
            // `controller` is only set when an older SW already controls the
            // page — i.e. this is an update, not the very first install.
            if (
              newWorker.state === "installed" &&
              navigator.serviceWorker.controller
            ) {
              setWaitingWorker(newWorker);
              setUpdateReady(true);
            }
          });
        });
      })
      .catch(() => {
        // SW registration failed — non-critical, the app still works online.
      });

    return () => {
      cancelled = true;
      navigator.serviceWorker?.removeEventListener(
        "controllerchange",
        onControllerChange,
      );
    };
  }, []);

  const applyUpdate = useCallback(() => {
    waitingWorker?.postMessage({ type: "SKIP_WAITING" });
  }, [waitingWorker]);

  return { updateReady, applyUpdate };
}
