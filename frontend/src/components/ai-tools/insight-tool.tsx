import {
  CheckCircle2,
  Circle,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { getLatestInsight, streamInsight } from "../../lib/api/insights";
import type { Insight, InsightKind } from "../../lib/types/insight";
import { Markdown } from "../shared/markdown";
import { AuditPanel } from "../reports/audit-panel";
import { VerificationBadge } from "../reports/verification-badge";

/**
 * One report-kind tool page body: shows the latest saved insight (with a
 * regenerate action) and streams a fresh one with live stage progress and
 * narrative text. Shared by every kind-specific /ai-tools page.
 */
export function InsightTool({
  memberId,
  kind,
  description,
}: {
  memberId: string;
  kind: InsightKind;
  description: string;
}) {
  const {
    data: latest,
    isLoading,
    mutate,
  } = useSWR<Insight | null>(["insights", "latest", memberId, kind], () =>
    getLatestInsight(memberId, kind),
  );
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<Insight | null>(null);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [reached, setReached] = useState<Record<string, true>>({});
  const [runError, setRunError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Stop an in-flight stream when the page unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleRun() {
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
        { signal: controller.signal },
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

  return (
    <div className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{description}</p>
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running}
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
          <InsightView insight={shown} />
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
