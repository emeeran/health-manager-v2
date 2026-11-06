/**
 * Four pinned themes: light / sepia / grey / dark.
 *
 * Ported from v1's mechanism:
 * - The chosen theme is applied as a class on <html> (`sepia` / `grey` /
 *   `dark`; light is the unclassed default), which globals.css maps to CSS
 *   custom properties.
 * - localStorage is the primary store, mirrored into a `theme` cookie because
 *   WebKitGTK (the Tauri desktop webview) can lose localStorage across
 *   restarts; the pre-paint bootstrap in index.html falls back to the cookie.
 * - The app never follows the OS appearance: a theme, once chosen, is pinned.
 *   A missing value is resolved against prefers-color-scheme exactly once and
 *   then persisted, so later OS light/dark flips never change the app.
 */

export const THEMES = ["light", "sepia", "grey", "dark"] as const;
export type Theme = (typeof THEMES)[number];

export const THEME_STORAGE_KEY = "theme";
export const THEME_COOKIE_KEY = "theme";

/** Legacy value from the old three-state theme; treated as "not chosen". */
const LEGACY_THEME = "system";

function isTheme(value: string | null | undefined): value is Theme {
  return (
    typeof value === "string" && (THEMES as readonly string[]).includes(value)
  );
}

/**
 * Pure resolver for the initial theme (unit-tested directly):
 * 1. localStorage wins, unless missing or the legacy "system" value;
 * 2. the mirror cookie is the fallback;
 * 3. otherwise prefers-color-scheme decides, exactly once.
 */
export function resolveInitialTheme(
  storage: string | null,
  cookie: string | null,
  prefersDark: boolean,
): Theme {
  const stored = storage === LEGACY_THEME ? null : storage;
  const mirrored = cookie === LEGACY_THEME ? null : cookie;
  if (isTheme(stored)) return stored;
  if (isTheme(mirrored)) return mirrored;
  return prefersDark ? "dark" : "light";
}

function readThemeCookie(): string | null {
  try {
    const match = document.cookie.match(
      new RegExp(`(?:^|; )${THEME_COOKIE_KEY}=([^;]*)`),
    );
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

/** Resolve the initial theme from the live browser environment. */
/** Pre-phase-12 storage key used by the old light/dark-only header toggle. */
const LEGACY_STORAGE_KEY = "fhm-theme";

export function getInitialTheme(): Theme {
  let storage: string | null = null;
  try {
    storage = localStorage.getItem(THEME_STORAGE_KEY);
    if (storage === null) {
      // Migrate the old light/dark-only preference on first run.
      storage = localStorage.getItem(LEGACY_STORAGE_KEY);
    }
  } catch {
    // Storage unavailable (private mode etc.) — fall through to cookie/OS.
  }
  const cookie = readThemeCookie();
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return resolveInitialTheme(storage, cookie, prefersDark);
}

/**
 * Apply a theme: set the class on <html>, keep the `dark` class in sync for
 * Tailwind's `dark:` variant, and persist to both localStorage and the
 * mirror cookie so the pre-paint bootstrap can restore it next launch.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  for (const value of THEMES) {
    if (value !== "light") root.classList.toggle(value, value === theme);
  }
  root.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Non-fatal: cookie mirror below still covers WebKitGTK.
  }
  document.cookie = `${THEME_COOKIE_KEY}=${encodeURIComponent(theme)}; max-age=31536000; path=/; SameSite=Strict`;
}
