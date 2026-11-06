export interface Attachment {
  id: string;
  file_path: string;
  content_hash: string;
  file_size: number;
  mime: string;
  original_name: string;
  created_at: string;
}

/** Human-readable byte size, e.g. `1.4 MB`. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes;
  let unit = "B";
  for (const next of units) {
    if (value < 1024) break;
    value /= 1024;
    unit = next;
  }
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} ${unit}`;
}
