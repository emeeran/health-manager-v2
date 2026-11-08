import {
  CheckCircle2,
  Circle,
  Copy,
  Download,
  Loader2,
  Printer,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { getLatestInsight, streamInsight } from "../../lib/api/insights";
import type { Insight, InsightKind } from "../../lib/types/insight";
import { downloadText } from "../../lib/export";
import { a5NoteFrom } from "../../lib/types/insight";
import { INPUT_CLASS } from "../../lib/utils";
import { Markdown } from "../shared/markdown";
import { A5NoteView } from "./a5-note-view";
import { AuditPanel } from "../reports/audit-panel";
import { VerificationBadge } from "../reports/verification-badge";

/**
 * One report-kind tool page body: shows the latest saved insight (with a
 * regenerate action) and streams a fresh one with live stage progress and
 * narrative text. Shared by every kind-specific /ai-tools page.
 *
 * `recordId` scopes per-visit kinds (visit_summary) to one doctor_visit
 * record; `structured` renders a structured payload (A5 note) instead of
 * the markdown narrative when the insight carries one.
 */
export function InsightTool({
  memberId,
  kind,
  description,
  recordId,
  structured = false,
  confirmBeforeRun = false,
}: {
  memberId: string;
  kind: InsightKind;
  description: string;
  recordId?: string;
  structured?: boolean;
  /** Ask for an explicit Continue/Cancel before burning a generation run. */
  confirmBeforeRun?: boolean;
}) {
  const {
    data: latest,
    isLoading,
    mutate,
  } = useSWR<Insight | null>(["insights", "latest", memberId, kind], () =>
    getLatestInsight(memberId, kind),
  );
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmNote, setConfirmNote] = useState("");
  const [report, setReport] = useState<Insight | null>(null);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [reached, setReached] = useState<Record<string, true>>({});
  const [runError, setRunError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Stop an in-flight stream when the page unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  // C/c style confirmation: C (or Enter) continues, Esc (or n) cancels.
  // Keystrokes in form fields (the complaints textarea) belong to the user —
  // there, Ctrl+Enter continues instead.
  useEffect(() => {
    if (!confirming) return;
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.key === "c" || event.key === "C" || event.key === "Enter") {
        event.preventDefault();
        setConfirming(false);
        void handleRun();
      } else if (event.key === "Escape" || event.key === "n" || event.key === "N") {
        event.preventDefault();
        setConfirming(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirming]);

  async function handleRun(userNote?: string) {
    if (kind === "visit_summary" && !recordId) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setReport(null);
    setNarrative("");
    setReached({});
    setRunError(null);
    try {
      const saved = await streamInsight(
        memberId,
        kind,
        (event) => {
          if (event.stage === "narrating") {
            setReached((prev) => ({ ...prev, narrating: true }));
            setNarrative((prev) => (prev ?? "") + (event.delta ?? ""));
          } else if (event.stage !== "complete") {
            setReached((prev) => ({ ...prev, [event.stage]: true }));
          }
        },
        { signal: controller.signal, recordId, note: userNote },
      );
      setReport(saved);
      await mutate(saved, { revalidate: false });
    } catch (err) {
      if (!controller.signal.aborted) {
        setRunError(
          err instanceof Error ? err.message : "Report generation failed.",
        );
      }
    } finally {
      setRunning(false);
    }
  }

  const shown = report ?? latest ?? null;
  const needsRecord = kind === "visit_summary" && !recordId;
  const a5 = structured ? a5NoteFrom(shown) : null;

  function requestRun() {
    if (running || needsRecord) return;
    if (confirmBeforeRun) {
      setConfirming(true);
    } else {
      void handleRun();
    }
  }

  function continueRun() {
    setConfirming(false);
    void handleRun(confirmNote);
    setConfirmNote("");
  }

  return (
    <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{description}</p>
        <button
          type="button"
          onClick={requestRun}
          disabled={running || needsRecord}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : latest ? (
            <RefreshCw className="size-4" aria-hidden />
          ) : (
            <Sparkles className="size-4" aria-hidden />
          )}
          {running ? "Generating…" : latest ? "Regenerate" : "Generate"}
        </button>
      </div>

      {needsRecord && (
        <p className="text-sm text-muted-foreground">
          Pick a visit above to summarize.
        </p>
      )}

      {confirming && !running && (
        <div
          role="alertdialog"
          aria-label="Confirm generation"
          className="space-y-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm"
        >
          <label className="block space-y-1">
            <span className="font-medium">
              Today's complaints / symptoms{" "}
              <span className="font-normal text-muted-foreground">
                (optional — added to the note's chief complaints)
              </span>
            </span>
            <textarea
              rows={2}
              value={confirmNote}
              autoFocus
              onChange={(e) => setConfirmNote(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  continueRun();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setConfirming(false);
                }
              }}
              placeholder="e.g. headache for 3 days, poor sleep — Enter for a new line, Ctrl+Enter to continue"
              className={`${INPUT_CLASS} w-full resize-y`}
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">
              Generate from this member's current records?
            </span>
            <span className="grow" />
            <button
              type="button"
              onClick={continueRun}
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Continue (C)
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
            >
              Cancel (Esc)
            </button>
          </div>
        </div>
      )}

      {runError && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {runError}
        </p>
      )}

      {running && (
        <div className="space-y-3" aria-live="polite">
          <StageList reached={reached} />
          {narrative !== null && <Markdown>{narrative}</Markdown>}
        </div>
      )}

      {!running &&
        (isLoading ? (
          <p className="text-sm text-muted-foreground">
            Checking for a saved report…
          </p>
        ) : shown ? (
          a5 ? (
            <A5NoteView key={shown.id} note={a5} noteId={shown.id} />
          ) : (
            <InsightView insight={shown} />
          )
        ) : (
          <p className="text-sm text-muted-foreground">
            Nothing generated yet — run it once to produce a report from this
            member's records.
          </p>
        ))}
    </div>
  );
}

