import { Heart, Loader2 } from "lucide-react";
import useSWR from "swr";
import { getAdherenceToday } from "../../lib/api/adherence";
import { getMember } from "../../lib/api/members";
import {
  SLOT_ORDER,
  doseTime,
  type AdherenceToday,
  type ScheduledDose,
} from "../../lib/types/adherence";
import { SLOT_LABELS, type MedicationSlot } from "../../lib/types/medication";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** Dose time → `08:30 AM`, without Date() timezone pitfalls. */
function formatTime(scheduledTime: string): string {
  const [h, m] = doseTime(scheduledTime).split(":").map(Number);
  const suffix = h < 12 ? "AM" : "PM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${String(hour12).padStart(2, "0")}:${String(m).padStart(2, "0")} ${suffix}`;
}

/** `YYYY-MM-DD` → `08 Sep 2026`. */
function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")} ${MONTHS[m - 1]} ${y}`;
}

function doseLabel(dose: ScheduledDose): string {
  const unit = dose.dosage || "1 dose";
  return dose.dose_count > 1 ? `${unit} × ${dose.dose_count}` : unit;
}

interface SlotGroup {
  slot: MedicationSlot;
  time: string;
  doses: ScheduledDose[];
}

/** Group the day's doses into slot rows in canonical morning→bedtime order. */
function groupBySlot(today: AdherenceToday): SlotGroup[] {
  const bySlot = new Map<string, ScheduledDose[]>();
  for (const dose of today.doses) {
    const bucket = bySlot.get(dose.slot);
    if (bucket) bucket.push(dose);
    else bySlot.set(dose.slot, [dose]);
  }
  return SLOT_ORDER.filter((slot) => bySlot.has(slot)).map((slot) => ({
    slot,
    time: bySlot.get(slot)![0].scheduled_time,
    doses: bySlot.get(slot)!,
  }));
}

/**
 * Daily medicine schedule in the doctor's-card format (TIME / MEDICINE /
 * DOSE, grouped by slot). Shown inline in the Medicines tab and on the
 * dedicated print route; the fixed light palette keeps the screen preview
 * identical to the printed page in every theme.
 */
export function MedicineScheduleCard({ memberId }: { memberId: string }) {
  const {
    data: today,
    error,
    isLoading,
  } = useSWR(memberId ? `/members/${memberId}/adherence/today` : null, () =>
    getAdherenceToday(memberId),
  );
  const { data: member } = useSWR(
    memberId ? `/members/${memberId}` : null,
    () => getMember(memberId),
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        Loading today's schedule…
      </div>
    );
  }
  if (error || !today) {
    return (
      <p
        role="alert"
        className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
      >
        Could not load today's schedule.{" "}
        {error instanceof Error ? error.message : ""}
      </p>
    );
  }

  const slotGroups = groupBySlot(today);
  const hasPrn = today.prn.length > 0;

  return (
    <article
      aria-label="Medicine schedule"
      className="rounded-xl border border-slate-200 bg-white p-6 text-slate-900 shadow-sm print:rounded-none print:border-0 print:p-0 print:shadow-none"
    >
      <header className="flex items-start justify-between gap-4 border-b-2 border-blue-600 pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-bold tracking-wide">
            <Heart className="size-6 fill-blue-600 text-blue-600" aria-hidden />
            MY MEDICINE SCHEDULE
          </h2>
          {member?.name && (
            <p className="mt-1 text-sm font-medium text-slate-600">
              {member.name}
            </p>
          )}
        </div>
        <p className="whitespace-nowrap pt-1 text-sm">
          <span className="font-bold">Date:</span> {formatDate(today.date)}
        </p>
      </header>

      {slotGroups.length === 0 && !hasPrn ? (
        <p className="py-10 text-center text-sm text-slate-500">
          No medicines scheduled for this day.
        </p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-blue-600 text-white">
              <th className="w-28 border border-blue-600 px-3 py-2 text-left text-xs font-bold uppercase tracking-wider">
                Time
              </th>
              <th className="border border-blue-600 px-3 py-2 text-left text-xs font-bold uppercase tracking-wider">
                Medicine{" "}
                <span className="font-normal normal-case opacity-80">
                  (Brand – Generic name &amp; strength)
                </span>
              </th>
              <th className="w-24 border border-blue-600 px-3 py-2 text-left text-xs font-bold uppercase tracking-wider">
                Dose
              </th>
            </tr>
          </thead>
          <tbody>
            {slotGroups.map((group) =>
              group.doses.map((dose, index) => (
                <tr
                  key={`${dose.medication_id}:${dose.scheduled_time}`}
                  className="align-top"
                >
                  {index === 0 && (
                    <td
                      rowSpan={group.doses.length}
                      className="border border-slate-300 px-3 py-3 text-center"
                    >
                      <p className="text-base font-bold">
                        {formatTime(group.time)}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-600">
                        {SLOT_LABELS[group.slot] ?? group.slot}
                      </p>
                    </td>
                  )}
                  <td className="border border-slate-300 px-3 py-2">
                    <span className="font-semibold">{dose.medicine}</span>
                    {dose.dosage && (
                      <span className="text-slate-600"> – {dose.dosage}</span>
                    )}
                    {dose.annotation && (
                      <span className="ml-1 text-xs text-slate-500">
                        ({dose.annotation})
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap border border-slate-300 px-3 py-2">
                    {doseLabel(dose)}
                  </td>
                </tr>
              )),
            )}
            {hasPrn && (
              <tr className="align-top">
                <td className="border border-slate-300 px-3 py-3 text-center">
                  <p className="text-base font-bold">As needed</p>
                  <p className="mt-0.5 text-xs text-slate-600">Any time</p>
                </td>
                <td className="border border-slate-300 px-3 py-3">
                  <ul className="space-y-1">
                    {today.prn.map((prn) => (
                      <li key={prn.medication_id}>
                        <span className="font-semibold">{prn.medicine}</span>
                        {prn.dosage && (
                          <span className="text-slate-600">
                            {" "}
                            – {prn.dosage}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </td>
                <td className="border border-slate-300 px-3 py-3 text-sm text-slate-600">
                  When required
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      {/* Sans footer message: the printed card ends at the table, per plan. */}
    </article>
  );
}
