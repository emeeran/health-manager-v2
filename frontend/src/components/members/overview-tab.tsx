import { Cake, Droplets, HeartPulse, UserRound } from "lucide-react";
import { CareTeamSection } from "./care-team-section";
import { InsuranceSection } from "./insurance-section";
import RemindersSection from "../reminders/reminders-section";
import type { Member } from "../../lib/types/member";

function ageFrom(birthDate: string | null): number | null {
  if (!birthDate) return null;
  const born = new Date(birthDate);
  if (Number.isNaN(born.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const months = now.getMonth() - born.getMonth();
  if (months < 0 || (months === 0 && now.getDate() < born.getDate())) age--;
  return age >= 0 ? age : null;
}

/** Overview tab: member summary card + reminders/care team/insurance.
 * Report generation lives in the /ai-tools suite. */
export function OverviewTab({ member }: { member?: Member }) {
  const age = ageFrom(member?.birth_date ?? null);

  return (
    <div className="space-y-6">
      <section
        aria-label="Member summary"
        className="rounded-xl border border-border bg-card p-4 shadow-sm"
      >
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <HeartPulse className="size-4 text-primary" aria-hidden />
          Summary
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <SummaryItem icon={UserRound} label="Relationship">
            <span className="capitalize">{member?.relationship ?? "—"}</span>
          </SummaryItem>
          <SummaryItem icon={Cake} label="Age">
            {age !== null ? `${age} ${age === 1 ? "year" : "years"} old` : "—"}
          </SummaryItem>
          <SummaryItem icon={Droplets} label="Blood group">
            {member?.blood_group ?? "—"}
          </SummaryItem>
          <SummaryItem icon={HeartPulse} label="Medical history">
            {member?.medical_history || "—"}
          </SummaryItem>
        </div>
      </section>

      {member && (
        <>
          <RemindersSection memberId={member.id} />
          <CareTeamSection memberId={member.id} />
          <InsuranceSection memberId={member.id} />
        </>
      )}
    </div>
  );
}

function SummaryItem({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof UserRound;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="mt-0.5 break-words text-sm">{children}</p>
      </div>
    </div>
  );
}
