import { Check, Copy, Download, Printer } from "lucide-react";
import { useState } from "react";
import { downloadText } from "../../lib/export";
import { a5NoteToText, type A5Note } from "../../lib/types/insight";

/**
 * sessionStorage handoff: edits made on the tool page reach the print view.
 * Stored as {id, note} so a stale draft can never shadow a NEWER generated
 * note — the print page only honors a draft for the same insight id.
 */
export const A5_DRAFT_KEY = "a5-note-draft";

export interface A5Draft {
  id: string;
  note: A5Note;
}

const inputClass =
  "w-full rounded-md border border-input bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring";

const actionButton =
  "flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted";

/**
 * Field-by-field render of the structured pre-consultation note, with the
 * discussion list editable in place, plus the share/print actions
 * (WhatsApp text + A5 print sheet). Renders from the validated payload —
 * the model's raw prose is never shown.
 */
export function A5NoteView({ note, noteId }: { note: A5Note; noteId: string }) {
  const [draft, setDraft] = useState<A5Note>(note);
  const [copied, setCopied] = useState(false);
  const text = a5NoteToText(draft);

  function setItem(index: number, value: string) {
    const to_discuss = [...draft.to_discuss];
    to_discuss[index] = value;
    const next = { ...draft, to_discuss };
    setDraft(next);
    try {
      const payload: A5Draft = { id: noteId, note: next };
      sessionStorage.setItem(A5_DRAFT_KEY, JSON.stringify(payload));
    } catch {
      // sessionStorage unavailable (private mode) — editing still works live.
    }
  }

  async function copyForWhatsApp() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked — the .txt download remains available.
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Pre-consultation note (A5)</h3>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void copyForWhatsApp()} className={actionButton}>
            {copied ? (
              <Check className="size-4 text-primary" aria-hidden />
            ) : (
              <Copy className="size-4" aria-hidden />
            )}
            {copied ? "Copied" : "Copy for WhatsApp"}
          </button>
          <button
            type="button"
            onClick={() => downloadText("pre-consultation-note.txt", text)}
            className={actionButton}
          >
            <Download className="size-4" aria-hidden />
            .txt
          </button>
          <a href="/ai-tools/pre-consultation/print" target="_blank" rel="noreferrer" className={actionButton}>
            <Printer className="size-4" aria-hidden />
            Print (A5)
          </a>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-4 text-sm leading-relaxed">
        <p>
          <span className="font-semibold">Date:</span> {draft.date}
        </p>
        <p>
          <span className="font-semibold">Member Name:</span> {draft.member_name}
        </p>
        {draft.chronic_conditions.length > 0 && (
          <p>
            <span className="font-semibold">Chronic:</span>{" "}
            {draft.chronic_conditions.join(", ")}
          </p>
        )}
        {draft.chief_complaints.length > 0 && (
          <p>
            <span className="font-semibold">C/c:</span>{" "}
            {draft.chief_complaints.join("; ")}
          </p>
        )}

        <p className="mt-3 font-semibold">To discuss with doctor</p>
        <ol className="mt-1 list-inside list-decimal space-y-1">
          {draft.to_discuss.map((item, index) => (
            <li key={index}>
              <input
                value={item}
                onChange={(e) => setItem(index, e.target.value)}
                aria-label={`Discussion item ${index + 1}`}
                className={inputClass}
              />
            </li>
          ))}
        </ol>

        {draft.current_medications.length > 0 && (
          <p className="mt-3">
            <span className="font-semibold">Current medications:</span>{" "}
            {draft.current_medications.join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
