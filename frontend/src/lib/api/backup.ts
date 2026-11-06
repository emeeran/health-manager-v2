import { apiRequest } from "../api-client";

export function createBackup(): Promise<{ filename: string }> {
  return apiRequest<{ filename: string }>("/backup/create", {
    method: "POST",
  });
}

/** Direct download URL (Content-Disposition: attachment, cookies sent). */
export function backupDownloadUrl(filename: string): string {
  return `/api/v1/backup/download/${encodeURIComponent(filename)}`;
}

/**
 * Queue a privileged restore. The backend restarts while applying it, so the
 * caller should warn before confirming.
 */
export function requestRestore(filename: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/backup/restore-request", {
    method: "POST",
    body: { filename },
  });
}
