import { ArrowLeft, Printer } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import useSWR from "swr";
import { Markdown } from "../components/shared/markdown";
import { getInsight } from "../lib/api/insights";
import { useEscapeNavigation } from "../hooks/use-escape-navigation";

/**
 * Printable report view (print/export from an insight view). Lives outside
 * AppLayout so the sidebar and header never appear in print output.
 */
export default function InsightPrint() {
  const { insightId = "" } = useParams();
  useEscapeNavigation();
  const { data: insight, isLoading } = useSWR(
    ["insight", "print", insightId],
    () => getInsight(insightId),
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between print:hidden">
        <Link
          to="/ai-tools/summaries"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Back to summaries
        </Link>
        <button
          type="button"
          onClick={() => window.print()}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Printer className="size-4" aria-hidden />
          Print / Save PDF
        </button>
      </div>

      <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading report…</p>
        ) : insight ? (
          <>
            <p className="mb-4 text-xs text-muted-foreground">
              {insight.kind} · {insight.created_at.slice(0, 10)}
            </p>
            <Markdown>{insight.content}</Markdown>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Report not found.</p>
        )}
      </div>
    </div>
  );
}
