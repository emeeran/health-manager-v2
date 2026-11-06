/**
 * Desktop (Tauri) detection. Tauri injects `window.__TAURI_INTERNALS__` (v2)
 * or `window.__TAURI__` (v1 compat) before any app code runs, so this is a
 * reliable synchronous check. Mirrors the detection used by the desktop
 * shell's own stub pages (desktop/stub/error.html).
 */
export function isDesktopApp(): boolean {
  return (
    typeof window !== "undefined" &&
    ("__TAURI_INTERNALS__" in window || "__TAURI__" in window)
  );
}
