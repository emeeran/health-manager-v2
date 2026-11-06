import { useState } from "react";
import useSWR from "swr";
import { Footprints, Loader2 } from "lucide-react";
import { getMilestones, setMilestone } from "../../lib/api/growth";
import type { MilestonesResponse } from "../../lib/types/growth";
import { formatDate, todayIso } from "../../lib/utils";

/** Developmental milestone checklist with expected-status context. */
export default function MilestonesCard({ memberId }: { memberId: string }) {
  const { data, mutate, isLoading } = useSWR<MilestonesResponse>(
    memberId ? ["milestones", memberId] : null,
    ([, id]: [string, string]) => getMilestones(id),
  );
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(key: string, achieved: boolean) {
    setBusyKey(key);
    setError(null);
    try {
      await setMilestone(memberId, key, {
        achieved: !achieved,
        achieved_on: achieved ? null : todayIso(),
      });
      await mutate();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update the milestone.",
      );
    } finally {
      setBusyKey(null);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading milestones…
      </div>
    );
  }
  // Milestones are a pediatric checkpoint — the reference set ends at 48
  // months, so the card hides for adults and members without a birth date.
  if (
    !data ||
    data.rows.length === 0 ||
    data.age_months == null ||
    data.age_months >= 72
  )
    return null;

  return (
    <section aria-label="Milestones" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Footprints className="size-5 text-primary" aria-hidden />
          Milestones
        </h2>
        {data.age_months != null && (
          <p className="text-xs text-muted-foreground">
            {data.age_months} months
          </p>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}

      <ul className="space-y-1.5">
        {data.rows.map((row) => (
          <li key={row.key}>
            <label className="flex cursor-pointer items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm shadow-sm">
              <span className="flex min-w-0 items-center gap-2">
                <input
                  type="checkbox"
                  checked={row.achieved}
                  disabled={busyKey === row.key}
                  onChange={() => void toggle(row.key, row.achieved)}
                  aria-label={row.label}
                />
                <span className="truncate">{row.label}</span>
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                ~{row.age_months} mo
                {row.achieved_on && ` · ${formatDate(row.achieved_on)}`}
                {!row.achieved && row.expected === "achieved" && (
                  <span className="ml-1 font-medium text-warning">
                    (expected by now)
                  </span>
                )}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Every child develops at their own pace — ranges here are screening
        checkpoints, not pass/fail.
      </p>
    </section>
  );
}
