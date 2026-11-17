import {
  CheckCircle2,
  Circle,
  Loader2,
  MinusCircle,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { VerificationBadge } from "../verification-badge";
import { ClinicalDataView } from "./clinical-data-view";
import { streamExtract } from "../../lib/api/ai";
import { downloadAttachment } from "../../lib/api/attachments";
import {
  applyExtraction,
  type ApplyExtractionInput,
} from "../../lib/api/records";
import { type Attachment } from "../../lib/types/attachment";
import type {
  ExtractStage,
  ExtractionResult,
  Verification,
} from "../../lib/types/ai";
import { errorMessage } from "../../lib/utils";

const EXTRACT_STAGES: readonly { stage: ExtractStage; label: string }[] = [
  { stage: "reading", label: "Reading document" },
  { stage: "extracting", label: "Extracting data" },
  { stage: "verifying", label: "Verifying result" },
  { stage: "report", label: "Writing consolidated report" },
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
export function ExtractWithAi({
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
            event.stage === "verifying" ||
            event.stage === "report"
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
          errorMessage(err, "Extraction failed. Try again."),
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
        errorMessage(err, "Could not apply to the record."),
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
        const blob = await downloadAttachment(attachment.id);
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
              event.stage === "verifying" ||
              event.stage === "report"
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
          detail: errorMessage(err, "extraction failed"),
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
                {verification && <VerificationBadge verification={verification} />}
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
