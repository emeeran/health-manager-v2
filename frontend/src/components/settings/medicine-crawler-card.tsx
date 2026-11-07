import { Loader2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  getMedicineCrawlerStatus,
  setMedicineCrawlerEnabled,
} from "../../lib/api/household";
import type { MedicineCrawlerStatus } from "../../lib/types/household";
import { useI18n } from "../../lib/i18n";
import { cn } from "../../lib/utils";

/**
 * Medicine catalog crawler toggle (Data settings).
 *
 * The crawler runs as a scheduler job in bounded batches; this card only
 * flips the persisted on/off flag (PUT /system/medicine-crawler, admin
 * guarded and audited server-side).
 */
export function MedicineCrawlerCard() {
  const { t } = useI18n();
  const { data, error, isLoading, mutate } = useSWR<MedicineCrawlerStatus>(
    "/system/medicine-crawler",
    getMedicineCrawlerStatus,
  );
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function toggle(next: boolean) {
    if (!data || saving) return;
    setSaving(true);
    setFailed(false);
    try {
      const updated = await setMedicineCrawlerEnabled(next);
      mutate(updated, { revalidate: false });
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-4 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {t.settings.data.crawlerHeading}…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-2 rounded-lg border border-border p-3">
        <p className="text-sm font-medium">{t.settings.data.crawlerHeading}</p>
        <p role="alert" className="text-sm text-danger">
          {t.settings.data.crawlerError}
        </p>
      </div>
    );
  }

  const enabled = data.enabled;

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{t.settings.data.crawlerHeading}</p>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label={t.settings.data.crawlerHeading}
          disabled={saving || !data.script_present}
          onClick={() => toggle(!enabled)}
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors",
            "disabled:cursor-not-allowed disabled:opacity-50",
            enabled ? "bg-primary" : "bg-muted-foreground/30",
          )}
        >
          <span
            className={cn(
              "inline-block size-4 transform rounded-full bg-background shadow transition-transform",
              enabled ? "translate-x-6" : "translate-x-1",
            )}
          />
        </button>
      </div>

      <p className="text-xs text-muted-foreground">
        {t.settings.data.crawlerDescription}
      </p>

      <p
        role={failed ? "alert" : "status"}
        className={cn(
          "text-xs",
          failed ? "text-danger" : "text-muted-foreground",
        )}
      >
        {failed
          ? t.settings.data.crawlerError
          : `${enabled ? t.settings.data.crawlerOn : t.settings.data.crawlerOff} · ${data.batch_pages} ${t.settings.data.crawlerBatchHint}`}
        {!data.script_present && (
          <span className="ml-2 text-warning">
            {t.settings.data.crawlerScriptMissing}
          </span>
        )}
      </p>
    </div>
  );
}
