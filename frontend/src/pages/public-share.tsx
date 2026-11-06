import {
  AlertTriangle,
  Biohazard,
  ClipboardList,
  Pill,
  Stethoscope,
} from "lucide-react";
import { useParams } from "react-router-dom";
import useSWR from "swr";
import { getPublicShare } from "../lib/api/public";
import { cn } from "../lib/utils";
import type { PublicShare } from "../lib/types/share";
import { AppLogo } from "../components/layout/app-logo";

/**
 * Public emergency summary behind a share token. Lives outside the auth
 * guard: the visitor — often a clinician — has no account and must not be
 * bounced to /login.
 */
export default function PublicShare() {
  const { token = "" } = useParams();
  const {
    data: share,
    isLoading: loading,
    error,
  } = useSWR<PublicShare>(token, () => getPublicShare(token));

  return (
    <div className="flex min-h-screen items-start justify-center bg-background p-4 sm:p-8">
      <div className="w-full max-w-lg space-y-5">
        <div className="flex items-center gap-2.5">
          <AppLogo className="size-9" />
          <div className="leading-tight">
            <p className="text-sm font-semibold">Family Health Manager</p>
            <p className="text-xs text-muted-foreground">Emergency summary</p>
          </div>
        </div>

        {loading ? (
          <p className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
            Loading…
          </p>
        ) : error || !share ? (
          <div className="rounded-xl border border-border bg-card p-8 text-center">
            <AlertTriangle
              className="mx-auto size-8 text-warning"
              aria-hidden
            />
            <p role="alert" className="mt-3 text-sm font-medium">
              This link can't be opened
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {error instanceof Error && error.message
                ? error.message
                : "The share link is invalid or has expired."}{" "}
              Ask the family for a fresh link — old ones stop working when
              revoked or expired.
            </p>
          </div>
        ) : (
          <ShareCard share={share} />
        )}
      </div>
    </div>
  );
}

function ShareCard({ share }: { share: PublicShare }) {
  const { member } = share;
  return (
    <div className="space-y-4 rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="flex items-center gap-3 border-b border-border pb-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/15 text-lg font-semibold text-primary">
          {member.name.charAt(0).toUpperCase()}
        </span>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {member.name}
          </h1>
          <div className="mt-0.5 flex items-center gap-2 text-sm text-muted-foreground">
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium capitalize text-primary">
              {member.relationship}
            </span>
            {member.age_years !== null && (
              <span className="text-xs">
                {member.age_years} {member.age_years === 1 ? "year" : "years"}{" "}
                old
              </span>
            )}
          </div>
        </div>
      </div>

      <SummaryList
        icon={<Pill className="size-4" aria-hidden />}
        label="Medications"
        empty="No active medications."
      >
        {share.medications.map((medication) => (
          <li
            key={medication.medicine}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="font-medium">{medication.medicine}</span>
            {medication.dosage && (
              <span className="text-muted-foreground">{medication.dosage}</span>
            )}
          </li>
        ))}
      </SummaryList>

      <SummaryList
        icon={<Biohazard className="size-4" aria-hidden />}
        label="Allergies"
        empty="No known allergies."
      >
        {share.allergies.map((allergy) => (
          <li
            key={allergy.substance}
            className="flex items-center justify-between gap-3 text-sm"
          >
            <span className="font-medium">{allergy.substance}</span>
            {allergy.severity && (
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  severityClasses(allergy.severity),
                )}
              >
                {allergy.severity}
              </span>
            )}
          </li>
        ))}
      </SummaryList>

      <SummaryList
        icon={<Stethoscope className="size-4" aria-hidden />}
        label="Conditions"
        empty="No recorded conditions."
      >
        {share.conditions.map((condition) => (
          <li
            key={condition.name}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="font-medium">{condition.name}</span>
            {condition.status && (
              <span className="text-muted-foreground">{condition.status}</span>
            )}
          </li>
        ))}
      </SummaryList>

      <p className="flex items-center gap-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
        <ClipboardList className="size-3.5" aria-hidden />
        Generated{" "}
        {new Date(share.generated_at).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        })}
      </p>
    </div>
  );
}

function SummaryList({
  icon,
  label,
  empty,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  empty: string;
  children: React.ReactNode;
}) {
  const items = Array.isArray(children) ? children : [children];
  return (
    <section aria-label={label}>
      <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <span className="text-primary" aria-hidden>
          {icon}
        </span>
        {label}
      </h2>
      {items.length === 0 ? (
        <p className="mt-1.5 text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="mt-1.5 space-y-1.5">{children}</ul>
      )}
    </section>
  );
}

function severityClasses(severity: string): string {
  const key = severity.toLowerCase();
  if (["mild", "low"].includes(key)) return "bg-primary/10 text-primary";
  if (["moderate", "medium"].includes(key))
    return "bg-warning/15 text-warning-foreground";
  if (["severe", "high", "critical", "anaphylaxis"].includes(key))
    return "bg-danger/10 text-danger";
  return "bg-muted text-muted-foreground";
}
