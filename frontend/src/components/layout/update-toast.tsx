import { useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { useI18n } from "../../lib/i18n";
import { useServiceWorkerUpdate } from "../../hooks/use-service-worker-update";

/**
 * "Update available — reload" toast, rendered under the header in AppLayout.
 * Shown only while a new service worker is installed and waiting; "Reload"
 * posts SKIP_WAITING to the worker, which activates it and reloads the page
 * (see useServiceWorkerUpdate). Dismissible — the user can finish what they
 * are doing and pick up the update on a later reload.
 */
export function UpdateToast() {
  const { t } = useI18n();
  const { updateReady, applyUpdate } = useServiceWorkerUpdate();
  const [dismissed, setDismissed] = useState(false);

  if (!updateReady || dismissed) return null;

  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-border bg-primary/10 px-4 py-2 text-sm text-foreground"
    >
      <RefreshCw className="size-4 shrink-0 text-primary" aria-hidden />
      <span className="flex-1">{t.update.available}</span>
      <button
        type="button"
        onClick={applyUpdate}
        className="rounded-lg bg-primary px-3 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        {t.update.reload}
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label={t.update.dismiss}
        className="rounded p-1 hover:bg-muted"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}
