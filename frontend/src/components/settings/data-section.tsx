import { AlertTriangle, CheckCircle2, Database, Loader2 } from "lucide-react";
import useSWR from "swr";
import { BackupSection } from "./backup-section";
import { getDatabaseIntegrity } from "../../lib/api/database";
import type { DatabaseIntegrity } from "../../lib/types/database";
import { useI18n } from "../../lib/i18n";

/**
 * Data settings: backup/restore (shared with the standalone backup section)
 * plus a read-only database integrity card from GET /database/integrity.
 *
 * NOTE: no destructive "reset household data" control — the v2 backend does
 * not expose a reset endpoint yet (the backup router only has create / list /
 * download / restore-request). Add one here when the backend ships it.
 */
export function DataSection() {
  const { t } = useI18n();
  return (
    <section
      aria-label={t.settings.data.heading}
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Database className="size-4 text-primary" aria-hidden />
        {t.settings.data.heading}
      </h2>
      <IntegrityCard />
      <BackupSection />
    </section>
  );
}

function IntegrityCard() {
  const { t } = useI18n();
  const { data, error, isLoading } = useSWR<DatabaseIntegrity>(
    "/database/integrity",
    getDatabaseIntegrity,
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {t.settings.data.integrity}…
      </div>
    );
  }

  if (error || !data) {
    return (
      <p
        role="alert"
        className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
      >
        Could not load the integrity report.
      </p>
    );
  }

  const healthy = data.ok && data.orphan_count === 0;

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{t.settings.data.integrity}</p>
        {healthy ? (
          <p
            role="status"
            className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
          >
            <CheckCircle2 className="size-3.5" aria-hidden />
            {t.settings.data.integrityOk}
          </p>
        ) : (
          <p
            role="alert"
            className="flex items-center gap-1.5 rounded-lg bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger"
          >
            <AlertTriangle className="size-3.5" aria-hidden />
            {t.settings.data.integrityProblems}
          </p>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted-foreground">
            {t.settings.data.engine}
          </dt>
          <dd className="font-mono text-xs">{data.engine}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            {t.settings.data.orphanCount}
          </dt>
          <dd className="tabular-nums text-xs">{data.orphan_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            {t.settings.data.attachmentsChecked}
          </dt>
          <dd className="tabular-nums text-xs">
            {data.attachment_check.checked}
            {data.attachment_check.missing > 0 && (
              <span className="ml-1 text-danger">
                ({data.attachment_check.missing}{" "}
                {t.settings.data.attachmentsMissing})
              </span>
            )}
          </dd>
        </div>
      </dl>

      {data.orphan_count > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left font-semibold uppercase tracking-wide text-muted-foreground">
              <th className="py-1.5 pr-3">Table</th>
              <th className="py-1.5 pr-3">Missing →</th>
              <th className="py-1.5 text-right">Rows</th>
            </tr>
          </thead>
          <tbody>
            {data.orphans
              .filter((orphan) => orphan.count > 0)
              .map((orphan) => (
                <tr
                  key={`${orphan.table}.${orphan.column}`}
                  className="border-b border-border/60 last:border-0"
                >
                  <td className="py-1.5 pr-3 font-mono">{orphan.table}</td>
                  <td className="py-1.5 pr-3 font-mono text-muted-foreground">
                    {orphan.column} → {orphan.target}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">
                    {orphan.count}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
      {data.orphan_count === 0 && (
        <p className="text-xs text-muted-foreground">
          {t.settings.data.noOrphans}
        </p>
      )}

      {(data.notes.length > 0 || !data.ok) && (
        <ul className="space-y-1">
          {(data.ok
            ? data.notes
            : [
                ...data.integrity_check.filter((line) => line !== "ok"),
                ...data.notes,
              ]
          ).map((note, index) => (
            <li
              key={index}
              className="flex items-start gap-1.5 rounded-lg bg-warning/10 px-2.5 py-1.5 text-xs text-foreground"
            >
              <AlertTriangle
                className="mt-0.5 size-3 shrink-0 text-warning"
                aria-hidden
              />
              {note}
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-muted-foreground">
        {t.settings.data.scanDuration} {data.duration_ms} ms
      </p>
    </div>
  );
}
