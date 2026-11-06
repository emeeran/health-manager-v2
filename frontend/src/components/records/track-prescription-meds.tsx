import { useState } from "react";
import { Check, Loader2, Pill } from "lucide-react";
import useSWR, { mutate as globalMutate } from "swr";
import { createMedication, listMedications } from "../../lib/api/medications";
import type { HealthRecord } from "../../lib/types/record";

interface ExtractedMed {
  name: string;
  dosage?: string;
  timing?: string;
  duration_days?: number;
}

/** Defensive parse of the extraction payload's medications array. */
function extractedMeds(
  clinical: Record<string, unknown> | null,
): ExtractedMed[] {
  const raw = clinical?.medications;
  if (!Array.isArray(raw)) return [];
  const meds: ExtractedMed[] = [];
  for (const item of raw) {
    const name = typeof item?.name === "string" ? item.name.trim() : undefined;
    if (!name) continue;
    meds.push({
      name,
      ...(typeof item?.dosage === "string" && item.dosage.trim()
        ? { dosage: item.dosage.trim() }
        : {}),
      ...(typeof item?.timing === "string" && item.timing.trim()
        ? { timing: item.timing.trim() }
        : {}),
      ...(typeof item?.duration_days === "number" && item.duration_days > 0
        ? { duration_days: Math.round(item.duration_days) }
        : {}),
    });
  }
  return meds;
}

/**
 * Extraction closes the loop: medications found in a prescription document
 * land in clinical_data but never become tracked Medication rows on their
 * own — so they never reach the pillbox. This section offers to create
 * them (daily schedule, default slots) with a duplicate check against the
 * member's existing medicines.
 */
export function TrackPrescriptionMeds({
  memberId,
  record,
}: {
  memberId: string;
  record: HealthRecord;
}) {
  const meds = extractedMeds(record.clinical_data);
  const { data: tracked } = useSWR(
    meds.length > 0 ? ["medications", memberId] : null,
    () => listMedications(memberId),
  );
  const [phase, setPhase] = useState<"idle" | "creating" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  if (meds.length === 0) return null;

  const trackedNames = new Set(
    (tracked ?? []).map((m) => m.medicine.trim().toLowerCase()),
  );
  // Compare only against active rows so re-filing a stopped med still works.
  const untracked = meds.filter(
    (med) => !trackedNames.has(med.name.toLowerCase()),
  );

  if (untracked.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
        <Check className="size-4 text-primary" aria-hidden />
        All {meds.length > 1 ? `${meds.length} medicines` : "medicine"} from
        this prescription are already tracked.
      </p>
    );
  }

  async function trackAll() {
    setPhase("creating");
    setError(null);
    try {
      for (const med of untracked) {
        await createMedication(memberId, {
          medicine: med.name,
          record_id: record.id,
          ...(med.dosage ? { dosage: med.dosage } : {}),
          ...(med.timing ? { timing: med.timing } : {}),
          ...(med.duration_days ? { duration_days: med.duration_days } : {}),
          schedule_type: "daily",
        });
      }
      // The pillbox and lists key off these; refresh them immediately.
      await globalMutate(["medications", memberId]);
      await globalMutate(`/members/${memberId}/adherence/today`);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add medicines.");
      setPhase("idle");
    }
  }

  return (
    <section
      aria-label="Track prescription medicines"
      data-testid="track-prescription-meds"
      className="space-y-3 rounded-xl border border-primary/30 bg-primary/5 p-4"
    >
      {phase === "done" ? (
        <p
          role="status"
          className="flex items-center gap-2 text-sm font-medium"
        >
          <Check className="size-4 text-primary" aria-hidden />
          Added {meds.length > 1 ? `${meds.length} medicines` : "medicine"} to
          this member's schedule — they now appear in Today's medicines.
        </p>
      ) : (
        <>
          <p className="flex items-center gap-2 text-sm font-medium">
            <Pill className="size-4 text-primary" aria-hidden />
            {untracked.length === 1
              ? "1 medicine in this prescription isn't tracked yet"
              : `${untracked.length} medicines in this prescription aren't tracked yet`}
          </p>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {untracked.map((med) => (
              <li key={med.name}>
                {med.name}
                {med.dosage ? ` — ${med.dosage}` : ""}
                {med.timing ? `, ${med.timing}` : ""}
              </li>
            ))}
          </ul>
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
          <button
            type="button"
            onClick={() => void trackAll()}
            disabled={phase === "creating"}
            className="flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {phase === "creating" && (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            )}
            Add to Today's medicines
          </button>
        </>
      )}
    </section>
  );
}
