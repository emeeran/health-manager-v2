import {
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  Download,
  FileWarning,
  Loader2,
  MinusCircle,
  Paperclip,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import useSWR from "swr";
import {
  attachmentDownloadUrl,
  attachmentPageUrl,
  attachmentPreviewUrl,
  attachmentThumbnailUrl,
  uploadAttachments,
} from "../lib/api/attachments";
import { CurrentMedicationsPrompt } from "../components/members/current-medications-prompt";
import { ConfidentialityBadge } from "../components/records/confidentiality";
import { TrackPrescriptionMeds } from "../components/records/track-prescription-meds";
import { streamExtract } from "../lib/api/ai";
import {
  applyExtraction,
  checkFilenames,
  deleteRecord,
  type ApplyExtractionInput,
} from "../lib/api/records";

import { recordTypeMeta } from "../lib/record-types";
import { formatFileSize, type Attachment } from "../lib/types/attachment";
import type {
  ExtractStage,
  ExtractionResult,
  Verification,
} from "../lib/types/ai";
import type { FilenameMatch, HealthRecord } from "../lib/types/record";

function isImage(attachment: Attachment): boolean {
  return attachment.mime.startsWith("image/");
}

function isPdf(attachment: Attachment): boolean {
  return attachment.mime === "application/pdf";
}

export default function RecordDetail() {
  const { memberId = "", recordId = "" } = useParams();
  // Arriving from the wizard with attached documents (?extract=1) kicks off
  // extraction for every attachment automatically.
  const [searchParams, setSearchParams] = useSearchParams();
  const autoExtract = searchParams.get("extract") === "1";
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);
  const {
    data: record,
    error,
    isLoading,
    mutate,
  } = useSWR<HealthRecord>(
    memberId && recordId ? `/members/${memberId}/records/${recordId}` : null,
  );

  async function handleDelete() {
    if (!record) return;
    if (!window.confirm("Delete this record? Its attachments go with it."))
      return;
    setDeleting(true);
    setDeleteError(false);
    try {
      await deleteRecord(memberId, recordId);
      await navigate(`/members/${memberId}`);
    } catch {
      setDeleteError(true);
    } finally {
      setDeleting(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl">
        <p
          role="alert"
          className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load this record.{" "}
          {error instanceof Error ? error.message : ""}
        </p>
      </div>
    );
  }

  if (isLoading || !record) {
    return (
      <div className="mx-auto flex max-w-3xl items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading record…
      </div>
    );
  }

  const { label, icon: TypeIcon } = recordTypeMeta(record.record_type);
  const extractedMedsCount =
    (record.clinical_data?.medications as unknown[] | undefined)?.length ?? 0;
  const hasClinicalData =
    record.clinical_data && Object.keys(record.clinical_data).length > 0;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        to={`/members/${memberId}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to member
      </Link>

      {(record.record_type === "prescription" || extractedMedsCount > 0) && (
        <>
          <CurrentMedicationsPrompt memberId={memberId} />
          <TrackPrescriptionMeds memberId={memberId} record={record} />
        </>
      )}

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <TypeIcon className="size-5" aria-hidden />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{label}</h1>
              <ConfidentialityBadge level={record.confidentiality_level} />
            </div>
            <p className="text-sm text-muted-foreground">
              {record.record_date}
              {record.record_time ? ` · ${record.record_time.slice(0, 5)}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {deleteError && (
            <span role="alert" className="text-xs text-danger">
              Delete failed
            </span>
          )}
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
          >
            {deleting ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Trash2 className="size-4" aria-hidden />
            )}
            Delete record
          </button>
        </div>
      </div>

      <section
        className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
        aria-label="Record details"
      >
        <DetailField label="Diagnosis" value={record.diagnosis} />
        <DetailField label="Investigations" value={record.investigations} />
        <DetailField label="Doctor" value={record.doctor_name} />
        {record.provider_name && (
          <DetailField label="Provider" value={record.provider_name} />
        )}
        <DetailField label="Summary" value={record.summary} multiline />
        <DetailField
          label="Prescription"
          value={record.prescription_text}
          multiline
        />
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Tags
          </p>
          {record.tags.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">—</p>
          ) : (
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {record.tags.map((tag) => (
                <li
                  key={tag}
                  className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
                >
                  {tag}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {hasClinicalData && (
        <section
          aria-label="Extracted clinical data"
          className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
        >
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" aria-hidden />
            Structured data
          </h2>
          <p className="text-xs text-muted-foreground">
            Saved alongside this record from document extraction — feeds trends,
            alerts, and the AI reports.
          </p>
          <ClinicalDataView
            data={record.clinical_data as Record<string, unknown>}
          />
        </section>
      )}

      <AttachmentsSection
        record={record}
        memberId={memberId}
        autoExtract={autoExtract}
        onAutoExtractStarted={() => setSearchParams({}, { replace: true })}
        onChanged={() => void mutate()}
      />
    </div>
  );
}

function DetailField({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string | null;
  multiline?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      {multiline ? (
        <p className="mt-1 whitespace-pre-wrap text-sm">
          {value || <span className="text-muted-foreground">—</span>}
        </p>
      ) : (
        <p className="mt-1 text-sm">
          {value || <span className="text-muted-foreground">—</span>}
        </p>
      )}
    </div>
  );
}

function AttachmentsSection({
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
        err instanceof Error ? err.message : "Upload failed. Try again.",
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

const EXTRACT_STAGES: readonly { stage: ExtractStage; label: string }[] = [
  { stage: "reading", label: "Reading document" },
  { stage: "extracting", label: "Extracting data" },
  { stage: "verifying", label: "Verifying result" },
];

const VERIFICATION_POLL_MS = 3_000;
const VERIFICATION_POLL_MAX_MS = 60_000;

/** Per-document progress for the auto pipeline started by the wizard. */
type QueueState = "waiting" | "running" | "done" | "failed" | "skipped";

interface QueueItem {
  name: string;
  state: QueueState;
  detail?: string;
}

/** MIME types the extraction pipeline accepts (mirrors the backend). */
const EXTRACTABLE_MIMES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
];

/**
 * "Extract with AI" action: picks the first chosen file, streams the SSE
 * extraction, shows live stage progress, then the parsed result with a
 * verification chip and an "Apply to record" action. When launched from the
 * wizard with attached documents (autoQueue), every attachment is extracted
 * and applied automatically — then the meds-update prompt takes over.
 */
function ExtractWithAi({
  memberId,
  recordId,
  autoQueue,
  onQueueStarted,
  onApplied,
}: {
  memberId: string;
  recordId: string;
  autoQueue?: Attachment[];
  onQueueStarted?: () => void;
  onApplied: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [stageMessages, setStageMessages] = useState<
    Partial<Record<ExtractStage, string>>
  >({});
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [verifyingSince, setVerifyingSince] = useState<number | null>(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const [appliedCounts, setAppliedCounts] = useState<{
    labs_created: number;
    vitals_created: number;
  } | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Stop an in-flight stream when the page unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const { data: verification } = useSWR<Verification>(
    result?.verification_id ? `/verifications/${result.verification_id}` : null,
    {
      refreshInterval: (latest) =>
        (latest?.status ?? "pending") === "pending" &&
        verifyingSince !== null &&
        Date.now() - verifyingSince < VERIFICATION_POLL_MAX_MS
          ? VERIFICATION_POLL_MS
          : 0,
    },
  );

  /** Persist an extraction result; returns the saved-row counts. */
  async function applyResult(
    extraction: ExtractionResult,
  ): Promise<{ labs_created: number; vitals_created: number }> {
    const clinical = extraction.clinical_data;
    // Absent fields are omitted so the record keeps its current values.
    const body: ApplyExtractionInput = {
      clinical_data: clinical,
      ...(extraction.summary !== null ? { summary: extraction.summary } : {}),
      ...(typeof clinical.diagnosis === "string"
        ? { diagnosis: clinical.diagnosis }
        : {}),
      ...(typeof clinical.record_date === "string"
        ? { record_date: clinical.record_date }
        : {}),
      ...(typeof clinical.doctor_name === "string"
        ? { doctor_name: clinical.doctor_name }
        : {}),
    };
    return applyExtraction(memberId, recordId, body);
  }

  async function handleExtract(file: File) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setFileName(file.name);
    setStageMessages({});
    setResult(null);
    setApplied(false);
    setAppliedCounts(null);
    setApplyError(null);
    setVerifyingSince(null);
    try {
      const extraction = await streamExtract(
        memberId,
        file,
        (event) => {
          if (
            event.stage === "reading" ||
            event.stage === "extracting" ||
            event.stage === "verifying"
          ) {
            setStageMessages((prev) => ({
              ...prev,
              [event.stage]: event.message,
            }));
          }
        },
        { signal: controller.signal, recordId },
      );
      setVerifyingSince(Date.now());
      setResult(extraction);
    } catch (err) {
      if (!controller.signal.aborted) {
        setExtractError(
          err instanceof Error ? err.message : "Extraction failed. Try again.",
        );
      }
    } finally {
      setRunning(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleApply() {
    if (!result) return;
    setApplying(true);
    setApplyError(null);
    try {
      const appliedResult = await applyResult(result);
      setAppliedCounts(appliedResult);
      setApplied(true);
      onApplied();
    } catch (err) {
      setApplyError(
        err instanceof Error ? err.message : "Could not apply to the record.",
      );
    } finally {
      setApplying(false);
    }
  }

  function setQueueAt(index: number, patch: Partial<QueueItem>) {
    setQueue(
      (current) =>
        current?.map((item, i) =>
          i === index ? { ...item, ...patch } : item,
        ) ?? null,
    );
  }

  /** Wizard hand-off: process every attached document in sequence —
   * download → OCR extraction → apply — refreshing the record between
   * files so labs/vitals/med prompts land as each document completes. */
  async function runQueue(attachments: Attachment[]) {
    setQueue(
      attachments.map((a) => ({ name: a.original_name, state: "waiting" })),
    );
    for (let index = 0; index < attachments.length; index++) {
      const attachment = attachments[index];
      setQueueAt(index, { state: "running" });
      if (!EXTRACTABLE_MIMES.includes(attachment.mime)) {
        setQueueAt(index, { state: "skipped", detail: "unsupported type" });
        continue;
      }
      try {
        const response = await fetch(attachmentDownloadUrl(attachment.id));
        if (!response.ok)
          throw new Error(`download failed (${response.status})`);
        const blob = await response.blob();
        const file = new File([blob], attachment.original_name, {
          type: attachment.mime,
        });
        const extraction = await streamExtract(
          memberId,
          file,
          (event) => {
            if (
              event.stage === "reading" ||
              event.stage === "extracting" ||
              event.stage === "verifying"
            ) {
              setStageMessages((prev) => ({
                ...prev,
                [event.stage]: event.message,
              }));
            }
          },
          { recordId },
        );
        const counts = await applyResult(extraction);
        onApplied();
        setQueueAt(index, {
          state: "done",
          detail: `${counts.labs_created} lab(s), ${counts.vitals_created} vital(s) saved`,
        });
      } catch (err) {
        setQueueAt(index, {
          state: "failed",
          detail: err instanceof Error ? err.message : "extraction failed",
        });
      }
    }
    setRunning(false);
  }

  const queueStartedRef = useRef(false);
  useEffect(() => {
    if (autoQueue && autoQueue.length > 0 && !queueStartedRef.current) {
      queueStartedRef.current = true;
      onQueueStarted?.(); // clear ?extract — a refresh must not re-trigger
      setRunning(true);
      void runQueue(autoQueue);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run-once hand-off
  }, [autoQueue]);

  const active = running || result !== null || extractError !== null;

  return (
    <>
      <input
        ref={inputRef}
        id="extract-input"
        type="file"
        // Literal MIME types: WebKitGTK drops extension tokens (see batch-upload).
        accept="application/pdf,image/jpeg,image/png,image/webp"
        className="sr-only"
        disabled={running}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleExtract(file);
        }}
      />
      <div className="mt-3 flex items-center justify-center gap-2">
        <label
          htmlFor="extract-input"
          aria-disabled={running}
          className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted ${
            running ? "pointer-events-none opacity-50" : ""
          }`}
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Sparkles className="size-4" aria-hidden />
          )}
          {running ? "Extracting…" : "Extract with AI"}
        </label>
        {running && (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="rounded-lg px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Cancel
          </button>
        )}
      </div>

      {queue && (
        <ul aria-label="Document processing queue" className="mt-3 space-y-1">
          {queue.map((item) => (
            <li
              key={item.name}
              className="flex items-center gap-2 text-xs"
              data-testid="extract-queue-item"
            >
              {item.state === "done" ? (
                <CheckCircle2
                  className="size-3.5 shrink-0 text-primary"
                  aria-hidden
                />
              ) : item.state === "running" ? (
                <Loader2
                  className="size-3.5 shrink-0 animate-spin text-primary"
                  aria-hidden
                />
              ) : item.state === "failed" ? (
                <XCircle
                  className="size-3.5 shrink-0 text-danger"
                  aria-hidden
                />
              ) : item.state === "skipped" ? (
                <MinusCircle
                  className="size-3.5 shrink-0 text-muted-foreground"
                  aria-hidden
                />
              ) : (
                <Circle className="size-3.5 shrink-0 text-border" aria-hidden />
              )}
              <span className="min-w-0 truncate">{item.name}</span>
              {item.detail && (
                <span className="text-muted-foreground">{item.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {active && (
        <div
          className="mt-3 space-y-3 rounded-xl border border-border bg-background p-4 text-left"
          aria-live="polite"
        >
          {fileName && (
            <p className="truncate text-xs text-muted-foreground">
              <Sparkles className="mr-1 inline size-3.5" aria-hidden />
              {fileName}
            </p>
          )}

          {!result && (
            <StageList running={running} stageMessages={stageMessages} />
          )}

          {extractError && (
            <p
              role="alert"
              className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {extractError}
            </p>
          )}

          {result && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <StageList
                  running={false}
                  stageMessages={stageMessages}
                  compact
                />
                <span className="text-xs text-muted-foreground">
                  via {result.provider_used}
                </span>
                {verification && (
                  <VerificationChip verification={verification} />
                )}
              </div>

              {result.summary && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    AI summary
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-sm">
                    {result.summary}
                  </p>
                </div>
              )}

              <ClinicalDataView data={result.clinical_data} />

              {applyError && (
                <p
                  role="alert"
                  className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
                >
                  {applyError}
                </p>
              )}
              {applied && (
                <p role="status" className="text-sm font-medium text-primary">
                  Applied to record.
                  {appliedCounts &&
                    (appliedCounts.labs_created > 0 ||
                      appliedCounts.vitals_created > 0) &&
                    ` ${appliedCounts.labs_created} lab result(s) and ${appliedCounts.vitals_created} vital(s) saved.`}
                </p>
              )}
              <button
                type="button"
                onClick={() => void handleApply()}
                disabled={applying || applied}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {applying ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Sparkles className="size-4" aria-hidden />
                )}
                {applied ? "Applied" : "Apply to record"}
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}

function StageList({
  running,
  stageMessages,
  compact = false,
}: {
  running: boolean;
  stageMessages: Partial<Record<ExtractStage, string>>;
  compact?: boolean;
}) {
  return (
    <ul className={compact ? "flex flex-wrap gap-x-4 gap-y-1" : "space-y-1.5"}>
      {EXTRACT_STAGES.map(({ stage, label }, index) => {
        const message = stageMessages[stage];
        if (message === undefined) return null;
        const laterReached = EXTRACT_STAGES.slice(index + 1).some(
          ({ stage: s }) => stageMessages[s] !== undefined,
        );
        const done = laterReached || compact;
        const current = running && !laterReached;
        return (
          <li
            key={stage}
            className={`flex items-center gap-2 ${compact ? "text-xs" : "text-sm"} ${
              done ? "" : current ? "font-medium" : "text-muted-foreground"
            }`}
          >
            {done ? (
              <CheckCircle2
                className={`${compact ? "size-3.5" : "size-4"} shrink-0 text-primary`}
                aria-hidden
              />
            ) : current ? (
              <Loader2
                className="size-4 shrink-0 animate-spin text-primary"
                aria-hidden
              />
            ) : (
              <Circle className="size-4 shrink-0 text-border" aria-hidden />
            )}
            <span className="min-w-0">{done ? label : message || label}</span>
          </li>
        );
      })}
    </ul>
  );
}

function VerificationChip({ verification }: { verification: Verification }) {
  switch (verification.status) {
    case "passed":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="size-3.5" aria-hidden />
          AI-verified
        </span>
      );
    case "flagged":
      return (
        <span
          title={verification.notes ?? undefined}
          className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-0.5 text-xs font-medium text-warning"
        >
          <FileWarning className="size-3.5" aria-hidden />
          Flagged: {verification.notes || "needs review"}
        </span>
      );
    case "failed":
      return (
        <span
          title={verification.notes ?? undefined}
          className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
        >
          <Circle className="size-3.5" aria-hidden />
          Verification failed
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          Verifying…
        </span>
      );
  }
}

/** Clinical data sections that render as labelled lists when present. */
const CLINICAL_SECTIONS = ["medications", "labs", "vitals"] as const;

function ClinicalDataView({ data }: { data: Record<string, unknown> }) {
  if (Object.keys(data).length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No structured clinical data was extracted.
      </p>
    );
  }

  const sectionKeys = CLINICAL_SECTIONS.filter((key) =>
    Array.isArray(data[key]),
  );
  const others = Object.entries(data).filter(
    ([key, value]) =>
      !(CLINICAL_SECTIONS as readonly string[]).includes(key) ||
      !Array.isArray(value),
  );

  return (
    <div className="space-y-3">
      {others.length > 0 && (
        <dl className="divide-y divide-border">
          {others.map(([key, value]) => (
            <div key={key} className="flex gap-3 py-1.5 first:pt-0 last:pb-0">
              <dt className="w-40 shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {titleize(key)}
              </dt>
              <dd className="min-w-0 flex-1 text-sm">
                {typeof value === "object" && value !== null ? (
                  <pre className="overflow-x-auto rounded-lg bg-muted p-2 text-xs">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                ) : (
                  formatValue(value)
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {sectionKeys.map((key) => (
        <div key={key}>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {titleize(key)}
          </p>
          <ul className="mt-1.5 space-y-1">
            {(data[key] as unknown[]).map((item, index) => (
              <li
                key={index}
                className="rounded-lg bg-muted px-3 py-1.5 text-sm"
              >
                {typeof item === "object" && item !== null
                  ? Object.entries(item)
                      .map(([k, v]) => `${titleize(k)}: ${formatValue(v)}`)
                      .join(" · ")
                  : formatValue(item)}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function titleize(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