const STAGES: readonly { stage: string; label: string }[] = [
  { stage: "stats", label: "Gathering history" },
  { stage: "narrating", label: "Writing narrative" },
  { stage: "verifying", label: "Verifying claims" },
];

function StageList({ reached }: { reached: Record<string, true> }) {
  return (
    <ul className="space-y-1.5">
      {STAGES.map(({ stage, label }, index) => {
        const done = STAGES.slice(index + 1).some(({ stage: s }) => reached[s]);
        const current = reached[stage] && !done;
        return (
          <li
            key={stage}
            className={`flex items-center gap-2 text-sm ${
              done ? "text-muted-foreground" : current ? "font-medium" : ""
            }`}
          >
            {done ? (
              <CheckCircle2
                className="size-4 shrink-0 text-primary"
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
            {label}
          </li>
        );
      })}
    </ul>
  );
}

export function InsightView({ insight }: { insight: Insight }) {
  const [copied, setCopied] = useState(false);
  const actionButton =
    "flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted";

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(insight.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked — the .md download remains available.
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {insight.verification_id && (
          <VerificationBadge verificationId={insight.verification_id} />
        )}
        {insight.provider_used && (
          <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
            {insight.provider_used}
          </span>
        )}
        <span className="grow" />
        <button type="button" onClick={() => void copyMarkdown()} className={actionButton}>
          {copied ? (
            <CheckCircle2 className="size-4 text-primary" aria-hidden />
          ) : (
            <Copy className="size-4" aria-hidden />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
        <button
          type="button"
          onClick={() => downloadText(`${insight.kind}-${insight.id.slice(0, 8)}.md`, insight.content)}
          className={actionButton}
        >
          <Download className="size-4" aria-hidden />
          .md
        </button>
        <a
          href={`/ai-tools/insights/${insight.id}/print`}
          target="_blank"
          rel="noreferrer"
          className={actionButton}
        >
          <Printer className="size-4" aria-hidden />
          Print
        </a>
      </div>
      {/* Report narratives are prompted as GFM markdown (see report_service
          PROMPTS); legacy plain-text reports render fine as a single paragraph. */}
      <Markdown>{insight.content}</Markdown>
      {insight.verification_id && (
        <AuditPanel verificationId={insight.verification_id} />
      )}
    </div>
  );
}
