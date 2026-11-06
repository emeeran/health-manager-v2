import useSWR from "swr";
import { Loader2, Syringe } from "lucide-react";
import { getImmunizationSchedule } from "../../lib/api/growth";
import {
  DOSE_STATUS_STYLES,
  type ImmunizationSchedule,
} from "../../lib/types/growth";
import { formatDate } from "../../lib/utils";

/** UIP immunization schedule with catch-up dates and per-dose status. */
export default function ImmunizationCard({ memberId }: { memberId: string }) {
  const { data, error, isLoading } = useSWR<ImmunizationSchedule>(
    memberId ? ["imm-schedule", memberId] : null,
    ([, id]: [string, string]) => getImmunizationSchedule(id),
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading schedule…
      </div>
    );
  }
  // Schedule requires a known date of birth; degrade silently for adults.
  if (error || !data) return null;

  return (
    <section aria-label="Immunization schedule" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Syringe className="size-5 text-primary" aria-hidden />
          Immunization schedule
        </h2>
        <p className="text-xs text-muted-foreground">
          {data.summary.complete}/{data.summary.total} done
          {data.summary.overdue > 0 && (
            <span className="ml-1 font-medium text-danger">
              · {data.summary.overdue} overdue
            </span>
          )}
        </p>
      </div>

      <ul className="space-y-1.5">
        {data.doses.map((dose) => (
          <li
            key={dose.label}
            className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-sm shadow-sm"
          >
            <span className="truncate font-medium">{dose.label}</span>
            <span className="flex shrink-0 items-center gap-2 text-xs">
              <span className="text-muted-foreground">
                {formatDate(dose.due_date)}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 font-medium capitalize ${DOSE_STATUS_STYLES[dose.status]}`}
              >
                {dose.status}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{data.disclaimer}</p>
    </section>
  );
}
