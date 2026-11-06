import { useMemo, useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Plus,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import {
  createAllergy,
  deleteAllergy,
  getAllergyConflicts,
  listAllergies,
  updateAllergy,
} from "../../lib/api/allergies";
import {
  ALLERGY_SEVERITIES,
  type Allergy,
  type AllergySeverity,
} from "../../lib/types/allergy";
import { INPUT_CLASS } from "../../lib/utils";

const SEVERITY_STYLES: Record<AllergySeverity, string> = {
  mild: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  moderate: "bg-warning/15 text-warning-foreground",
  severe: "bg-danger/10 text-danger",
};

/** Safety tab: allergy list CRUD + allergen–medication conflict checks. */
export function SafetyTab({ memberId }: { memberId: string }) {
  const {
    data: allergies,
    error: listError,
    isLoading,
    mutate,
  } = useSWR<Allergy[]>(
    memberId ? ["allergies", memberId] : null,
    ([, id]: [string, string]) => listAllergies(id),
  );
  const { data: conflicts } = useSWR(
    memberId && (allergies ?? []).length > 0
      ? ["allergy-conflicts", memberId]
      : null,
    ([, id]: [string, string]) => getAllergyConflicts(id),
  );

  const [substance, setSubstance] = useState("");
  const [severity, setSeverity] = useState<AllergySeverity>("mild");
  const [reaction, setReaction] = useState("");
  const [verified, setVerified] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const conflictList = useMemo(() => conflicts ?? [], [conflicts]);

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!substance.trim()) return;
    setFormError(null);
    setSaving(true);
    try {
      await createAllergy(memberId, {
        substance: substance.trim(),
        severity,
        reaction: reaction.trim() || null,
        verified,
      });
      setSubstance("");
      setReaction("");
      setVerified(false);
      await mutate();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Could not add the allergy.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleVerified(allergy: Allergy) {
    setActionError(null);
    try {
      await updateAllergy(memberId, allergy.id, {
        verified: !allergy.verified,
      });
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Update failed.");
    }
  }

  async function handleDelete(id: string) {
    setActionError(null);
    setDeleting(id);
    try {
      await deleteAllergy(memberId, id);
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="space-y-8">
      <section aria-label="Allergies" className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <ShieldCheck className="size-5 text-primary" aria-hidden />
          Allergies
        </h2>

        <form
          onSubmit={handleAdd}
          className="rounded-xl border border-border bg-card p-4 shadow-sm"
          aria-label="Add allergy"
        >
          <div className="grid gap-3 sm:grid-cols-4">
            <label className="space-y-1.5 text-sm font-medium">
              Substance
              <input
                required
                value={substance}
                onChange={(e) => setSubstance(e.target.value)}
                placeholder="e.g. penicillin"
                className={INPUT_CLASS}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Severity
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as AllergySeverity)}
                aria-label="Allergy severity"
                className={INPUT_CLASS}
              >
                {ALLERGY_SEVERITIES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              Reaction
              <input
                value={reaction}
                onChange={(e) => setReaction(e.target.value)}
                placeholder="e.g. rash"
                className={INPUT_CLASS}
              />
            </label>
            <label className="flex items-end gap-2 pb-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={verified}
                onChange={(e) => setVerified(e.target.checked)}
              />
              Clinician confirmed
            </label>
          </div>
          {formError && (
            <p
              role="alert"
              className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {formError}
            </p>
          )}
          <button
            type="submit"
            disabled={saving}
            className="mt-3 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            <Plus className="size-4" aria-hidden />
            Add allergy
          </button>
        </form>

        {isLoading ? (
          <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Loading allergies…
          </div>
        ) : listError ? (
          <p
            role="alert"
            className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            Could not load allergies.{" "}
            {listError instanceof Error ? listError.message : ""}
          </p>
        ) : (allergies ?? []).length === 0 ? (
          <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No known allergies recorded.
          </p>
        ) : (
          <ul className="space-y-2">
            {(allergies ?? []).map((allergy) => (
              <li
                key={allergy.id}
                className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm shadow-sm"
              >
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {allergy.substance}
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${SEVERITY_STYLES[allergy.severity]}`}
                    >
                      {allergy.severity}
                    </span>
                    {allergy.verified && (
                      <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="size-3" aria-hidden />
                        Verified
                      </span>
                    )}
                  </p>
                  {allergy.reaction && (
                    <p className="text-xs text-muted-foreground">
                      Reaction: {allergy.reaction}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    type="button"
                    onClick={() => void handleToggleVerified(allergy)}
                    className="rounded-lg px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {allergy.verified ? "Unverify" : "Verify"}
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${allergy.substance}`}
                    disabled={deleting === allergy.id}
                    onClick={() => void handleDelete(allergy.id)}
                    className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                  >
                    {deleting === allergy.id ? (
                      <Loader2 className="size-4 animate-spin" aria-hidden />
                    ) : (
                      <Trash2 className="size-4" aria-hidden />
                    )}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {actionError && (
          <p
            role="alert"
            className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {actionError}
          </p>
        )}
      </section>

      <AllergyConflicts conflicts={conflictList} />
    </div>
  );
}

function AllergyConflicts({
  conflicts,
}: {
  conflicts: {
    allergy: string;
    severity: string;
    medication: string;
    matched_on: string;
  }[];
}) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed || conflicts.length === 0) return null;

  return (
    <section
      aria-label="Allergy conflicts"
      className="space-y-2 rounded-xl border border-warning/40 bg-warning/5 p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-warning-foreground">
          <AlertTriangle className="size-4" aria-hidden />
          Medication conflicts ({conflicts.length})
        </p>
        <button
          type="button"
          aria-label="Dismiss conflicts"
          onClick={() => setDismissed(true)}
          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <ul className="space-y-1.5">
        {conflicts.map((conflict) => (
          <li
            key={`${conflict.allergy}-${conflict.medication}-${conflict.matched_on}`}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm"
          >
            <span className="font-medium">{conflict.medication}</span>{" "}
            <span className="text-muted-foreground">
              matches allergy “{conflict.allergy}” ({conflict.severity}, by{" "}
              {conflict.matched_on === "ingredient"
                ? "ingredient"
                : "medicine name"}
              )
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Decision-support hints based on name matching — always confirm with the
        prescribing clinician before changing any medication.
      </p>
    </section>
  );
}
