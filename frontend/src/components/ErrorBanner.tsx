import { AlertTriangle, X } from "lucide-react";
import { useSyncExternalStore } from "react";
import {
  dismissApiError,
  getApiErrorSnapshot,
  subscribeApiErrors,
} from "../lib/api-errors";

export function ErrorBanner() {
  const message = useSyncExternalStore(subscribeApiErrors, getApiErrorSnapshot);
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex items-center gap-2 border-b border-border bg-danger/10 px-4 py-2 text-sm text-danger"
    >
      <AlertTriangle className="size-4 shrink-0" aria-hidden />
      <span className="flex-1">{message}</span>
      <button
        type="button"
        onClick={dismissApiError}
        aria-label="Dismiss error"
        className="rounded p-1 hover:bg-danger/10"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}
