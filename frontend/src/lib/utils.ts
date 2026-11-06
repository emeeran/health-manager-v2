import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
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
