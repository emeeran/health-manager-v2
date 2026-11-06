import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  FileWarning,
  Loader2,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { streamBatchExtract } from "../../lib/api/extraction-batch";
import {
  applyBatchStreamEvent,
  countBatchCompleted,
  createBatchItems,
  finalizeBatchItems,
  type BatchFileItem,
} from "../../lib/batch-stream";

const MAX_BATCH_FILES = 20;

/**
 * Batch upload: multi-file picker → SSE extraction stream → per-file progress
 * list. The backend creates a draft record per extracted file; each finished
 * row links to the created record for review.
 */
export default function BatchUpload({ memberId }: { memberId: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [running, setRunning] = useState(false);
  const [items, setItems] = useState<BatchFileItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Stop an in-flight stream when the page unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleStart(fileList: File[]) {
    if (fileList.length === 0) return;
    if (fileList.length > MAX_BATCH_FILES) {
      setError(`One batch supports at most ${MAX_BATCH_FILES} files.`);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const names = fileList.map((file) => file.name);
    setRunning(true);
    setError(null);
    setItems(createBatchItems(fileList.length, names));
    try {
      await streamBatchExtract(
        memberId,
        fileList,
        (event) => {
          setItems((prev) => applyBatchStreamEvent(prev, event));
        },
        { signal: controller.signal },
      );
      setItems((prev) => finalizeBatchItems(prev, names));
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(
          err instanceof Error ? err.message : "Batch extraction failed.",
        );
      }
      setItems((prev) => finalizeBatchItems(prev, names));
    } finally {
      setRunning(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const completed = countBatchCompleted(items);
  const done = !running && items.length > 0;

  return (
    <section
      aria-label="Batch upload"
      className="rounded-xl border border-border bg-card p-4 shadow-sm"
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <UploadCloud className="size-4 text-primary" aria-hidden />
        Batch upload &amp; extract
      </h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Choose up to {MAX_BATCH_FILES} documents (PDF / JPEG / PNG / WebP); AI
        extracts each one and creates a draft record per file.
      </p>

      <input
        ref={inputRef}
        id="batch-upload-input"
        type="file"
        multiple
        // Literal MIME types only: WebKitGTK (desktop shell) drops
        // extension-only accept tokens like ".pdf" when building the
        // file-chooser filter, which hides every PDF from the dialog.
        accept="application/pdf,image/jpeg,image/png,image/webp"
        className="sr-only"
        disabled={running}
        onChange={(e) => void handleStart(Array.from(e.target.files ?? []))}
      />
      <div className="mt-3 flex items-center gap-2">
        <label
          htmlFor="batch-upload-input"
          aria-disabled={running}
          className={`inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 ${
            running ? "pointer-events-none opacity-60" : ""
          }`}
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Sparkles className="size-4" aria-hidden />
          )}
          {running ? "Extracting…" : "Choose files"}
        </label>
        {running && (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-3.5" aria-hidden />
            Cancel
          </button>
        )}
        {items.length > 0 && (
          <p className="ml-auto text-xs tabular-nums text-muted-foreground">
            {completed}/{items.length} files
          </p>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}

      {items.length > 0 && (
        <ul className="mt-3 space-y-1.5" aria-live="polite">
          {items.map((item, index) => (
            <li
              key={`${item.filename}-${index}`}
              className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm"
            >
              {item.status === "extracting" ? (
                <Loader2
                  className="size-4 shrink-0 animate-spin text-primary"
                  aria-hidden
                />
              ) : item.status === "error" ? (
                <FileWarning
                  className="size-4 shrink-0 text-danger"
                  aria-hidden
                />
              ) : item.status === "complete" ? (
                <CheckCircle2
                  className="size-4 shrink-0 text-emerald-500"
                  aria-hidden
                />
              ) : (
                <span
                  aria-hidden
                  className="size-4 shrink-0 rounded-full border border-border"
                />
              )}
              <span className="min-w-0 flex-1 truncate">{item.filename}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {item.status === "pending" && "Waiting…"}
                {item.status === "extracting" && "Extracting…"}
                {item.status === "error" && (item.error ?? "Failed")}
                {item.status === "complete" &&
                  (item.result?.summary || "Extracted").slice(0, 60)}
              </span>
              {item.status === "complete" && item.result?.record_id && (
                <Link
                  to={`/members/${memberId}/records/${item.result.record_id}`}
                  className="shrink-0 text-xs font-medium text-primary hover:underline"
                >
                  Review
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {done && !error && (
        <p
          role="status"
          className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <CheckCircle2 className="size-3 text-emerald-500" aria-hidden />
          Batch finished. Review each draft record — AI output is a draft, not a
          verdict.
        </p>
      )}
    </section>
  );
}
