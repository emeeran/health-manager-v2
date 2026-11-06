/** Household dashboard summary (single-call GET /dashboard). */

export interface DashboardAlert {
  id: string;
  member_id?: string;
  member_name?: string;
  alert_type: string;
  severity: "high" | "medium" | "low";
  title: string;
  message: string;
  test_name?: string | null;
  value?: string | null;
  reference?: string | null;
}

export interface ScoreBreakdownItem {
  score: number;
  max: number;
  label: string;
}

export interface MemberScore {
  member_id: string;
  name?: string;
  health_score: number;
  risk_level?: "low" | "moderate" | "high";
  score_breakdown?: Record<string, ScoreBreakdownItem>;
}

export interface DashboardRecordActivity {
  total_last_30_days: number;
  by_type: Record<string, number>;
}

export interface DashboardReminder {
  id: string;
  title: string;
  remind_at: string | null;
  repeat?: string;
}

export interface DashboardRecentRecord {
  id: string;
  member_id: string;
  member_name?: string;
  record_type: string;
  record_date: string | null;
  diagnosis: string | null;
  summary?: string | null;
}

export interface DashboardMember {
  id: string;
  name: string;
  relationship?: string;
  birth_date?: string | null;
  blood_group?: string | null;
  health_score?: number | null;
}

export interface DashboardSummary {
  alerts?: DashboardAlert[];
  scores?: MemberScore[];
  record_activity?: DashboardRecordActivity;
  household_name?: string;
  members?: DashboardMember[];
  upcoming_reminders?: DashboardReminder[];
  recent_records?: DashboardRecentRecord[];
}

export const ALERT_SEVERITY_STYLES: Record<DashboardAlert["severity"], string> =
  {
    high: "bg-danger/10 text-danger border-danger/40",
    medium: "bg-warning/15 text-warning-foreground border-warning/40",
    low: "bg-primary/10 text-primary border-primary/40",
  };
