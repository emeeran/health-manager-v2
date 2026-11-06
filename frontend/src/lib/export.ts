/**
 * Client-side CSV export. Builds the file in-memory (RFC 4180 quoting) and
 * triggers a download — no backend round-trip needed for tabular exports.
 */
export function downloadCsv(
  filename: string,
  rows: (string | number | null)[][],
): void {
  const escape = (value: string | number | null) => {
    const s = value === null || value === undefined ? "" : String(value);
    return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  const csv = rows.map((row) => row.map(escape).join(",")).join("\r\n");
  // Leading BOM so Excel opens UTF-8 (medicine names) correctly.
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
