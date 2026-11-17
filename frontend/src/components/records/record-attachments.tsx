import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileWarning,
  Loader2,
  Paperclip,
  UploadCloud,
  X,
} from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import {
  attachmentDownloadUrl,
  attachmentPageUrl,
  attachmentPreviewUrl,
  attachmentThumbnailUrl,
  uploadAttachments,
} from "../../lib/api/attachments";
import { checkFilenames } from "../../lib/api/records";
import { ExtractWithAi } from "./extraction-queue";
import { recordTypeMeta } from "../../lib/record-types";
import { formatFileSize, type Attachment } from "../../lib/types/attachment";
import type { FilenameMatch, HealthRecord } from "../../lib/types/record";
import { errorMessage } from "../../lib/utils";

function isImage(attachment: Attachment): boolean {
  return attachment.mime.startsWith("image/");
}

function isPdf(attachment: Attachment): boolean {
  return attachment.mime === "application/pdf";
}

export function RecordAttachments({
  record,
  memberId,
  autoExtract,
  onAutoExtractStarted,
  onChanged,
}: {
  record: HealthRecord;
  memberId: string;
  autoExtract?: boolean;
  onAutoExtractStarted?: () => void;
  onChanged: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [warnings, setWarnings] = useState<FilenameMatch[]>([]);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function uploadAndCheck(files: File[]) {
    if (files.length === 0) return;
    setUploadError(null);
    setUploading(true);
    try {
      await uploadAttachments(memberId, record.id, files);
      onChanged();
      try {
        const { matches } = await checkFilenames(
          memberId,
          files.map((file) => file.name),
        );
        setWarnings(matches);
      } catch {
        setWarnings([]); // duplicate warnings are best-effort
      }
    } catch (err) {
      setUploadError(
        errorMessage(err, "Upload failed. Try again."),
      );
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    void uploadAndCheck(Array.from(event.dataTransfer.files));
  }

  const viewing = record.attachments.find((a) => a.id === viewingId);

  return (
    <section
      className="rounded-xl border border-border bg-card p-5 shadow-sm"
      aria-label="Attachments"
    >
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
        <Paperclip className="size-4" aria-hidden />
        Attachments
        <span className="text-muted-foreground">
          ({record.attachments.length})
        </span>
      </h2>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`rounded-xl border border-dashed p-4 text-center transition-colors ${
          dragOver ? "border-primary bg-primary/5" : "border-border"
        }`}
      >
        <input
          ref={inputRef}
          id="attachment-input"
          type="file"
          multiple
          // Literal MIME types: WebKitGTK drops extension tokens (see batch-upload).
          accept="application/pdf,image/jpeg,image/png,image/webp"
          className="sr-only"
          onChange={(e) =>
            void uploadAndCheck(Array.from(e.target.files ?? []))
          }
        />
        <label
          htmlFor="attachment-input"
          className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          {uploading ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <UploadCloud className="size-4" aria-hidden />
          )}
          {uploading ? "Uploading…" : "Choose files"}
        </label>
        <p className="mt-2 text-xs text-muted-foreground">
          PDF, JPEG, PNG or WebP · up to 25 MB each · or drag files here
        </p>

        <ExtractWithAi
          memberId={memberId}
          recordId={record.id}
          autoQueue={autoExtract ? record.attachments : undefined}
          onQueueStarted={onAutoExtractStarted}
          onApplied={onChanged}
        />
      </div>

      {uploadError && (
        <p
          role="alert"
          className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {uploadError}
        </p>
      )}

      {warnings.length > 0 && (
        <div
          role="alert"
          className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning"
        >
          <p className="flex items-center gap-1.5 font-medium">
            <FileWarning className="size-4" aria-hidden />
            Possible duplicates found
          </p>
          <ul className="mt-1 space-y-0.5">
            {warnings.map((match) => (
              <li key={`${match.record_id}-${match.filename}`}>
                <span className="font-medium">{match.filename}</span> matches a{" "}
                {recordTypeMeta(match.record_type).label.toLowerCase()} from{" "}
                {match.record_date}
              </li>
            ))}
          </ul>
        </div>
      )}

      {record.attachments.length > 0 && (
        <ul className="mt-4 divide-y divide-border">
          {record.attachments.map((attachment) => (
            <li
              key={attachment.id}
              className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
            >
              <button
                type="button"
                onClick={() =>
                  setViewingId((current) =>
                    current === attachment.id ? null : attachment.id,
                  )
                }
                aria-expanded={viewingId === attachment.id}
                className="flex min-w-0 flex-1 items-center gap-3 text-left"
              >
                <img
                  src={attachmentThumbnailUrl(attachment.id)}
                  alt=""
                  loading="lazy"
                  className="size-12 shrink-0 rounded-lg border border-border object-cover"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {attachment.original_name}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {formatFileSize(attachment.file_size)} ·{" "}
                    {isImage(attachment)
                      ? "Image"
                      : isPdf(attachment)
                        ? "PDF"
                        : attachment.mime}
                  </span>
                </span>
              </button>
              <a
                href={attachmentDownloadUrl(attachment.id)}
                aria-label={`Download ${attachment.original_name}`}
                className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <Download className="size-4" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      )}

      {viewing && (
        <AttachmentViewer
          attachment={viewing}
          onClose={() => setViewingId(null)}
        />
      )}
    </section>
  );
}

function AttachmentViewer({
  attachment,
  onClose,
}: {
  attachment: Attachment;
  onClose: () => void;
}) {
  // PDF page index is 0-based server-side; the UI shows 1-based page numbers.
  const [pageIndex, setPageIndex] = useState(0);
  const pdf = isPdf(attachment);

  function goToPage(next: number) {
    if (next < 0) return;
    if (!pdf) return;
    // Probe the next page image first so an out-of-range request never lands
    // in the iframe; instead the known page count is clamped.
    const probe = new Image();
    probe.onload = () => {
      setPageIndex(next);
    };
    probe.onerror = () => {
      // Page doesn't exist — stay put.
    };
    probe.src = attachmentPageUrl(attachment.id, next);
  }

  return (
    <div className="mt-4 rounded-xl border border-border">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <p className="min-w-0 flex-1 truncate text-sm font-medium">
          {attachment.original_name}
        </p>
        {pdf && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
              disabled={pageIndex === 0}
              aria-label="Previous page"
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
            >
              <ChevronLeft className="size-4" aria-hidden />
            </button>
            <span className="text-xs tabular-nums text-muted-foreground">
              page {pageIndex + 1}
            </span>
            <button
              type="button"
              onClick={() => goToPage(pageIndex + 1)}
              aria-label="Next page"
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ChevronRight className="size-4" aria-hidden />
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close viewer"
          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
      {isImage(attachment) ? (
        <img
          src={attachmentPreviewUrl(attachment.id)}
          alt={attachment.original_name}
          className="max-h-[70vh] w-full rounded-b-xl bg-muted object-contain"
        />
      ) : pdf ? (
        <iframe
          key={pageIndex}
          title={`${attachment.original_name} page ${pageIndex + 1}`}
          src={attachmentPageUrl(attachment.id, pageIndex)}
          className="h-[70vh] w-full rounded-b-xl bg-muted"
        />
      ) : (
        <p className="p-6 text-center text-sm text-muted-foreground">
          No inline preview for this file type.{" "}
          <a
            href={attachmentDownloadUrl(attachment.id)}
            className="font-medium text-primary hover:underline"
          >
            Download it instead.
          </a>
        </p>
      )}
    </div>
  );
}
