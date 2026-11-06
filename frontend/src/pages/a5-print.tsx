import { ArrowLeft, Printer } from "lucide-react";
import { Link } from "react-router-dom";
import useSWR from "swr";
import { A5_DRAFT_KEY, type A5Draft } from "../components/ai-tools/a5-note-view";
import { getLatestA5NoteInsight } from "../lib/api/insights";
import { a5NoteFrom, a5NoteToText, type A5Note } from "../lib/types/insight";
import { useEscapeNavigation } from "../hooks/use-escape-navigation";

/**
 * A5 print sheet for the pre-consultation note (Print (A5) from the tool
 * page). Lives outside AppLayout; edits made on the tool page arrive via
 * sessionStorage — honored only for the SAME insight, so a stale draft can
 * never shadow a newer generated note.
 */
export default function A5Print() {
  useEscapeNavigation();
  const { data: insight } = useSWR(["insight", "a5-print"], getLatestA5NoteInsight);

  let note: A5Note | null = insight ? a5NoteFrom(insight) : null;
  try {
    const raw = sessionStorage.getItem(A5_DRAFT_KEY);
    if (raw && insight) {
      const draft = JSON.parse(raw) as Partial<A5Draft>;
      if (draft.id === insight.id && draft.note) {
        note = a5NoteFrom({
          ...insight,
          sources: { a5_note: draft.note },
        });
      }
    }
  } catch {
    // Corrupt draft — the saved note stands.
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* A5 sheet geometry — overrides the global 10mm print margin. */}
      <style>{`@media print { @page { size: A5; margin: 12mm } }`}</style>

      <div className="flex items-center justify-between print:hidden">
        <Link
          to="/ai-tools/pre-consultation"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Back to pre-consultation
        </Link>
        <button
          type="button"
          onClick={() => window.print()}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Printer className="size-4" aria-hidden />
          Print (A5)
        </button>
      </div>

      <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
        {note ? (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
            {a5NoteToText(note)}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground">
            No pre-consultation note yet — generate one on the tool page first.
          </p>
        )}
      </div>
    </div>
  );
}
