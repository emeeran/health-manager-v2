import { Suspense, lazy } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CalendarPlus,
  HeartPulse,
  ScanLine,
  UserRound,
} from "lucide-react";
import {
  ALERT_SEVERITY_STYLES,
  type DashboardAlert,
  type MemberScore,
} from "../../lib/types/dashboard";
import type { Member } from "../../lib/types/member";

const inputChip =
  "flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium shadow-sm transition-colors hover:border-primary/50";

const FamilyRadar = lazy(() => import("./family-radar"));

/** Dismissal-free alert strip (severity-colored) from the dashboard feed. */
export function AlertStrip({ alerts }: { alerts: DashboardAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <section aria-label="Health alerts" className="space-y-2">
      {alerts.slice(0, 4).map((alert) => (
        <div
          key={alert.id}
          role="alert"
          className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${ALERT_SEVERITY_STYLES[alert.severity] ?? ALERT_SEVERITY_STYLES.low}`}
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="font-medium">{alert.title}</p>
            <p className="mt-0.5 text-xs opacity-80">
              {alert.message}
              {alert.member_name ? ` · ${alert.member_name}` : ""}
            </p>
          </div>
        </div>
      ))}
    </section>
  );
}

/** Member chips row linking to each member's page. */
export function FamilyStrip({ members }: { members: Member[] }) {
  if (members.length === 0) return null;
  return (
    <nav aria-label="Family members" className="flex flex-wrap gap-2">
      {members.map((member) => (
        <Link
          key={member.id}
          to={`/members/${member.id}`}
          className={inputChip}
        >
          <span className="flex size-6 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
            {member.name.charAt(0).toUpperCase()}
          </span>
          {member.name}
        </Link>
      ))}
    </nav>
  );
}

/** Quick actions: new record / add vital / batch scan. */
export function QuickActions({ firstMemberId }: { firstMemberId: string }) {
  const actions = [
    {
      label: "New record",
      icon: CalendarPlus,
      to: firstMemberId ? `/members/${firstMemberId}` : "/members",
    },
    {
      label: "Add vital",
      icon: Activity,
      to: firstMemberId ? `/members/${firstMemberId}?tab=trends` : "/members",
    },
    {
      label: "Batch scan",
      icon: ScanLine,
      to: firstMemberId ? `/members/${firstMemberId}?tab=records` : "/members",
    },
  ];
  return (
    <div
      role="group"
      aria-label="Quick actions"
      className="flex flex-wrap gap-2"
    >
      {actions.map(({ label, icon: Icon, to }) => (
        <Link key={label} to={to} className={inputChip}>
          <Icon className="size-4 text-primary" aria-hidden />
          {label}
        </Link>
      ))}
    </div>
  );
}

/** Per-member health score cards (+ radar comparison when ≥2 members). */
export function HealthOverview({
  scores,
  members,
}: {
  scores: MemberScore[];
  members: Member[];
}) {
  if (scores.length === 0) return null;
  const nameOf = (score: MemberScore) =>
    score.name ||
    members.find((member) => member.id === score.member_id)?.name ||
    "Member";

  const withBreakdown = scores.filter(
    (score) =>
      score.score_breakdown && Object.keys(score.score_breakdown).length > 0,
  );
  const sharedKeys =
    withBreakdown.length >= 2 &&
    withBreakdown.every(
      (score) =>
        Object.keys(score.score_breakdown ?? []).length ===
        Object.keys(withBreakdown[0].score_breakdown ?? []).length,
    )
      ? Object.keys(withBreakdown[0].score_breakdown ?? {})
      : null;

  return (
    <section aria-label="Health overview" className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <HeartPulse className="size-4 text-primary" aria-hidden />
        Health overview
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2">
        {scores.map((score) => (
          <li
            key={score.member_id}
            className="rounded-xl border border-border bg-card p-4 shadow-sm"
          >
            <div className="flex items-center justify-between gap-2">
              <Link
                to={
                  score.member_id ? `/members/${score.member_id}` : "/members"
                }
                className="flex min-w-0 items-center gap-2 text-sm font-semibold hover:text-primary"
              >
                <UserRound className="size-4 text-primary" aria-hidden />
                <span className="truncate">{nameOf(score)}</span>
              </Link>
              {score.risk_level && (
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                    score.risk_level === "high"
                      ? "bg-danger/10 text-danger"
                      : score.risk_level === "moderate"
                        ? "bg-warning/15 text-warning-foreground"
                        : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                  }`}
                >
                  {score.risk_level} risk
                </span>
              )}
            </div>
            <div className="mt-2 flex items-baseline gap-1">
              <span className="text-2xl font-semibold tabular-nums tracking-tight">
                {score.health_score}
              </span>
              <span className="text-xs text-muted-foreground">/100</span>
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.min(100, score.health_score)}%` }}
              />
            </div>
            {score.score_breakdown && (
              <p className="mt-2 truncate text-xs text-muted-foreground">
                {Object.entries(score.score_breakdown)
                  .map(([, item]) => `${item.label} ${item.score}/${item.max}`)
                  .join(" · ")}
              </p>
            )}
          </li>
        ))}
      </ul>
      {sharedKeys && (
        <Suspense
          fallback={
            <div className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
              Loading chart…
            </div>
          }
        >
          <FamilyRadar scores={withBreakdown} keys={sharedKeys} />
        </Suspense>
      )}
    </section>
  );
}
