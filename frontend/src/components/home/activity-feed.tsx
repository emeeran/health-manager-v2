import { Link } from "react-router-dom";
import { Activity, Clock, FileText } from "lucide-react";
import { recordTypeMeta } from "../../lib/record-types";
import type { DashboardSummary } from "../../lib/types/dashboard";

/** Recent records + upcoming reminders, newest first. */
export function ActivityFeed({ summary }: { summary: DashboardSummary }) {
  const records = (summary.recent_records ?? []).slice(0, 6);
  const reminders = (summary.upcoming_reminders ?? []).slice(0, 3);
  if (records.length === 0 && reminders.length === 0) return null;

  return (
    <section aria-label="Recent activity" className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Activity className="size-4 text-primary" aria-hidden />
        Recent activity
      </h2>

      {reminders.length > 0 && (
        <ul className="space-y-1.5">
          {reminders.map((reminder) => (
            <li
              key={reminder.id}
              className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm shadow-sm"
            >
              <Clock className="size-4 shrink-0 text-warning" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{reminder.title}</span>
              {reminder.remind_at && (
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(reminder.remind_at).toLocaleDateString()}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {records.length > 0 && (
        <ul className="space-y-1.5">
          {records.map((record) => {
            const { label } = recordTypeMeta(record.record_type);
            return (
              <li key={record.id}>
                <Link
                  to={
                    record.member_id
                      ? `/members/${record.member_id}/records/${record.id}`
                      : "/members"
                  }
                  className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm shadow-sm transition-colors hover:border-primary/50"
                >
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <FileText className="size-4" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{label}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {record.member_name ?? ""}
                      {record.diagnosis ? ` · ${record.diagnosis}` : ""}
                    </span>
                  </span>
                  {record.record_date && (
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {record.record_date}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
