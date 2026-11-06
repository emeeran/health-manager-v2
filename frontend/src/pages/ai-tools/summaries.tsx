import { Loader2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import { InsightView } from "../../components/ai-tools/insight-tool";
import { listInsights } from "../../lib/api/insights";
import {
  INSIGHT_KINDS,
  INSIGHT_KIND_META,
  type Insight,
  type InsightKind,
} from "../../lib/types/insight";
import { formatYearMonthDay } from "../../lib/utils";

/** /ai-tools/summaries — past AI narratives for the selected member. */
export default function SummariesPage() {
  return (
    <AiToolPage title="Summaries">
      {(memberId) => <SummariesList memberId={memberId} />}
    </AiToolPage>
  );
}

function SummariesList({ memberId }: { memberId: string }) {
  const [kindFilter, setKindFilter] = useState<InsightKind | "">("");
  const { data, isLoading, error } = useSWR<Insight[]>(
    ["insights", memberId, kindFilter],
    () => listInsights(memberId, kindFilter || undefined),
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Every AI narrative generated for this member, newest first.
        </p>
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value as InsightKind | "")}
          aria-label="Filter by kind"
          className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All kinds</option>
          {INSIGHT_KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {INSIGHT_KIND_META[kind].label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load insights. {error instanceof Error ? error.message : ""}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading insights…
        </div>
      ) : !data || data.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          No insights yet — generate one from a report tool page.
        </p>
      ) : (
        <ul className="space-y-3">
          {data.map((insight) => (
            <li
              key={insight.id}
              className="rounded-xl border border-border bg-card p-5 shadow-sm"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                  {INSIGHT_KIND_META[insight.kind]?.label ?? insight.kind}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatYearMonthDay(insight.created_at)}
                </span>
              </div>
              <InsightView insight={insight} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
