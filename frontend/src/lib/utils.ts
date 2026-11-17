import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** First error message from an unknown thrown value; fallback when it
 * isn't an Error (api-client normalizes failures to ApiError, but catch
 * blocks can receive anything). */
export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/** Shared text-input classes — the standard form field look app-wide.
 * Compact variants (ai-tool-page, ai-providers-section) keep local strings. */
export const INPUT_CLASS =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring";

/** Today as a YYYY-MM-DD <input type="date"> value, local time. */
export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

const DAY_MONTH_YEAR = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const YEAR_MONTH_DAY = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
});
const MONTH_DAY = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});
const FULL_DATE_TIME = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** "05 Jan 2026" — em-dash when absent, raw input when unparseable. */
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DAY_MONTH_YEAR.format(date);
}

/** "5 Jan 2026" — raw input when unparseable. */
export function formatYearMonthDay(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : YEAR_MONTH_DAY.format(date);
}

/** "5 Jan" — chart-axis labels; raw input when unparseable. */
export function formatMonthDay(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : MONTH_DAY.format(date);
}

/** "Fri, 5 Jan 2026, 14:30" — raw input when unparseable. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : FULL_DATE_TIME.format(date);
}
