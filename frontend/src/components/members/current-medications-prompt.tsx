import { useState } from "react";
import { Check, Loader2, Pill, RefreshCw, X } from "lucide-react";
import useSWR from "swr";
import {
  getMember,
  mergeCurrentMedications,
  updateMember,
} from "../../lib/api/members";
import { cn } from "../../lib/utils";

/**
 * Shown on prescription records: filing a prescription may change what the
 * member currently takes, so offer an AI merge into their
 * current-medications list. Accept edits the member record; dismiss is one
 * tap and the banner stays gone for the visit (no persistence needed).
 */
export function CurrentMedicationsPrompt({ memberId }: { memberId: string }) {
  const { data: member } = useSWR(memberId ? ["member", memberId] : null, () =>
    getMember(memberId),
  );
  const [phase, setPhase] = useState<
    "idle" | "merging" | "review" | "saved" | "dismissed"
  >("idle");
  const [suggestion, setSuggestion] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function merge() {
    setPhase("merging");
    setError(null);
    try {
      const { suggestion: merged } = await mergeCurrentMedications(memberId);
      setSuggestion(merged);
      setPhase("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed.");
      setPhase("idle");
    }
  }

  async function save() {
    setError(null);
    try {
      await updateMember(memberId, {
        current_medications: suggestion || null,
      });
      setPhase("saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save list.");
    }
  }

  if (phase === "dismissed" || phase === "saved") {
    return phase === "saved" ? (
      <p
        role="status"
        className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground"
      >
        <Check className="size-4 text-primary" aria-hidden />
        Current medications updated.
      </p>
    ) : null;
  }

  return (
    <section
      aria-label="Update current medications"
      data-testid="current-medications-prompt"
      className="space-y-3 rounded-xl border border-primary/30 bg-primary/5 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Pill className="size-4 text-primary" aria-hidden />
          New prescription filed
          {member?.current_medications
            ? " — update this member's current-medications list?"
            : " — start a current-medications list for this member?"}
        </p>
        {phase === "idle" && (
          <button
            type="button"
            onClick={() => setPhase("dismissed")}
            aria-label="Dismiss current medications prompt"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        )}
      </div>

      {phase === "review" ? (
        <div className="space-y-2">
          <label className="block space-y-1.5 text-sm font-medium">
            Merged list — edit before saving if needed
            <textarea
              rows={4}
              value={suggestion}
              onChange={(e) => setSuggestion(e.target.value)}
              className={cn(
                "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring",
                "font-mono",
              )}
            />
          </label>
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void save()}
              className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Save list
            </button>
            <button
              type="button"
              onClick={() => setPhase("idle")}
              className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
            >
              Back
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
          <button
            type="button"
            onClick={() => void merge()}
            disabled={phase === "merging"}
            className="flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {phase === "merging" ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <RefreshCw className="size-4" aria-hidden />
            )}
            Merge with tracked medications
          </button>
        </div>
      )}
    </section>
  );
}
