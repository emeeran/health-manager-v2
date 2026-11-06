import { Loader2 } from "lucide-react";
import useSWR from "swr";
import {
  AlertStrip,
  FamilyStrip,
  HealthOverview,
  QuickActions,
} from "../components/home/dashboard-cards";
import { ActivityFeed } from "../components/home/activity-feed";
import { SmartEntryBar } from "../components/home/smart-entry-bar";
import { getDashboardSummary } from "../lib/api/dashboard";
import { listMembers } from "../lib/api/members";
import type { DashboardSummary } from "../lib/types/dashboard";
import type { Member } from "../lib/types/member";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home() {
  const { data: members } = useSWR<Member[]>("/members", listMembers);
  const {
    data: summary,
    error,
    isLoading,
  } = useSWR<DashboardSummary>("dashboard-summary", getDashboardSummary, {
    revalidateOnFocus: false,
    dedupingInterval: 30_000,
  });

  if (isLoading || (!summary && !error)) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-center gap-2 p-16 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading dashboard…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-5xl">
        <p
          role="alert"
          className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Could not load the dashboard.{" "}
          {error instanceof Error ? error.message : ""}
        </p>
      </div>
    );
  }

  const activeMembers = members ?? [];
  const alerts = summary?.alerts ?? [];
  const scores = summary?.scores ?? [];
  const householdName = summary?.household_name || "My family";
  const firstMemberId = activeMembers[0]?.id ?? "";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          {greeting()}, {householdName}
        </h1>
        <p className="text-sm text-muted-foreground">
          {activeMembers.length} member
          {activeMembers.length !== 1 ? "s" : ""}
          {summary?.record_activity?.total_last_30_days != null &&
            ` · ${summary.record_activity.total_last_30_days} records in last 30 days`}
        </p>
      </header>

      <SmartEntryBar />

      <QuickActions firstMemberId={firstMemberId} />

      <AlertStrip alerts={alerts} />

      <FamilyStrip members={activeMembers} />

      <HealthOverview scores={scores} members={activeMembers} />

      <ActivityFeed summary={summary ?? {}} />
    </div>
  );
}
