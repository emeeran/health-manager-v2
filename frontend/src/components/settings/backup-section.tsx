import {
  Archive,
  Download,
  HardDriveDownload,
  Info,
  Loader2,
  Undo2,
} from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import {
  backupDownloadUrl,
  createBackup,
  requestRestore,
} from "../../lib/api/backup";
import { formatFileSize } from "../../lib/types/attachment";
import type { BackupInfo } from "../../lib/types/backup";

export function BackupSection() {
  const {
    data: backups,
    isLoading,
    mutate,
  } = useSWR<BackupInfo[]>("/backup/list");
  const [creating, setCreating] = useState(false);
  const [restoringName, setRestoringName] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setCreating(true);
    setError(null);
    try {
      const { filename } = await createBackup();
      await mutate();
      setNotice(`Backup created: ${filename}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backup failed.");
    } finally {
      setCreating(false);
    }
  }

  async function handleRestore(backup: BackupInfo) {
    if (
      !window.confirm(
        `Restore "${backup.filename}"? Current data will be replaced by this archive, and the app restarts while the restore runs. You'll be signed out briefly — wait a minute or two, then sign in again.`,
      )
    )
      return;
    setRestoringName(backup.filename);
    setError(null);
    try {
      const { message } = await requestRestore(backup.filename);
      setNotice(message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restore request failed.");
    } finally {
      setRestoringName(null);
    }
  }

  return (
    <section
      aria-label="Backup & restore"
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Archive className="size-4 text-primary" aria-hidden />
          Backup & restore
        </h2>
        <button
          type="button"
          onClick={() => void handleCreate()}
          disabled={creating}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {creating ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <HardDriveDownload className="size-4" aria-hidden />
          )}
          Create backup
        </button>
      </div>

      <p className="flex items-start gap-2 rounded-lg bg-primary/5 px-3 py-2 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
        Backups are encrypted archives of every record, medication and document.
        Download them and keep a copy off this machine — a backup you can't
        reach is not a backup.
      </p>

      {notice && (
        <p
          role="status"
          className="rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary"
        >
          {notice}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading backups…
        </div>
      ) : !backups || backups.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-background p-6 text-center text-sm text-muted-foreground">
          No backups yet. Create one before installing updates.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-3">File</th>
                <th className="py-2 pr-3">Size</th>
                <th className="py-2 pr-3">Created</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {backups.map((backup) => (
                <tr
                  key={backup.filename}
                  className="border-b border-border/60 last:border-0"
                >
                  <td className="py-2.5 pr-3 font-mono text-xs">
                    {backup.filename}
                  </td>
                  <td className="py-2.5 pr-3 tabular-nums text-muted-foreground">
                    {formatFileSize(backup.size_bytes)}
                  </td>
                  <td className="py-2.5 pr-3 text-muted-foreground">
                    {new Date(backup.created_at).toLocaleString(undefined, {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td className="py-2.5">
                    <div className="flex items-center justify-end gap-2">
                      <a
                        href={backupDownloadUrl(backup.filename)}
                        download
                        className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs transition-colors hover:bg-muted"
                      >
                        <Download className="size-3.5" aria-hidden />
                        Download
                      </a>
                      <button
                        type="button"
                        onClick={() => void handleRestore(backup)}
                        disabled={restoringName === backup.filename}
                        className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
                      >
                        {restoringName === backup.filename ? (
                          <Loader2
                            className="size-3.5 animate-spin"
                            aria-hidden
                          />
                        ) : (
                          <Undo2 className="size-3.5" aria-hidden />
                        )}
                        Restore
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
